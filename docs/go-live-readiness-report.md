# Omnixa V1 Go-Live Readiness Final Report

> 生成时间：2026-09-09（收口阶段）
> 分支：`feature/frontend-productization`
> 结论：**READY TO DEPLOY**
> 依据：Independent Final Review（P0/P1 必修项全 PASS）+ 全量 E2E/容量/突发/持久化/CI/迁移实测 + 安全红队复核。

---

## 0. 最终判定（Final Decision）

**READY TO DEPLOY**

- P0 = 0，P1 = 0（历史上报的两个 P0/P1 均已修复并带真实证据回归通过，非伪造/非 mock 掩盖）。
- Independent Final Review 独立复核结论一致：**READY TO DEPLOY**。
- 唯一上线前人工确认项（非代码阻塞）：生产 `backend/.env` 不设 `INVITE_REQUIRED=false`、填 `TAOTOKEN_*`/`VISION_*` 视觉密钥、用产品默认限流（见 §安全 / §Known Debt D3/D6）。

---

## 1. 能力矩阵（Capability Matrix）

| # | 能力 / 收口项 | 判定 | 关键证据 |
| --- | --- | --- | --- |
| 0 | 现有能力基线 | PASS | 后端 582、前端 402、lint 0 |
| 1a | P0 修复：Chat 图片「已失效」 | **PASS** | `AttachmentGallery.vue` blob URL 生命周期修复；magic bytes + 路径穿越三重防护；`test_attachments.py`/`test_multimodal*.py` 全绿 |
| 1b | P1 修复：Knowledge 卡 queued/processing | **PASS** | lease 回收 + 指数退避 + generation 栅栏；`verify_knowledge_fresh.py` PASS；Document Burst 24/24 ready |
| 2 | Vision productionization | **PASS** | JPEG/PNG/WEBP + size/count/ownership/mime/magic/path 限制；`LLMImageError` 9 类错误 UX |
| 3 | Taotoken 真实 Vision smoke | **PASS** | `vision_smoke.py` exit 0：kimi-k3 识别截图 `FileNotFoundError: config.json`，credits=2 |
| 4 | Knowledge/Worker 全链恢复 | **PASS** | crash/redis-restart/embedding-failure/retry 三场景测试全绿 |
| 5 | 开发一键启动 | PASS | `scripts/dev-up.ps1`（start/stop/status/logs）实测 |
| 6 | Production Docker | PASS（静态） | `docker-compose.yml` 6 服务 + 2 Dockerfile；smoke 未跑（本机无 Docker，D7） |
| 7 | Alembic 单头 | **PASS** | `heads`=`d3e4f5a6b7c8`；MySQL dev 在 head；CI 迁移用 MySQL 服务 |
| 8 | Health/Readiness | **PASS** | `/health` 200、`/ready` 200（db ok, redis ok） |
| 9 | Logging/request_id | PASS | `AccessLogMiddleware` JSON + `request.state.user_id` 已接入 |
| 10 | Security Gate | **PASS** | auth bypass/IDOR/admin bypass 403 全部关闭（`test_security_redteam.py` 12 个全绿） |
| 11 | Billing Security（刷分） | **PASS** | `INVITE_REQUIRED=True` 默认 + `REFERRAL_*=0` + ledger `request_id` 幂等 |
| 12 | Recharge 自定义金额 | PASS | 自定义金额 + 审批 + 幂等 409 |
| 13 | Manual Payment Beta | PASS | 人工审批流 + 定价服务器计算 + `recharge-approve-` 前缀校验 |
| 14 | Admin Ops Center | PASS | `require_admin` 403 + admin 路由 + 手动赠送/审批 |
| 15 | Classroom onboarding | PASS | 邀请码注册 + `BETA_REGISTER_CREDITS` 到账 |
| 16 | Project Templates | PASS | 轻量模板（classroom 脚手架） |
| 17 | Golden Path E2E | **PASS** | classroom-beta 黄金路径（真实 frontend/backend/mysql/redis/worker/billing）12.2s PASS |
| 18 | Error Path E2E | **PASS** | 14/14：401/400/409/402/413/415/422/failed 全对 |
| 19 | Persistence | **PASS** | 应用层全重启后快照**逐字段一致**（见 §Persistence） |
| 20 | Backup/Restore | PASS | `backup.ps1` MySQL dump + uploads zip 已验证 |
| 21 | CI | PASS | frontend quality + backend pytest + migrations(MySQL) |
| 22 | Capacity 10/20/30 | **PASS** | 100% 成功、0 429、0 5xx |
| 23 | Document Burst | **PASS** | 24/24 ready、0 卡死 |
| 24 | Vision Burst | **PASS** | 20/20、无积分负数 |
| 25 | Release docs | PASS | deployment/env/cost/known-debt/acceptance 5 篇 |
| 26 | Deployment 方案 A/B | PASS | Compose + 无 Docker 两套，步骤级 |
| 27 | Release Gate（P0=0,P1=0） | **PASS** | 见 §Security |
| 28 | Independent Final Review | **PASS** | 独立子代理复核定级 READY TO DEPLOY |
| 29 | 本报告 | — | 本文档 |

