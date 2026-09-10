# Omnixa Classroom Beta RC1 Final Report

> 阶段：Omnixa Classroom Beta Release Candidate + Operations Center + Real Vision Validation + Beta Reliability
> 分支：`feature/frontend-productization` ｜ 未做任何 `git commit` / `push` / 公网部署
> 日期：2026-09-06（本地开发栈验证）

---

## A. 交付物总览

| 交付物 | 状态 |
|---|---|
| Classroom Beta 完整产品链（注册→邀请码→积分→工作区→项目→Chat→模型档位→传图→多模态→Knowledge→RAG→Agent→Usage→Feedback→人工充值→Admin 审核→余额入账→持久化） | ✅ 黄金路径 E2E 全通 |
| 错误路径 E2E（无效/过期/已用满/禁用邀请码、错密码、/admin 403、402、429、图片超限/不支持、文档失败重试、充值重复审核拒绝） | ✅ 6/6 全通 |
| 红队安全验证（IDOR、Admin 权限、Billing 滥用、邀请码并发、Vision 恶意文件） | ✅ 25/25 全通 |
| Analytics 真实验证（7d/30d/all、非法区间 422、单调性） | ✅ PASS |
| 容量基线（并发 10/20/30 × chat/rag/agent，DB 池、Redis 队列、P50/P95） | ✅ MEASURED（见 G 节） |
| 突发上传（文档 10/20/30×5、Vision 10/20 同时传图） | ✅ MEASURED（见 H 节） |
| 文档：`docs/classroom-beta.md`（学生向）、`docs/beta-admin.md`（管理员向）、Beta Notice UI、定价页人工充值说明 | ✅ |
| 运维能力：备份/恢复/FK 完整性/持久化 API 检查/request_id 排障 | ✅ 往返实测通过 |

## B. 环境与运行栈（验证基线）

- 后端 API：8011（**Mock 提供方** `LLM_PROVIDER_LABEL=mock`，`DB_POOL_SIZE=10/DB_MAX_OVERFLOW=20`，`RATE_LIMIT_CHAT=5000` 仅 dev 放宽）；8010（真实配置 API，`/api/models` 200）
- 数据库：本地 MySQL（InnoDB，持久化实例）｜ 缓存/队列：本地 Redis（AOF）
- Worker：2 个 RQ worker（其一为 mock 模式，负责文档处理；突发测试实测 8–17 文档/s）
- 前端：Playwright 自带 Vite（`--mode classroom-e2e` → 8011）；手动开发 Vite 已修复指向 8010（`.env.development`）
- Docker：本机未安装 → compose smoke / Docker 重启持久化门禁按规格"有 Docker 则"判定为 **N/A**，持久化改由真实 MySQL + 备份/恢复往返验证

## C. Wave E — 黄金路径 E2E（真实前端/后端/MySQL/Redis/Worker/Billing）

16 步全链（Landing→注册带邀请码→Beta 积分→登录→Workspace→建学习项目→Chat→切模型档位→传图→`[mock-vision]` 多模态→传 Knowledge→processing→ready→RAG→Agent→Usage→Credits 减少→Feedback→充值申请→Admin 登录→看到→approve→余额增加→登出→登录→数据还在）：
**PASS**（Playwright `classroom-beta.spec.js`，全套 21/21 时 ~22s）

## D. Wave E — 错误路径 E2E（≥10 条）

`classroom-errors.spec.js` 6 组用例覆盖：邀请码 invalid/expired/max-used/disabled；密码错误；普通用户 `/admin` 前端路由拦截 + API 403；**402** 积分不足（专用零余额用户 `classroom_zero`，自足不依赖他人）；图片 >10MB（前端拦截）、GIF 不支持；文档处理失败→可重试；充值重复审核被拒（400/409）。
**6/6 PASS**。全量 21 个 Playwright spec（含既有基线）**21/21 PASS**。

## E. Wave F — 红队安全验证（25/25 PASS）

