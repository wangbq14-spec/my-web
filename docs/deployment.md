# Omnixa V1 生产部署方案（Go-Live 收口）

> 适用范围：Omnixa V1（Classroom Beta）Go-Live 收口阶段的两套可执行部署方案。
> 本文所有命令以 Linux（Ubuntu 22.04/24.04 LTS）为准；不包含任何真实密钥，只引用 `.env.example` / `backend/.env.example`。
>
> 相关文件（均已核对）：
> - `docker-compose.yml`：6 服务编排（mysql / redis / migration / backend / worker / frontend）
> - `Dockerfile.backend` / `Dockerfile.frontend` / `nginx.frontend.conf` / `.dockerignore`
> - `.env.example`（Compose 基础设施变量）、`backend/.env.example`（应用变量）
> - `docs/backup-restore.md`（备份/恢复）、`docs/env.md`（变量全量清单）
> - `backend/alembic/versions/*`（迁移链，单头 `d3e4f5a6b7c8`）

---

## 方案选择速览

| 维度 | 方案 A：Docker Compose（推荐） | 方案 B：无 Docker 手工部署（轻量备选） |
| --- | --- | --- |
| 依赖 | Docker Engine + Compose 插件 + 宿主机 nginx | MySQL 8 + Redis 7 + `uv` + Node 22 + systemd + nginx |
| 迁移 | 一次性 `migration` 服务自动 `alembic upgrade head` | 手工 `uv run alembic upgrade head` |
| 进程管理 | Compose `restart: unless-stopped` | systemd unit（backend / worker 各一） |
| 前端 | 容器内 nginx（`nginx.frontend.conf`） | `vite build` 产物 + 宿主机 nginx |
| 适合 | 生产主推，隔离性好、升级/回滚简单 | 无法装 Docker、追求极简、需手工掌控进程时 |
| 结论 | ✅ 可执行落地（`docker-compose.yml` + 两个 Dockerfile 已齐备） | ✅ 可执行落地（`pyproject.toml`/`uv.lock`/`alembic` 齐备，需补 systemd unit） |

---

# 方案 A（推荐）：单台 VPS + Docker Compose

## A0. 前置准备

- 一台 Linux VPS：**最低 2 vCPU / 4GB 内存**，推荐 2C / 8GB（规格与成本见 `docs/cost-estimate.md`）。
- 一个域名，把 A 记录指向 VPS 公网 IP（如 `app.example.com`）。
- 防火墙放行：`22`（SSH）、`80`（HTTP）、`443`（HTTPS）。**8000 / 8080 / 3306 / 6379 不要对公网开放**（后端与前端端口仅本机回环访问）。

## A1. 安装 Docker 与 nginx