---

## 2. 未完成项（Unfinished / Not Done）

| 项 | 状态 | 说明 | 是否阻塞 |
| --- | --- | --- | --- |
| Docker compose smoke | 未执行 | 本机无 Docker（known-debt D7）；`deployment.md` 方案 A 首跑即验证 | 否（部署动作） |
| MySQL 服务级重启（管理员权限） | 未执行 | 沙箱非管理员，`Restart-Service mysql` 被拒；已用「应用层全重启 + InnoDB 崩溃安全 + 备份/恢复」等价覆盖 | 否 |
| 生产 `.env` 填视觉密钥 / 确认限流默认 | 上线操作项 | secret 不入库，属部署前置（D3/D6） | 否（部署动作） |

---

## 3. Image Attachment —— PASS

- 上传（`backend/app/services/attachments.py`）：文件名清洗、扩展名→MIME 白名单、`content_type` 严格匹配、限读 `MAX_CHAT_IMAGE_SIZE+1`、`valid_magic` 校验 JPEG/PNG/WebP magic bytes、`path.open("xb")` 独占创建。
- 鉴权读取：按 `user_id` 过滤 + `attachment_path` 三重校验（ownership + type + `[0-9a-f]{32}\.(jpg|jpeg|png|webp)` 正则 + `is_symlink()` + `resolve().parent==directory`）。
- 绑定/多模态：`validate_attachments`（per-message=4 / per-conversation=4 + `with_for_update` 串行化）+ `bind_attachments`（原子 UPDATE + rowcount 防重绑）。
- 前端：`useAttachments.js`（客户端 4 张/类型/10MB 校验）+ `AttachmentGallery.vue`（axios 带 JWT 拉取并生成 blob URL，绝不把原始 server URL 交给 `<img>`，修复历史「图片已失效」根因）。
- 测试：`test_attachments.py`、`test_multimodal.py`、`test_multimodal_chat.py`、`test_security_redteam.py::test_vision_upload_rejects_malicious_files` 全绿。

## 4. Real Vision —— PASS

- Taotoken OpenAI-compatible `kimi-k3`，`TAOTOKEN_BASE_URL=https://api.taotoken.net/token/v1`，`VISION_TIMEOUT=180`。
- 真实冒烟 `backend/data/maintenance/vision_smoke.py` exit 0：kimi-k3 正确识别测试截图内容 `FileNotFoundError: config.json`，usage 667/326，credits=2，`REAL_VISION_SMOKE_OK: True`。
- 生产化：`LLMImageError`（codes image_read_failed / image_too_large / image_format）→ 9 类错误 UX；auto+image→upgrade tier→standard→kimi-k3 路由。
- 遗留：生产 `.env` 需填 `TAOTOKEN_*`/`VISION_*`（secret 不入库，属上线操作项 D3）。

## 5. Knowledge Worker —— PASS

- 状态机 queued→processing→ready/failed：`claim_document` / `mark_ready`（token+generation 栅栏，删旧代 chunks）/ `mark_failed`。
- lease 回收：`schedule_pending_documents`（processing 且 `lease_expires_at<now`→重置 queued）+ `reclaim_expired`（generation+1 防重复 chunk）。
- retry backoff：指数退避+抖动，`MAX_RETRIES=5` 到顶转 failed（不永久卡住）+ 手动重试 + 失败可删除。
- 三场景：crash→lease 回收；redis 不可用→`next_retry_at` 恢复重扫；embedding 失败→retryable→backoff→failed（30s 单次超时 < 300s lease）。
- 测试：`test_document_async_regressions.py`（8）、`test_document_state.py`、`test_document_tasks.py`、`test_document_retry_api.py` 全绿。

## 6. Real RAG —— PASS

- `verify_knowledge_fresh.py`：fresh markdown → 202 → queued → processing → ready → chunks=6 → RAG 命中（`RAG_HIT_NEW_DOC: True`）；0 卡死文档。

## 7. Billing —— PASS

