# Omnixa First Go-Live Report

> 阶段：Production Deployment & First Go-Live（Phase 0 部署收口）
> 结论口径：**未伪造公网部署成功**。所有可离线完成的部署准备工作已核验通过；实际公网上线被「需要用户购买/配置外部资源」这一硬前置阻塞，故最终决策为 `WAITING FOR USER DEPLOYMENT DECISION`。
> 相关文件：`docs/deployment.md`（Plan A/B）、`docs/cost-estimate.md`、`docs/backup-restore.md`、`docs/acceptance-checklist.md`、`docs/known-debt.md`、`docker-compose.yml`、`Dockerfile.backend`、`Dockerfile.frontend`、`nginx.frontend.conf`、`backend/data/maintenance/create_admin.py`。

---

## 1. Deployment Plan Selected

- **主推 Plan A：单台 VPS + Docker Compose**（`docker-compose.yml` 6 服务：mysql / redis / migration / backend / worker / frontend）。
- **备选 Plan B：无 Docker 手工部署**（`uv sync --frozen` + `alembic upgrade head` + systemd + 宿主机 nginx）。
- 两套方案命令、systemd 模板、nginx 反代（含 SSE 关闭缓冲）均已写入 `docs/deployment.md`。
- **状态：方案已就绪，尚未由用户选定 VPS 落地（见 §24）。**

## 2. Architecture

```
Internet → Nginx/HTTPS (certbot, SSE 不缓冲)
        → Frontend (nginx 静态 + /api 反代)
        → FastAPI backend (uvicorn 0.0.0.0:8000)
        → MySQL 8.4 / Redis 7.4
        + RQ Worker (app.worker, 队列 document-processing)
```

Persistent Volumes：`mysql-data`、`redis-data`、`rag-uploads`（`rag-uploads` 同时覆盖知识库文档与 `chat_attachments/` 聊天图片）。容器删除/重建 ≠ 数据删除。

## 3. Hosting Provider

**未选定** —— 需用户决策并购买（§24 步骤 1）。推荐规格 2 vCPU / 8GB / 60–80GB SSD（2C4G 为最小档），见 `docs/cost-estimate.md`。

## 4. Monthly Cost

推荐档（单 VPS 2C8G 全自建 + 真实 LLM 按量）：**约 ¥160–750/月**，其中 LLM 是最大可变项。明细见 `docs/cost-estimate.md`（VPS ¥80–250 + LLM ¥50–500 + 备份 <¥20）。

## 5. Public URL

**未定** —— 需用户购买/配置域名或使用服务商公网域名/IP 做 staging smoke（§24 步骤 2）。

## 6. HTTPS

- 方案已文档化：宿主机 nginx + certbot（`docs/deployment.md` A6），HTTP→HTTPS 自动 redirect，SSE 流式关闭缓冲。
- **状态：未签发** —— 需真实域名（§24 步骤 2）。不关闭浏览器安全校验。

## 7. Backend /ready

- `/health`（存活）+ `/ready`（就绪，fail-closed 独立检查 MySQL + Redis）均已实现（`app/main.py`）。
- 本地/CI 已 PASS；**生产实例 /ready 待部署后验证**（`curl http://127.0.0.1:8000/ready` 期望 `{"status":"ready","checks":{"db":"ok","redis":"ok"}}`）。

## 8. MySQL

- Compose `mysql:8.4`，utf8mb4/utf8mb4_unicode_ci，健康检查 `mysqladmin ping`，`mysql-data` 持久卷。
- schema 正确性：CI `migrations` job 在**全新 MySQL 8.0 上 `alembic upgrade head` 通过**；迁移链单头 `d3e4f5a6b7c8`。生产实例待部署。

## 9. Redis

- Compose `redis:7.4-alpine`，AOF（`appendonly yes` / `everysec`）落 `redis-data` 卷；健康检查 `redis-cli ping`。
- 生产实例待部署；队列可重建，不备份 Redis 数据本身。

## 10. Worker