```bash
# Docker Engine + Compose 插件
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"        # 重新登录使组生效
newgrp docker
docker --version && docker compose version

# 宿主机 nginx（仅作 TLS 边缘反代）+ certbot
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

## A2. 获取代码

```bash
git clone <REPO_URL> /opt/omnixa
cd /opt/omnixa
```

## A3. 配置环境变量（复制示例，不覆盖已有）

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

### A3.1 根 `.env`（Compose 基础设施变量）——必填项

编辑 `.env`（对应 `.env.example` 的 8 个键）：

| 变量 | 是否必填 | 说明 |
| --- | --- | --- |
| `MYSQL_DATABASE` | 必填 | 库名，默认 `my_web`，无需改 |
| `MYSQL_USER` | 必填 | 应用账号，默认 `my_web`（**不要用 root 跑应用**） |
| `MYSQL_PASSWORD` | **必填** | 应用账号密码，**强随机**（见下） |
| `MYSQL_ROOT_PASSWORD` | **必填** | root 密码，**强随机且与 MYSQL_PASSWORD 不同** |
| `BACKEND_PORT` | 可选 | 宿主机后端端口，默认 `8000` |
| `FRONTEND_PORT` | 可选 | 宿主机前端端口，默认 `8080` |
| `VITE_API_BASE_URL` | 可选 | 前端 API 基路径，默认 `/api`（同源反代，勿改） |
| `VITE_API_TIMEOUT` | 可选 | 前端 axios 超时（ms），默认 `10000` |

生成强随机值（**DB 密码用 hex，避免 `@:/` 等字符破坏 `DATABASE_URL`**）：

```bash
openssl rand -hex 32   # JWT_SECRET_KEY（放入 backend/.env）
openssl rand -hex 16   # MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD（放入根 .env）
```

### A3.2 `backend/.env`（应用变量）——必填项

编辑 `backend/.env`（对应 `backend/.env.example`；完整清单见 `docs/env.md`）：

- `JWT_SECRET_KEY`：**必填**，`openssl rand -hex 32` 生成（config.py 强制非空，生产禁止示例值）。
- `DATABASE_URL` / `REDIS_URL` / `RAG_UPLOAD_DIR`：**在 Compose 中被 `environment:` 覆盖**（见 `docker-compose.yml` 的 `backend`/`worker`/`migration`），后端容器内实际使用 `mysql:3306` / `redis:6379` / `/app/data/uploads`；此处保留占位即可，但需非空（`DATABASE_URL` 有 `min_length=1` 校验）。
- `CORS_ORIGINS`、`TRUSTED_HOSTS`：**必改**，加入生产域名，如 `CORS_ORIGINS=["https://app.example.com"]`、`TRUSTED_HOSTS=["app.example.com"]`（否则域名访问会被 TrustedHostMiddleware 拦下）。
- `LLM_*`（`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_FAST_MODEL`/`LLM_STANDARD_MODEL`/`LLM_REASONING_MODEL`）：真实提供方必填；仅演示可 `LLM_PROVIDER_LABEL=mock`。
- `EMBEDDING_*`（`EMBEDDING_API_KEY`/`EMBEDDING_BASE_URL`/`EMBEDDING_MODEL`）：知识库/RAG 必填（向量写入依赖）。
- 视觉：`VISION_*` 或 `TAOTOKEN_*`（真实冒烟已于 9/9 PASS，生产 `.env` 需提供密钥，见 `docs/known-debt.md` D3）。
- **Classroom Beta 门禁（必须保持）**：`INVITE_REQUIRED=true`、`REFERRAL_REWARD_CREDITS=0`、`REFERRAL_NEW_USER_CREDITS=0`（关闭自助注册刷积分 P0）。
- 计费（Beta 人工充值）：`CREDIT_PER_CNY=300`、`CUSTOM_RECHARGE_*` 保持默认；`PAYMENT_QR_IMAGE_URL` 未配置时前端明示「暂未开放扫码充值」。

## A4. 构建并启动（迁移由一次性 migration 服务执行）

```bash
docker compose up -d --build
docker compose ps
```

- `migration` 服务运行 `/app/.venv/bin/alembic upgrade head`（`restart: "no"`，一次性），当前迁移链单头为 `d3e4f5a6b7c8`。
- `backend` / `worker` 通过 `depends_on: migration: service_completed_successfully` 等待迁移完成后才启动，**不会并发跑迁移**。

## A5. 验证 `/health` 与 `/ready`

```bash
# 存活探针（仅进程存活）
curl -s http://127.0.0.1:8000/health      # 期望 {"status":"ok"}

# 就绪探针（MySQL + Redis 均就绪，fail-closed）
curl -s http://127.0.0.1:8000/ready       # 期望 {"status":"ready","checks":{"db":"ok","redis":"ok"}}

# 前端可访问
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/   # 期望 200

# 迁移日志确认升级到 head
docker compose logs migration | tail -20   # 期望出现 Running upgrade ... -> d3e4f5a6b7c8
docker compose logs -f backend worker      # worker 期望出现 Listening on document-processing...
```

## A5.1 创建首个管理员（安全 bootstrap）

管理员权限**按 `role="admin"` 字段显式授予**，绝不按用户名推断（`app/api/deps.py` 的 `require_admin` 校验 `role != "admin"` → 403，用户名恰好叫 `admin` 的普通用户仍是普通用户）。用维护脚本创建，密码走交互回显或环境变量，绝不硬编码：

```bash
# 交互式（密码不回显、不进 shell 历史）
docker compose exec backend /app/.venv/bin/python data/maintenance/create_admin.py \
  --email admin@example.com --username admin

# 非交互（自动化）：密码从环境变量读取
docker compose exec -e OMNIXA_ADMIN_PASSWORD='<强随机>' backend \
  /app/.venv/bin/python data/maintenance/create_admin.py \
  --email admin@example.com --username admin --password-env OMNIXA_ADMIN_PASSWORD