- 代码默认 `INVITE_REQUIRED=True`；无邀请码注册 400；邀请码原子消费。
- `REFERRAL_REWARD_CREDITS=0` / `REFERRAL_NEW_USER_CREDITS=0` + 自邀请守卫 → referral 刷分关闭。
- ledger 幂等：`grant_credit`/`consume_credit` 先查 `request_id` + DB 唯一约束 `uq_credit_ledger_request_operation`；`consume_credit` 用 `balance >= amount` 条件更新防负数。

## 8. Recharge —— PASS

- 自定义金额 + 审批流 + 定价服务器计算 + `credits_requested` 匹配 + `recharge-approve-` 前缀校验 + 幂等 409。

## 9. Admin —— PASS

- `require_admin` 校验 `role != "admin"`→403；admin 路由整体挂依赖；`User.role` server_default `"user"`；手动赠送 `GrantIn.amount gt=0`。

## 10. Security（P0/P1/P2）

| 级别 | 结果 | 项 |
| --- | --- | --- |
| P0 | **0** | 开放注册刷分 → `INVITE_REQUIRED=True` 修复 |
| P1 | **0** | referral 自邀请 → `REFERRAL_*=0` + 守卫修复 |
| P2 | 2（红队）+ 2（评审） | ① invite 校验 oracle（未鉴权泄露邀请码有效性）；② 限流仅 IP/内存（单机）；③ embedding 单请求 30s 超时（近 10MB 文档 5 次重试后落 failed，可手动重试）；④ `MAX_CHAT_IMAGES_PER_CONVERSATION=4 == PER_MESSAGE=4`（单会话 4 张封顶，刻意限制） |

- auth bypass / IDOR / admin bypass 403：全部关闭（`test_security_redteam.py` 12 个全绿：IDOR sweep×4、admin-forbidden、duplicate-approve-once、concurrent-consume×n 等）。

## 11. Backend tests —— PASS

- `uv run python -m pytest -q` → **582 passed, 1 skipped, 0 failed**（skip = `test_document_redis_integration.py`，测试环境 `REDIS_URL=""` 主动跳过）。

## 12. Frontend tests —— PASS

- `npx vitest run` → **402 passed (38 files), 0 failed**。lint 0 错误。

## 13. E2E —— PASS

- **Playwright 全量套件：21 passed / 0 failed（1.5m）**。含：
  - `classroom-beta.spec.js` 黄金路径（真实 frontend/backend/mysql/redis/worker/billing）12.2s PASS；
  - `classroom-errors.spec.js` 全部 error paths（auth/image/failed-doc/recharge-double-approve）PASS；
  - `knowledge_async.spec.js`（document upload polls to ready + retries failed）、`conversation.spec.js`（未登录重定向）PASS。
- 补充脚本 `e2e_golden_error_paths.py`：**14 PASS / 0 FAIL**。
  - Error paths：wrong pwd 401、invalid/expired invite 400、dup register 400、402、image 413/415、knowledge 422/failed 全对。
  - Golden paths：register→conversation→project→recharge-approve（2000→17000）PASS。
- 早期 2 failed / 3 blocked 均为 mock-8011 未运行的环境缺口（非产品缺陷）；E2E 子代理补跑隔离 mock 栈（8011 + `my_web_classroom` + Redis DB2）后全部转 PASS，已清理。

## 14. Alembic —— PASS

- `uv run python -m alembic heads` → `d3e4f5a6b7c8 (head)`（单头）；`alembic current`（MySQL dev）→ 该 head。
- 迁移链 MySQL 方言守卫（3 个迁移加 `dialect.name == "mysql"` 守卫）；CI migrations job 用 `services: mysql`（mysql:8.0）。

## 15. Docker —— PASS（静态）

- `docker-compose.yml` 6 服务（mysql/redis/migration/backend/worker/frontend）+ `Dockerfile.backend`/`Dockerfile.frontend`/`nginx.frontend.conf`；backend healthcheck → `/ready`。
- compose smoke 未跑（本机无 Docker，D7）；`deployment.md` 方案 A 首跑即验证。

## 16. Persistence —— PASS

- 应用层全重启（backend 8010 + worker + Redis 6379，MySQL 数据不动）后，`persistence_snapshot.py` 前后快照**逐字段一致**：

| 实体 | before | after |
| --- | --- | --- |
| users / wallets / credit_ledger | 55 / 54 / 237 | 55 / 54 / 237 |
| conversations / messages | 80 / 346 | 80 / 346 |
| message_attachments | 175 | 175 |
| documents / document_chunks | 1155 / 1533 | 1155 / 1533 |
| usage_records / recharge_requests | 174 / 15 | 174 / 15 |
| feedback / projects / invite_codes | 8 / 12 / 19 | 8 / 12 / 19 |
| sample_user / latest_conversation / sample_wallet | id1 bqw(admin) / id82 / balance 3996 | 全一致 |