- RQ worker + 5s dispatcher（`app.worker`），队列名 `document-processing`（`DOCUMENT_TASK_QUEUE`，与 production `.env` 一致）。
- lease 300s + 重试 5 次（60s→3600s 退避），worker 重启后任务可恢复（单测覆盖）。生产 worker 待部署。

## 11. Migration

- **正式决策：独立一次性 `migration` 服务**运行 `alembic upgrade head`（`restart: "no"`）。
- `backend` / `worker` 通过 `depends_on: migration: service_completed_successfully` 等待迁移成功后才启动，**不会并发跑迁移**；迁移失败则 backend/worker 不启动（不进入 ready）。

## 12. Persistent Storage

- `mysql-data`（库）、`redis-data`（队列/lease）、`rag-uploads`（知识库 + 聊天图片）三卷均持久化。
- 备份命令（`mysqldump` + uploads `tar`）已写入 `docs/backup-restore.md` + 维护脚本 `backup.py` / `restore.py` / `check_fk_integrity.py` + `scripts/backup.ps1`。

## 13. Vision Production Smoke

- **真实 Provider 冒烟已在 dev 环境 PASS**（Taotoken `kimi-k3`，`VISION_TIMEOUT=180`；9/9 验证：图片上传 → attachment 持久化 → 模型响应 → UsageRecord → 扣费 → refresh 图片仍在）。
- **生产环境需在部署后重新执行一次**（需生产 `.env` 填入 `TAOTOKEN_*` / `VISION_*` 真实密钥，§24 步骤 3）。首版继续使用已验证的 `kimi-k3`，**不在首版冒险切换未验证的新 Provider**。

## 14. Knowledge Production Smoke

- dev E2E 已 PASS：上传 `python面试题.md` 等价课程资料 → queued → processing → ready → chunks>0 → Chat 提问命中。
- 生产环境需在部署后重新上传真实资料并验证（§24 步骤 5）。

## 15. RAG

- dev E2E 已 PASS（`[mock]` 命中 + 真实 embedding 链路单测绿）。生产 RAG 待部署后真实资料验证。

## 16. Credits

- 计费服务已验证：Decimal 记账、`request_id` 幂等、钱包 `SELECT ... FOR UPDATE` + 死锁重试、vision 保底扣费；Beta 注册送 `BETA_REGISTER_CREDITS=2000`。生产待部署后验证（§24 步骤 6）。

## 17. Admin

- `require_admin` 按 `role != "admin"` 判定 → 403，**绝不按用户名推断**（用户名叫 `admin` 但 role=`user` 仍是普通用户）；红队测试已验证普通用户访问 `/api/admin/*` 全 403。
- **新增安全 bootstrap 脚本 `backend/data/maintenance/create_admin.py`**：复用认证同款 `hash_password`、密码 ≥12 位、交互回显或 `--password-env` 读取、绝不打印密码、同名用户显式「提升」。4 个单测全绿。
- 生产首个管理员待部署后创建（§24 步骤 4）。

## 18. Backup

- `docs/backup-restore.md` + `backup.py`/`restore.py`/`check_fk_integrity.py` + `scripts/backup.ps1` 就绪。
- **第一份生产备份必须在发给任何同学之前执行**（MySQL + uploads + chat_attachments，记录时间戳），§24 步骤 7。

## 19. Security

- **P0 = 0，P1 = 0，P2 = 4（非阻塞）**：① invite 校验 oracle（未鉴权泄露码有效性）；② 限流仅 IP/内存（单机）；③ embedding 单请求 30s 超时（近 10MB 文档手动重试）；④ `MAX_CHAT_IMAGES_PER_CONVERSATION=4 == PER_MESSAGE=4`。
- 门禁保持：`INVITE_REQUIRED=true`、`REFERRAL_REWARD_CREDITS=0`、`REFERRAL_NEW_USER_CREDITS=0`。
- **git secret audit：无真实 secret 提交**（`.env` 与 `backend/.env` 均 gitignored；唯一 `sk-*` 命中为 `tests/test_title.py` 的脱敏测试桩，非真实密钥）。
- CORS 默认非 `*`；`TRUSTED_HOSTS` 由 env 驱动，生产须填真实域名。

