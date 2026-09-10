# Omnixa V1 已知技术债清单（Known Debt）

> 来源：`docs/classroom-beta-rc1-report.md`（M 节已知限制 + 全篇），`backend/app/core/config.py` 代码注释，`backend/app/db/init_db.py`，`backend/app/api/routes/auth.py`，`scripts/*.ps1` 与 `docs/*.md` 中的硬编码路径。
> 用途：Go-Live 收口阶段的透明记录——**哪些是已知限制、为什么不阻塞、后续谁处理**。分级：P0 阻塞上线 / P1 上线后尽快处理 / P2 择机清理。

---

## 1. 清单总览

| # | 技术债 / 限制 | 分级 | 来源 | 影响 | 建议处置 |
| --- | --- | --- | --- | --- | --- |
| D1 | `init_db.py` 的 `Base.metadata.create_all` 死代码 | P2 | `backend/app/db/init_db.py`（`create_all` 绕过 Alembic） | 若有人误调用会与迁移链产生 schema 漂移；当前未被启动路径调用 | 删除或改为「仅测试夹具」；统一走 Alembic |
| D2 | Referral 无 IP/设备指纹防护 | P1 | `config.py` L79-82 注释、`auth.py` L50-60 | 自拉自刷 referral 无法可靠识别，故 `REFERRAL_*` 强制为 0 | 上线前保持 `REFERRAL_*=0`；未来要开 referral 需先加设备/IP 指纹或风控 |
| D3 | 真实视觉需生产 `.env` 提供外部凭据 | P1 | `data/maintenance/vision_smoke.py` | 真实 Taotoken 视觉冒烟已于 9/9 **PASS**（`vision_smoke.py` exit 0：kimi-k3 正确识别截图 `FileNotFoundError: config.json`，usage 667/326，credits=2）。遗留仅为：生产 `.env` 需填 `TAOTOKEN_*`/`VISION_*` 密钥（secret 不入库，属上线操作项而非代码阻塞） | 生产 `.env` 填 `TAOTOKEN_*` 后重跑 `vision_smoke.py` 复核 |
| D4 | 同账户高并发流式死锁边缘（MySQL 1213） | P1 | rc1-report M 节第 2 条 | 20 并发流式对同一钱包扣费时，`start` SSE 事件之后的扣费点可能 1213；已缓解（钱包行锁 + 首事件重试），残留为客户端收流错误、用户消息原子回滚、**不重复扣费** | 完整消除需「流中事务级死锁重试」；正常教室模式（单会话、前端发送中禁按钮）不触发 |
| D5 | 已延期业务指标（转化/留存/SEO 等） | P2 | rc1-report M 节第 3 条 | 纯开发环境无法度量，延至生产埋点 | 上线后接入埋点/分析，再补指标 |
| D6 | dev 栈放宽项被写入本机 `.env` | P1 | rc1-report M 节第 4 条 | `RATE_LIMIT_AUTH=200`、`RATE_LIMIT_CHAT=5000`、`DB_POOL_SIZE/MAX_OVERFLOW` 上调仅在 dev；误带入生产会削弱限流 | 生产 `.env` 用 `backend/.env.example` 的产品默认值（10/30，池 5+10 或谨慎调 10+20） |
| D7 | Docker compose smoke 未执行（本机无 Docker） | P1 | rc1-report K/L 节 | 容器化链路未经实测，`deployment.md` 方案 A 需在真实 VPS 首跑验证 | Go-Live 部署时按 `docs/deployment.md` 方案 A 首跑即验证 |
| D8 | 目录重命名遗留缓存/硬编码路径 | P2 | `docs/dev-startup.md`（`05vibeCoding` vs 旧 `vibeCoding`）、`scripts/dev-up.ps1`（`%LOCALAPPDATA%\omnixa-dev-tools\redis`）、`scripts/backup.ps1`（候选 mysqldump 路径 `D:\BtSoft\mysql\...`）、`.env.development`（硬编码 `127.0.0.1:8010`） | 重命名项目目录后，`node_modules/.vite`、`.uv-cache`、`__pycache__` 等缓存可能残留旧路径导致「路径串味」；脚本不可移植到非本机路径 | 清理缓存；脚本改为可配置路径/环境变量；文档路径统一 |
| D9 | `CREDIT_GRANT_ON_REGISTER` 无调用方的遗留配置 | P2 | `config.py` L70 + `.env.example` L68（实际生效是 `BETA_REGISTER_CREDITS`，见 `auth.py` L47） | 两个「注册赠积分」变量并存，易误配；`CREDIT_GRANT_ON_REGISTER=1000` 改动无效 | 删除该配置项或标注 deprecated |
| D10 | Worker 无 HTTP 健康端点 | P2 | `docker-compose.yml`（worker 无 healthcheck）、`dev-startup.md` | worker 只能靠进程存活 + 日志 `Listening on document-processing...` 判断，编排层无法自动探活 | 可加 `/worker/health` 或把 dispatcher 心跳接入日志采集 |
| D11 | Redis 单实例（无主从/哨兵），AOF-only | P2 | `docker-compose.yml` redis 服务 | Redis 挂掉期间 RQ 队列/lease 丢失；dispatcher 会从 MySQL 重新入队（可恢复），但瞬时吞吐受影响 | Beta 可接受；规模上去再上哨兵/托管 |
| D12 | Analytics `agent_steps` 恒为 0（设计使然） | P2 | rc1-report F 节 | Agent 计费走 `chat_messages/credits`，`agent_steps` 仅计 StepRun 行；报表维度受限 | 若需 Agent 步数报表，补 StepRun 统计口径 |
| D13 | 上传文件仅靠目录（无对象存储抽象） | P2 | `config.py` `RAG_UPLOAD_DIR`、`docs/backup-restore.md` | 单机目录存储，扩容/多副本时上传不共享 | 后续可抽象存储后端（S3/OSS） |
| D14 | `VISION_MODEL_TIER` 只能单一档位（禁止跨档位） | P2 | `config.py` L86 注释 | 视觉只能固定一个计费档位，无法按图动态调档 | 短期保持单档；长期再支持多档路由 |

---

## 2. 分级处置顺序建议

- **上线前必须明确（P0/P1 相关）**：D3（生产 `.env` 提供 `TAOTOKEN_*` 视觉密钥，真实冒烟已 PASS）、D6（生产限流/pool 用产品默认值）、D7（方案 A 首跑）、D2（保持 `REFERRAL_*=0`）。这些是 Go-Live 的前置条件或上线首日的验证动作，**均不阻塞 mock 演示模式**。
- **上线后尽快（P1）**：D4（死锁重试增强，仅极端并发触发）。
- **择机清理（P2）**：D1、D5、D8、D9、D10、D11、D12、D13、D14——多为清理/可观测性/扩展性，不影响 Beta 交付。

> 结论：**无 P0 阻塞项**（与 rc1-report 的 VERDICT: READY FOR CLASSROOM BETA 一致）。所有已知债均有记录与处置方向，可在 Go-Live 后按优先级迭代消化。