```

> 脚本 `backend/data/maintenance/create_admin.py` 复用认证同款 `hash_password`，密码长度 ≥12，绝不打印密码；同名用户已存在时自动「提升」为 admin。创建后用该账号登录应看到「运营中心」；普通用户访问 `/admin` 返回 403。

## A6. nginx 反代 + HTTPS（certbot）

宿主机 nginx 作 TLS 边缘，反代到 Compose 前端的 `127.0.0.1:8080`。**关键点：Chat/Agent 是 SSE 流式响应，必须关闭代理缓冲并放宽读超时**。

```nginx
# /etc/nginx/sites-available/omnixa
server {
    listen 80;
    server_name app.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # SSE 流式响应必需：关闭缓冲、关闭缓存、放宽读超时
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        add_header X-Accel-Buffering no;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/omnixa /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d app.example.com   # 自动获取并续期 HTTPS 证书
```

> 内层 `nginx.frontend.conf` 已把 `/api/` 反代到 `backend:8000` 并带 SPA history fallback（`try_files $uri $uri/ /index.html`），故外层只需透传整站即可。

## A7. 备份 / 恢复（引用 `docs/backup-restore.md`）

持久化数据仅两类：**MySQL（`mysql-data` 卷）** + **上传文件（`rag-uploads` 卷）**。向量存在 MySQL 里，随库备份；Redis（`redis-data` 卷）不备份。

```bash
# Docker 下备份 MySQL（宿主机执行，密码从根 .env 读取）
docker compose exec mysql mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines --triggers "$MYSQL_DATABASE" > backup/my_web_$(date +%Y%m%d_%H%M%S).sql

# 备份上传文件（rag-uploads 卷：RAG 文档 + chat_attachments/ 聊天图片）
docker compose exec backend tar czf - /app/data/uploads > backup/uploads_$(date +%Y%m%d_%H%M%S).tgz
```

恢复前先停写入：`docker compose stop backend worker`，再按 `docs/backup-restore.md` 覆盖库 + 解压 uploads + `alembic upgrade head` + 重启。也可用后端维护脚本（`backend/data/maintenance/backup.py` / `restore.py` / `check_fk_integrity.py`），见 `docs/beta-admin.md` §7。

## A8. 监控与日志

```bash
docker compose logs -f backend worker      # 实时日志（按 request_id 排障，见 docs/beta-admin.md §8）
docker stats                               # 资源占用
curl -s http://127.0.0.1:8000/ready        # 周期性健康探测
```

- 建议用 UptimeRobot 等对 `https://app.example.com/api`（或后端 `/ready`）做周期探活。
- 日志落盘：`docker compose logs` 走 journald/容器日志驱动，建议配 `json-file` 的 `max-size`/`max-file` 轮转，或接入 Loki/ELK。

## A9. 升级 / 回滚

```bash
cd /opt/omnixa
git pull
docker compose up -d --build               # 新迁移会自动由 migration 服务执行
docker compose logs migration | tail -20   # 确认升级成功
```

回滚：`git checkout <上个稳定 tag>` 后 `docker compose up -d --build`（迁移不自动降级，需要时手工 `docker compose run --rm migration /app/.venv/bin/alembic downgrade -1`）。

---

# 方案 B（轻量备选）：无 Docker 手工部署

> 适合无法安装 Docker 的场景。依赖 `backend/pyproject.toml` + `backend/uv.lock`（`uv` 冻结安装）、`backend/alembic` 迁移、`npm ci` 前端构建。需自建 systemd unit（下方给出示例）。

## B0. 前置

- Ubuntu 22.04/24.04，已装 `build-essential`、`git`、Node.js 22、`uv`、MySQL 8.x、Redis 7.x、nginx。
- 应用用户：`sudo useradd --system --create-home omnixa`，代码放 `/opt/omnixa`。

## B1. 安装 MySQL 8

```bash
sudo apt-get install -y mysql-server
sudo mysql_secure_installation
# 建库建号（与 docker-compose 的 utf8mb4 设置一致）
sudo mysql -e "CREATE DATABASE my_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'my_web'@'127.0.0.1' IDENTIFIED BY '<强随机hex>';
GRANT ALL ON my_web.* TO 'my_web'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

## B2. 安装 Redis 7（开启 AOF）

```bash
sudo apt-get install -y redis-server
# 编辑 /etc/redis/redis.conf：
#   appendonly yes
#   appendfsync everysec
#   bind 127.0.0.1
sudo systemctl enable --now redis-server
redis-cli ping   # 期望 PONG
```

> AOF 必须开启，否则 RQ 队列 / lease 状态重启即丢（见 `docs/dev-startup.md`）。

## B3. 安装 `uv` 并冻结安装后端依赖

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /opt/omnixa/backend
uv sync --frozen --no-dev       # 依据 uv.lock 精确安装到 .venv
```

## B4. 配置 `backend/.env` 并执行迁移

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env：
#   DATABASE_URL=mysql+pymysql://my_web:<密码>@127.0.0.1:3306/my_web
#   REDIS_URL=redis://127.0.0.1:6379/0
#   RAG_UPLOAD_DIR=./data/uploads
#   JWT_SECRET_KEY=<openssl rand -hex 32>
#   CORS_ORIGINS/TRUSTED_HOSTS 加入域名；LLM_*/EMBEDDING_*/VISION_* 按需
#   INVITE_REQUIRED=true / REFERRAL_*_CREDITS=0

cd backend
uv run alembic upgrade head        # 手工执行迁移（单头 d3e4f5a6b7c8）
```

## B5. Backend：uvicorn（systemd）

`/etc/systemd/system/omnixa-backend.service`：

```ini
[Unit]
Description=Omnixa Backend API
After=network.target mysql.service redis-server.service

[Service]
WorkingDirectory=/opt/omnixa/backend
ExecStart=/opt/omnixa/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
EnvironmentFile=/opt/omnixa/backend/.env
User=omnixa
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## B6. Worker：RQ 消费者 + dispatcher（systemd）

`/etc/systemd/system/omnixa-worker.service`：

```ini
[Unit]
Description=Omnixa Document Worker (RQ + dispatcher)
After=network.target mysql.service redis-server.service omnixa-backend.service

[Service]
WorkingDirectory=/opt/omnixa/backend
ExecStart=/opt/omnixa/backend/.venv/bin/python -m app.worker
EnvironmentFile=/opt/omnixa/backend/.env
User=omnixa
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now omnixa-backend omnixa-worker
sudo systemctl status omnixa-backend omnixa-worker
# worker 日志应出现 Listening on document-processing...
```

## B7. 前端构建 + nginx 托管

```bash
cd /opt/omnixa
npm ci
npm run build                       # VITE_API_BASE_URL 默认 /api（.env.production）
sudo mkdir -p /var/www/omnixa
sudo cp -r dist/* /var/www/omnixa/
```

## B8. nginx 反代 + HTTPS

> **注意**：`nginx.frontend.conf` 中的 `proxy_pass http://backend:8000/api/` 是 Docker 内部主机名，手工部署必须改为 `http://127.0.0.1:8000/api/`。

```nginx
# /etc/nginx/sites-available/omnixa
server {
    listen 80;
    server_name app.example.com;
    root /var/www/omnixa;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;          # SSE 流式响应
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        add_header X-Accel-Buffering no;
    }
    location / { try_files $uri $uri/ /index.html; }   # SPA history fallback
}
```

```bash
sudo ln -s /etc/nginx/sites-available/omnixa /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d app.example.com
```

## B9. 验证

```bash
curl -s http://127.0.0.1:8000/health   # {"status":"ok"}
curl -s http://127.0.0.1:8000/ready    # {"status":"ready",...}
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/   # 200
# 浏览器冒烟：注册（邀请码）→ 登录 → 建项目 → Chat 文本/图片 → Knowledge 上传 → RAG 提问
```

备份/恢复：直接使用 `docs/backup-restore.md` 的 `mysqldump` + `Compress-Archive`（或 `tar`）命令；维护脚本走 `cd backend && uv run python data/maintenance/backup.py`。

---

# 方案 A / B 落地判断

- **方案 A 可执行落地**：`docker-compose.yml`、`Dockerfile.backend`、`Dockerfile.frontend`、`nginx.frontend.conf`、`.dockerignore`、根 `.env.example`、`backend/.env.example`、`backend/uv.lock` 全部齐备；迁移由 `migration` 一次性服务执行，健康检查/重启策略已定义。唯一外部依赖是 Docker 与域名证书。RC1 阶段仅因「本机无 Docker」未跑 compose smoke（见 `docs/classroom-beta-rc1-report.md` §K），属环境缺失而非方案缺陷。
- **方案 B 可执行落地**：`uv sync --frozen` + `alembic upgrade head` + `python -m app.worker` + `npm run build` 均为已验证命令（CI 的 `migrations`/`backend` job 已用 uv + alembic 在 MySQL 上跑通）；需人工补 systemd unit（上文已给示例）并把 `nginx.frontend.conf` 的 `backend:8000` 改为 `127.0.0.1:8000`。
- **共同前置（任一方案都必须满足，否则无法 Go-Live）**：真实 `LLM_*` / `EMBEDDING_*` 凭据；视觉真实能力需 `VISION_*`/`TAOTOKEN_*` 密钥（真实冒烟已于 9/9 PASS，生产 `.env` 需提供，见 `docs/known-debt.md` D3）；`INVITE_REQUIRED=true` 且 `REFERRAL_*=0`。