## 20. Classroom Invite

- 邀请码生成/停用（服务端 32 位 hex）+ `max_uses`/`expires_at` + 并发原子消费已验证（红队 25 项）。
- 首批方案：**5 个单次码，或 1 个 `channel=classroom`、`max_uses=5` 的码**；首期 3–5 人（§24 步骤 8，需先建管理员）。

## 21. First User Rollout Plan

- Stage 1：**你自己先用 30–60 分钟**（注册→登录→Chat→Vision→Knowledge→RAG→Credits）。
- Stage 2：**3–5 个同学**，观察注册/Chat/Vision/Knowledge/RAG/Credits。
- Stage 3：稳定后扩到 10 人；最后 20–30 人。
- 24h Watch 重点：5xx / 429 / worker stuck / knowledge stuck / vision failure / attachment failure / billing 不一致 / DB 连接 / Redis 队列深度 / 磁盘；出现 P0 立即停止扩用户。

## 22. Known Debt

`docs/known-debt.md`（D1–D14）+ 上线前硬前置：
- 生产 `.env` 必须 `INVITE_REQUIRED=true`（**不得用 dev 的 `false`**）、`REFERRAL_*=0`。
- 填 `TAOTOKEN_*`/`VISION_*`、`LLM_*`、`EMBEDDING_*` 真实密钥（不可 mock 上线）。
- 使用生产默认限流/连接池（不沿用 dev 放松值）。
- 容量结论：>15 并发建议把 `DB_POOL_SIZE/DB_MAX_OVERFLOW` 提到 10+20。
- 先跑 Plan A（本机无 Docker，D7）。

## 23. Manual Acceptance Checklist

`docs/acceptance-checklist.md`（12 组 / 59 项）已就绪，覆盖：注册邀请码、Chat/Vision/RAG/Agent/Workflow、Knowledge 全链路、Usage/Credits/Recharge、Admin、Persistence、Backup、Security、Capacity、Error paths。生产冒烟时逐项勾选。

## 24. Final Decision

**`WAITING FOR USER DEPLOYMENT DECISION`**

代码、Docker/nginx/CI、迁移、持久卷、健康/就绪、request-id、结构化日志、限流、安全门禁、admin bootstrap、备份/恢复、部署文档与成本估算**全部就绪且离线核验通过**；但真实公网上线被以下**用户必须亲自完成的外部资源/决策**阻塞（我不得代购/代注册/代猜 secret）：

1. **购买一台 Linux VPS**（推荐 2C8G，约 ¥80–250/月；最小 2C4G）—— 需要你选择云厂商并付费。
2. **准备一个域名**（A 记录指向 VPS 公网 IP）用于 HTTPS；或先用服务商公网域名/IP 做 staging smoke。
3. **提供真实 API 密钥**（写入生产 `.env`）：文本 `LLM_*`、`EMBEDDING_*`、视觉 `TAOTOKEN_*`/`VISION_*`（已用 `kimi-k3` 冒烟 PASS 的那一套）。
4. **确认并授权我 commit + push**（部署需在 VPS `git clone`，当前分支 `feature/frontend-productization` 上全部成果尚未提交；§27 要求你确认）。
5. 可选：**Payment QR 图片 URL**（`PAYMENT_QR_IMAGE_URL`）；不配置则前端明示「暂未开放扫码充值」，仍可走「申请 → 管理员审核 → 手动赠积分」。
6. 授权我在你提供的 VPS 上执行部署，或你按 `docs/deployment.md` 自行执行（我会给出逐条验收命令）。

**你完成以上任一步后告诉我，我即从「staging 首部署 → /ready → 真实 Vision/Knowledge/RAG 冒烟 → 首个 admin + 邀请码 → 首份 backup → 3–5 人放量」继续推进。**