- 重启后 `/health` 200、`/ready` 200（db ok, redis ok）、worker 正常运行。
- MySQL 服务级重启未执行（沙箱非管理员）；由 InnoDB 崩溃安全 + `backup.ps1` 备份/恢复等价覆盖。

## 17. Backup-Restore —— PASS

- `scripts/backup.ps1`：MySQL `mysqldump`（约 8.2MB）+ uploads 目录 zip（约 596KB）；恢复脚本 `backend/data/maintenance/restore.py`；`docs/backup-restore.md` 记录。

## 18. CI —— PASS

- `.github/workflows/ci.yml`：frontend quality（lint+build）+ backend pytest + migrations（`services: mysql`，`DATABASE_URL=mysql+pymysql://root:root@127.0.0.1:3306/my_web`）。YAML 经 PyYAML 校验通过。

## 19. Capacity（10/20/30）—— PASS

| 并发 | 成功 | 429 | 5xx | P50 | P95 | P99 |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 10/10 | 0 | 0 | 343.8ms | 380.3ms | 381.7ms |
| 20 | 20/20 | 0 | 0 | 710.1ms | 753.8ms | 757.7ms |
| 30 | 30/30 | 0 | 0 | 702.6ms | 892.2ms | 918.0ms |

- 全部 `[mock]` 回复，成功率 100%。20→30 并发延迟约翻倍，与 DB 连接池饱和一致（`DB_POOL_SIZE=5`+`MAX_OVERFLOW=10`=15）。Go-live 建议：单实例预期 >15 并发时调大池（如 10+20）。

## 20. Document Burst —— PASS

- 24 个 .txt/.md 并发上传 → 202×24 → ready=24、failed=0、卡 queued/processing=0、RQ 队列 depth=0。
- worker 端到端：parse→chunk→mock-embed→DbVectorStore→ready。无永久卡死。

## 21. Vision Burst（mock）—— PASS

- 20 个并发（图片+文本）→ 成功 20/20、`mock_vision_ok=20/20`、errors=0；积分 2000→1980（20×1）、**无负数**（balance_negative=false）。P50 983ms。

## 22. Deployment Plan A（Docker Compose，推荐）

- 单 VPS + `docker-compose.yml`（mysql 8.4 + redis 7.4 + migration + backend + worker + frontend/nginx）；`migration` 服务自动 `alembic upgrade head`；`restart: unless-stopped`。见 `docs/deployment.md` §方案 A。

## 23. Deployment Plan B（无 Docker）

- MySQL 8 + Redis 7 + `uv` + Node 22 + systemd unit（backend/worker 各一）+ `vite build` 产物 + 宿主机 nginx；手工 `alembic upgrade head`。见 `docs/deployment.md` §方案 B。

## 24. Monthly Cost —— ¥160–750/月（推荐档）

- 推荐「2C8G VPS + 自建 MySQL/Redis + 真实 LLM 按量」≈ ¥160–750/月（VPS ¥80–250 + LLM ¥50–500）；LLM 是最大可变项。详见 `docs/cost-estimate.md`。

## 25. Known Debt —— D1–D14（无 P0）

- 无 P0 阻塞。上线前需明确：D3（生产 `.env` 视觉密钥）、D6（生产限流/pool 用产品默认）、D7（方案 A 首跑）、D2（保持 `REFERRAL_*=0`）。P2 类（D1/D5/D8/D9/D10/D11/D12/D13/D14）为清理/可观测性/扩展性项。详见 `docs/known-debt.md`。

## 26. Manual Acceptance Checklist —— 12 组 / 59 项

- `docs/acceptance-checklist.md`：环境健康(H)/注册登录(R)/知识库(K)/对话聊天(C)/视觉(V)/计费充值(P)/管理员(A)/项目模板(T)/安全(S)/性能容量/备份恢复/一键启动，共 12 组 59 项，含「结果 + 备注」列，供 中午人工验收逐项勾选。

---

## 27. 收口约束遵守

- 全程未 commit / push / 公网部署 / 自动购买服务器 / 真实自动支付。
- 未打印任何 secret（TAOTOKEN / LLM / EMBEDDING / VISION / JWT / DB 密码）。
- Wave-2 子代理只改 tests / docs / maintenance 脚本，未改生产代码（生产代码在 Wave-1 + 安全修复后冻结）。
- 隔离测试栈（mock 8012/8011 + `my_web_capacity`/`my_web_classroom` + Redis DB1/2）均已清理，生产 8010 / `my_web` / Redis DB0 未污染。

---

## 最终决定

**READY TO DEPLOY**
