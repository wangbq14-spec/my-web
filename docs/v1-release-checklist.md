# Omnixa V1 发布清单（V1 Release Checklist）

> 用途：冻结 V1 Release Candidate 之后、部署到首批学生之前的**强制门禁清单**。每一项必须为 `PASS`；`FAIL` 阻塞发布，`N/A` 需在备注写明原因。
> 关联文档：`docs/deployment.md`（部署步骤）、`docs/acceptance-checklist.md`（人工验收）、`docs/go-live-readiness-report.md`（Go-Live 收口报告）、`docs/classroom-beta-rc1-report.md`（黄金路径/错误路径 E2E 证据）。

---

## 0. 代码门禁（自动化，全部必须 PASS）

| # | 门禁 | 命令 | 冻结结果 |
| --- | --- | --- | --- |
| G1 | 后端全量测试 | `cd backend && uv run python -m pytest` | ☑ PASS — 601 passed / 1 skipped |
| G2 | 前端单元/组件测试 | `npm run test` | ☑ PASS — 418 passed |
| G3 | Lint | `npm run lint` | ☑ PASS — 0 errors（518 warnings 非阻断） |
| G4 | 生产构建 | `npm run build` | ☑ PASS — 构建成功 |
| G5 | E2E（真实前端/后端/MySQL/Redis/Worker/计费） | `npm run test:e2e` | ☑ PASS — 7 passed（黄金路径 + 错误路径） |
| G6 | Alembic 单头 | `uv run python -m alembic heads` | ☑ PASS — `d3e4f5a6b7c8`（唯一 head） |

---

## 1. 安全门禁（Independent Review P0/P1 修复确认）

| # | 修复项 | 说明 | 冻结结果 |
| --- | --- | --- | --- |
| S1 | P0-1 限流真实 IP | 反代后按 X-Forwarded-For 分桶；`TRUST_PROXY_HEADERS` 默认关闭防伪造；`Dockerfile.backend` 加 `--proxy-headers` | ☑ PASS |
| S2 | P1-1 流式零扣费 | 文本流式 `usage=None` 时按 `CHAT_BASE_CREDIT_COST` floor 计费，杜绝免费对话 | ☑ PASS |
| S3 | P1-2 生成后 402 | 生成前按 tier 预估成本并 `require_balance`，余额不足 402 提前返回、不白烧 token | ☑ PASS |
| S4 | P1-3 客户端 model 注入 | `resolve_model` 忽略客户端 `conversation.model`，一律按服务端 tier 解析 | ☑ PASS |
| S5 | Secret 扫描 | 全仓扫描无真实密钥（仅配置字段名 / 测试夹具 / 文档示例） | ☑ PASS |
| S6 | `.gitignore` | 修复 null-byte 损坏 + 重复条目，`qa-artifacts/` 纳入忽略（提交计划中处理） | ☑ 见提交计划 |

---

## 2. 配置 / 环境（生产部署前人工确认）

| # | 项 | 要求 | 状态 |
| --- | --- | --- | --- |
| E1 | `JWT_SECRET_KEY` | 生产使用强随机值，替换所有测试/开发默认值 | ☐ |
| E2 | `INVITE_REQUIRED` | 教室场景设为 `true`（邀请码注册） | ☐ |
| E3 | `TRUST_PROXY_HEADERS` | 生产（nginx 反代后）设为 `true` | ☐ |
| E4 | 视觉提供方 | 生产 `.env` 配 `TAOTOKEN_*` / `VISION_*`（真实视觉），否则仅文本 | ☐ |
| E5 | `TRUSTED_HOSTS` | 按域名/反代地址收紧（见 known-debt） | ☐ |
| E6 | 收款码 | `PAYMENT_QR_IMAGE_URL` 配则开放扫码；留空则前端提示「暂未开放」 | ☐ |

---

## 3. 数据 / 基础设施

| # | 项 | 冻结结果 |
| --- | --- | --- |
| D1 | MySQL 持久化（重启不丢数据） | ☑ PASS — 重启 backend/worker/redis 后全表计数一致 |
| D2 | Redis AOF | ☑ 已配置 `--appendonly yes` |
| D3 | 备份/恢复 | ☑ 脚本齐备（`backup/` + `docs/backup-restore.md`），按 B1–B5 人工执行 |
| D4 | docker-compose 6 服务 | ☑ 配置就绪（mysql/redis/migration/backend/worker/frontend）；本地无 Docker，compose smoke 判 N/A |

---

## 4. 部署手交

| # | 项 | 状态 |
| --- | --- | --- |
| H1 | 部署步骤 | ☑ `docs/deployment.md` |
| H2 | 管理员账号 + 邀请码 | ☐ 生产准备（`bqw` 演示账号勿带入生产） |
| H3 | 学生引导 | ☑ `docs/classroom-beta.md` |
| H4 | 管理员操作 | ☑ `docs/beta-admin.md` |
| H5 | 人工验收 | ☐ 按 `docs/acceptance-checklist.md` 逐项执行 |

---

## 5. 冻结决策

**结论：`V1 FROZEN — READY FOR DEPLOYMENT`**

> 阻塞项（P0-1 + P1×3）已全部修复并通过后端全量测试（601 passed）与 E2E（7 passed）门禁。P2×12 为已知债（见 `docs/known-debt.md`），不阻塞首批发布，列入后续迭代。