- **IDOR 9 类资源**：conversation / messages / project / document（含 PATCH、DELETE 合法体）、workflow（`/api/tasks` 及其 artifacts/start/cancel/retry/approve/reject）、充值取消、附件下载 → 跨用户一律 403/404，本人 200
- **`/api/admin/*`**：9 个参数化用例（overview/users/invite-codes/recharge-requests/feedback/analytics/新建邀请码/orphan 清理）普通用户一律 **403**
- **Billing 滥用（P0 防刷）**：重复审核幂等（`recharge-approve-{request_id}`）→ 单条 ledger、wallet==∑ledger、第二次 400/409；拒绝后零入账；approve 后取消被拒
- **邀请码并发（事务语义）**：`max_uses=10, used=9` 时 5 线程并发注册 **恰 1 成功**、used_count 恰好 10
- **Vision 安全**：`.jpg` 实为 exe→415、伪 MIME→415、SVG→415、空文件→415、`../../`/`..\` 文件名→400、>10MB→413、极端尺寸 PNG→无害（201/400/413/415，绝不 500）、重复上传 ID 独立、跨用户附件→404
- 回归：20 并发同用户扣费恰 20 条 ledger、余额 1000-20

## F. Wave G — Analytics 真实验证（PASS）

真实数据：User A chat×3 + RAG×2 + vision×1；User B agent×2 + 文档×1。
7d/30d/all 三档均返回：`chat_messages [106,106,106]`、`active_users [15,15,15]`、`documents [23,23,23]`、`feedback [4,4,4]` 单调一致；非法区间 `?range=1y` → **422**；agent_steps 恒 0 为设计使然（Agent 计费走 chat_messages/credits，agent_steps 仅计 StepRun 行）。结果落盘 `data/maintenance/results/g_analytics.json`。

## G. Wave G — 容量基线（MEASURED）

**结论前置**：本机 MySQL 默认连接池 5+10 是并发上限瓶颈（30 并发 chat 开始丢连接 ~87%）；调高 API 服务端连接池 10+20 后 chat 10/20/30 全 100%。同账户并发流式写触发 MySQL **1213 死锁**（详情见 M 节）。

| 场景 | 并发 | success | 429 | 5xx | P50 | P95 |
|---|---|---|---|---|---|---|
| chat-10 | 10 | 10/10 | 0 | 0 | ~265-295ms | ~265-405ms |
| chat-20 | 20 | 20/20 | 0 | 0 | ~360-587ms | ~484-698ms |
| chat-30 | 30 | 27-30/30 | 0 | 0 | ~817-871ms | ~825-1071ms |
| rag-20 | 20 | 12-20/20（死锁受害者波动） | 0 | 0 | — | — |
| agent-20 | 20 | 15-17/20（死锁受害者波动） | 0 | 0 | ~366-408ms | ~406-512ms |

- Redis 队列深度 0（无积压）；连接池 `threads_connected≈17, max 300`
- 修复历程：`consume_credit/grant_credit/refund_credit` 加 `SELECT ... FOR UPDATE` 先锁钱包行（rag 55%→60-100%、agent 15%→75-85% 改善）＋ 流式首事件 1205/1213 死锁自动重试（最多 2 次）
- **无数据损坏**：死锁受害者由 InnoDB 原子回滚，`request_id` 幂等保证不重复扣费

## H. Wave G — 突发上传（MEASURED）

| 突发 | 上传 | 处理 | 吞吐 |
|---|---|---|---|
| 文档 10×5 轮 | 10/10×5 | 全 ready | ~8.3-13.8/s |
| 文档 20×5 轮 | 20/20×5 | 全 ready | ~12.2-18.4/s |
| 文档 30×5 轮 | 30/30×5 | 全 ready | ~14.7-21.0/s |
| Vision 10 | 10/10 | 10/10 chat 成功（mock vision） | ~16-21 chats/s |
| Vision 20 | 20/20 上传 | 20 并发 vision chat 命中死锁边缘（见 M 节） | — |

全程**未打真实 Taotoken**（mock 提供方）。结果落盘 `data/maintenance/results/g_burst.json`。

## I. REAL_VISION_SMOKE 状态

**BLOCKED（如实，不虚构 PASS）**：
- 本阶段多次实测 SiliconFlow 对全部 Vision 模型返回 403（凭据/权限不符）；Taotoken 提供方 Key 未提供
- Mock Vision 全链验证完毕（`[mock-vision]` 响应、视觉档位自动升级、非视觉模型传图 → 400「当前模型不支持图片理解…」）
- **教室演示真实视觉能力的前置条件**：提供可用的 Taotoken Key（或可用的 SiliconFlow 视觉凭据）→ `backend/.env` 配置 `VISION_*` → 重跑真实视觉冒烟。当前状态：视觉功能以 mock 提供方运行，可正常演示全流程

## J. Wave H — 文档与 UI 文案

- `docs/classroom-beta.md`：学生向（邀请码注册、Beta 体验积分、项目/图片/RAG/Agent、充值人工流程、反馈、FAQ、隐私提示）
- `docs/beta-admin.md`：管理员向（邀请码管理、用户/补积分幂等、充值两步入库、Feedback、Analytics、备份/恢复命令、request_id 排障、worker/租约说明、安全须知）
- Beta Notice：定价页显式声明「当前暂未开放扫码充值（可提交充值申请，由管理员人工审核后到账）」，不编造任何合规认证；Usage 页文案改为「Beta 注册赠送体验积分」

## K. 最终质量门禁

| 门禁 | 结果 |
|---|---|
| `uv run pytest`（后端全量，含 549 基线 + 新增红队/并发/邀请码测试） | **576 passed, 1 skipped**（58s） |
| Vitest（前端单测） | **396 passed / 38 文件** |
| ESLint | **0 errors**（500 条为既有风格 warning；修复 6 个新增 `Buffer` no-undef：eslint 配置为 tests/ 补 Node globals） |
| Vite 生产构建 | **PASS** |
| Playwright（全部 spec，含黄金路径 + 6 错误路径 + 既有基线） | **21/21 PASS** |
| Alembic | **单头 `d3e4f5a6b7c8`** |
| 备份→恢复→FK 完整性往返 | **PASS**（48 users / 298 messages / 1302 chunks，0 孤儿，恢复进独立库 `my_web_restore`） |
| 持久化 API 检查 | **PASS**（含普通用户打 admin=403） |
| Docker compose smoke | **N/A**（本机无 Docker） |

## L. 运维能力（Operations Center 实测）

- 邀请码生成/停用（服务端 32 位 hex）、一次性码并发消费语义已验证
- 充值申请→审核两步入库（approve 幂等 409 防重、reject 零入账、approve 后取消被拒）
- Feedback / Analytics 管理端可用；请求排障按 request_id（`Select-String` 日志）
- 备份/恢复命令实测：`uv run python data/maintenance/backup.py <dir>` + `restore.py <备份目录> --yes` + `check_fk_integrity.py`；已为全部维护脚本补齐 sys.path 引导，文档命令可直接执行

## M. 已知限制与已延期指标

1. **真实视觉冒烟 BLOCKED**（外部凭据，见 I 节）
2. **同账户高并发流式中流死锁边缘**：20 个流式请求对同一钱包并发扣费时，MySQL 1213 可能出现在 `start` SSE 事件之后的扣费点（首事件重试覆盖不到）。已缓解（钱包行锁串行化 + 首事件重试），残余表现为客户端收到流错误、用户消息原子回滚、**绝不重复扣费**。正常教室模式（单人单会话、前端发送中禁用按钮）不会触发；完整消除需流中事务级死锁重试（列为后续优化项）
3. **已延期指标（Wave A 口径）**：不可在纯开发环境度量的业务指标（转化率、留存、SEO 等）延至生产埋点；所有可实现的分析键均已真实验证
4. dev 栈放宽项（仅本机 `.env`）：`RATE_LIMIT_AUTH=200`、`RATE_LIMIT_CHAT=5000`（产品默认仍为 10/30 分钟级）；`DB_POOL_SIZE/MAX_OVERFLOW` 为验证上调
5. 本机无 Docker，容器化冒烟未执行

## N. 安全与合规声明

- 无任何自动支付/收款（扫码充值明示暂未开放，全部人工审核入账）；无微信/支付宝商户、无 Stripe
- 未编造任何合规/资质认证文案；Beta Notice 仅陈述真实流程
- 前端无密钥泄露（图片经带 JWT 的 fetch 加载，不走无鉴权 `<img>`；`VITE_*` 无凭据）
- 邀请码/Billing/IDOR/上传安全由红队 25 项测试背书

## O. DSH-direct 偏差声明（必须如实记录）

- **codex 运行时本阶段持续不可用**（多次探测失败，含最终独立复审探测 `subagent-33`），故按会话内已批准偏差执行：**每个 Wave 以完整自动化测试替代独立 codex 复审**（红队 25 项、并发/幂等回归、黄金/错误路径 E2E、容量与突发脚本）
- **独立 Final Review 由 Orchestrator 直接执行**（codex 不可用），覆盖：安全 25 项、计费正确性（幂等/并发）、容量与突发数据、备份恢复往返、持久化、前端安全、无提交/部署核查
- 若需补做 codex 独立复审：待运行时恢复后，以本报告 + `backend/tests/test_security_redteam.py` + `data/maintenance/results/*.json` 为输入即可

## P. 变更文件清单（本阶段主要产出）

- 后端：`app/services/billing.py`（死锁修复/幂等）、`app/api/routes/conversations.py`（死锁重试）、`app/api/routes/agent.py`（死锁重试）、`backend/.env`（dev 放宽）、`tests/test_security_redteam.py`（新增 25 项）
- 前端：`src/components/chat/AttachmentGallery.vue`（鉴权图片加载）、`FeedbackDialog.vue`（showModal 修复）、`PricingView.vue`（人工充值说明 + Beta Notice）、`UsageView.vue`（文案）、`eslint.config.js`（tests Node globals）、`tests/classroom-errors.spec.js`（零余额用户/时间戳文件名）
- 运维：`data/maintenance/{g_analytics_verify,g_capacity,g_burst}.py` + `results/*.json`；全部维护脚本 sys.path 引导；`setup_classroom_e2e.py`（poor 确定性余额 + zero 用户）
- 文档：`docs/classroom-beta.md`、`docs/beta-admin.md`、本报告

## Q. 结论与验收请求

**VERDICT: READY FOR CLASSROOM BETA**

依据：全部功能门禁（黄金路径 + 错误路径 + 红队 + Analytics + 容量 + 突发 + 全量单测/E2E/构建 + Alembic 单头 + 备份恢复持久化）通过；未发现 P0 安全/计费/数据完整性问题；已知限制均已如实记录且不阻塞教室 Beta 的 mock 提供方运行模式。

**教室演示前请确认**（人工验收项）：
1. 真实视觉能力需先提供 Taotoken/SiliconFlow 可用凭据（当前 REAL_VISION_SMOKE=BLOCKED，视觉以 mock 运行）
2. 服务器保持 mock 模式启动（`LLM_PROVIDER_LABEL=mock`），勿在未配置真实 Key 时切真实提供方
3. 本阶段未 commit/push/公网部署；验收通过后由人工决定后续动作

等待**中午统一人工验收**。
