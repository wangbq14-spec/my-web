# 本地开发启动指南（Omnixa）

本指南覆盖 Windows 本地开发环境的 4 个必需进程：**MySQL → Redis → Backend → Worker**，以及可选的前端 Vite。均使用真实数据（非 mock）。

> 项目真实根目录：`C:\Users\Admin（无密码）\Desktop\05vibeCoding\my-web`（注意是 `05vibeCoding`，不是旧的 `vibeCoding`）。

## 前置

- MySQL 已在 `127.0.0.1:3306` 运行，库 `my_web`（见 `backend/.env` 的 `DATABASE_URL`）。
- 后端依赖已装（`backend/.venv` 由 `uv` 管理）。
- Redis 二进制位于 `%LOCALAPPDATA%\omnixa-dev-tools\redis\`。

## 启动顺序（每个在独立终端）

### 1. Redis（必须最先启动）

```powershell
cd "$env:LOCALAPPDATA\omnixa-dev-tools\redis"
.\redis-server.exe --port 6379 --bind 127.0.0.1 --appendonly yes --appendfsync everysec --dir ./data
```

- 必须开启 AOF（`--appendonly yes --dir ./data`），否则 RQ 队列 / lease 状态重启即丢。
- 验证：`.\redis-cli.exe -h 127.0.0.1 -p 6379 ping` 返回 `PONG`。

### 2. Backend API（8010）

```powershell
cd C:\Users\Admin（无密码）\Desktop\05vibeCoding\my-web
npm run backend
```

等价命令：

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

- 验证：`curl http://127.0.0.1:8010/health`。

### 3. Document Worker（处理知识库，必须启动）

```powershell
cd C:\Users\Admin（无密码）\Desktop\05vibeCoding\my-web\backend
.venv\Scripts\python.exe -m app.worker
```

（`uv run python -m app.worker` 等价。）

- Worker 同时运行两件事：
  1. **dispatcher 循环** —— 从 MySQL 捞 `status=queued` 的文档安全入队（这是卡住的 `python面试题.md` 自动恢复的关键，禁止直接改 SQL）。
  2. **RQ 消费者** —— 监听队列 `document-processing`（`DOCUMENT_TASK_QUEUE`），执行 parse → chunk → embedding → 落库。
- 验证：日志出现 `Listening on document-processing...`；上传文档后 status 从 `queued → processing → ready`。

### 4. Frontend Vite（5173）

```powershell
cd C:\Users\Admin（无密码）\Desktop\05vibeCoding\my-web
npm run dev
```

- 访问 `http://127.0.0.1:5173`。前端通过 `.env.development` 的 `VITE_API_BASE_URL=http://127.0.0.1:8010/api` 直连后端（后端 CORS 已放行 5173，无需 Vite 代理）。

## 一键启动 / 停止 / 状态 / 日志

`scripts\dev-up.ps1` 覆盖 **MySQL / Redis / Worker / Backend / Frontend** 五个组件的管理，幂等，后台运行并把日志落盘到 `logs\`。

```powershell
cd C:\Users\Admin（无密码）\Desktop\05vibeCoding\my-web

# 启动全部（默认，幂等：已运行的组件自动跳过）
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 start

# 停止脚本托管的进程（frontend/backend/worker/redis）
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 stop

# 查看状态（mysql/redis/backend/worker/frontend 的端口与 PID）
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 status

# 查看日志（默认全部；可指定：logs backend / logs worker / logs redis / logs frontend）
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 logs
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 logs worker
```

- 每个组件 stdout/stderr 分别落在 `logs\<name>.out.log` 与 `logs\<name>.err.log`（uvicorn / worker / RQ 的访问与任务日志主要在 `.err.log`）。
- **MySQL 是宝塔面板的 Windows 服务**（`mysql`），脚本只负责在缺失时启动它，**不会主动停止**（共享依赖）。需要停止时请以管理员手动执行 `Stop-Service mysql`。
- 需要热重载开发后端时，仍可用 `npm run backend`（带 `--reload`）；一键脚本启动的 backend 为单进程（无 reload），便于可靠 stop/status。

## 故障排查

| 症状 | 检查 |
| --- | --- |
| 知识库文档一直「排队中」 | Redis 是否 `PONG`？Worker 是否在跑且打印 `Listening on document-processing`？`REDIS_URL` 与 `DOCUMENT_TASK_QUEUE` 是否与 worker 一致（`backend/.env`）。 |
| 图片「已失效」 | 该附件 `storage_path` 指向的文件是否真实存在（目录迁移后旧附件可能真的丢失，此时「已失效」是诚实结果）。新上传后刷新应正常。 |
| 视觉返回 502/上游错误 | `TAOTOKEN_API_KEY/TAOTOKEN_BASE_URL/TAOTOKEN_VISION_MODEL` 是否配置；Taotoken 视觉模型为 `kimi-k3`（见 `/models` 的 `supported_modalities` 含 `image_url`）。 |

## 环境变量安全

- 所有密钥（`LLM_API_KEY` / `TAOTOKEN_API_KEY` / `EMBEDDING_API_KEY` / `VISION_API_KEY` / `JWT_SECRET_KEY` 等）只放在 `backend/.env`，**严禁**写入前端、git、日志或异常信息。

## 生产 Docker（Compose）

`docker-compose.yml` 编排 6 个服务：`mysql`、`redis`、`migration`、`backend`、`worker`、`frontend`。

- **前提**：根目录需存在 `.env`（由 `.env.example` 复制并填入强密码），提供 `${MYSQL_*}` / `${BACKEND_PORT}` / `${FRONTEND_PORT}` 替换与 `env_file:` 引用；`backend/.env` 提供应用密钥（已 gitignore）。
- **持久化 volumes**：`mysql-data`（MySQL，含文档/分块/embedding 向量/聊天元数据）、`redis-data`（Redis AOF，`--appendonly yes --appendfsync everysec`）、`rag-uploads`（`/app/data/uploads`：上传文档 + 聊天图片 `chat_attachments/`）。知识库向量存 MySQL（`DbVectorStore`），随 `mysql-data` 持久化。
- **迁移执行者**：仅 `migration` 一次性服务执行 `alembic upgrade head`（`restart: "no"`）；`backend` / `worker` 通过 `depends_on: migration: service_completed_successfully` 等待其完成，**不会多进程并发 migration**。
- **健康检查 / 重启**：`mysql`、`redis`、`backend` 均有 healthcheck；`backend` 探针打 `/ready`（MySQL+Redis 就绪）；长驻服务 `restart: unless-stopped`，`migration` 为 `no`。`worker`（RQ 消费进程）无 HTTP 端点，靠进程存活 + 日志 `Listening on document-processing...` 判断。
- **网络**：未显式声明，使用 Compose 默认网络，`frontend` 通过 nginx 反代到 `backend:8000`（`nginx.frontend.conf`）。
