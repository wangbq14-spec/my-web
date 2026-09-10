# Omnixa V1 环境变量全量清单（env）

> 来源：`backend/app/core/config.py`（Pydantic Settings，默认值 + 校验）、`backend/.env.example`、根 `.env.example`、`docker-compose.yml`。
> 说明：本清单**只列变量名、必填/可选、用途与生产建议方向，绝不写真实 secret 值**。
>
> 分层：
> - **根 `.env`**（Compose 基础设施）：被 `docker-compose.yml` 的 `${VAR}` 替换与 `env_file:` 使用。
> - **`backend/.env`**（应用变量）：被 `config.py` 读取（`env_file=backend/.env`），gitignored。
> - **覆盖关系**：`docker-compose.yml` 中 `backend`/`worker`/`migration` 的 `environment:` 会**覆盖** `backend/.env` 里的 `DATABASE_URL`、`REDIS_URL`、`RAG_UPLOAD_DIR`（容器内指向 `mysql:3306` / `redis:6379` / `/app/data/uploads`）。

---

## 1. 根 `.env`（Compose 基础设施，来自根 `.env.example`）

| 变量名 | 必填 | 用途 | 生产建议方向 |
| --- | --- | --- | --- |
| `MYSQL_DATABASE` | 必填 | MySQL 库名 | `my_web`（保持默认） |
| `MYSQL_USER` | 必填 | MySQL 应用账号 | `my_web`（不要用 root） |
| `MYSQL_PASSWORD` | **必填** | 应用账号密码 | 强随机 hex（避免 URL 特殊字符） |
| `MYSQL_ROOT_PASSWORD` | **必填** | root 密码 | 强随机 hex，与上面不同 |
| `BACKEND_PORT` | 可选 | 宿主机后端端口（`${BACKEND_PORT:-8000}`） | `8000`，不对公网开放 |
| `FRONTEND_PORT` | 可选 | 宿主机前端端口（`${FRONTEND_PORT:-8080}`） | `8080`，不对公网开放 |
| `VITE_API_BASE_URL` | 可选 | 前端 API 基路径（构建期注入） | `/api`（同源反代，勿改） |
| `VITE_API_TIMEOUT` | 可选 | 前端 axios 超时（ms） | `10000` |

---

## 2. `backend/.env`（应用变量，来自 `backend/.env.example` + `config.py`）

### 2.1 应用 / 调试 / 日志

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `APP_NAME` | 可选 | `my-web-backend` | FastAPI title | 保持默认 |
| `DEBUG` | 可选 | `false` | 调试模式 | **必须 `false`** |
| `LOG_LEVEL` | 可选 | `INFO` | 日志级别 | `INFO`（排障临时 `DEBUG`） |
| `RATE_LIMIT_GENERAL` | 可选 | `120` | 通用接口限流（次/分钟） | 按需，勿盲目调大 |
| `RATE_LIMIT_AUTH` | 可选 | `10` | 认证接口限流 | 保持 `10`（防爆破） |
| `RATE_LIMIT_CHAT` | 可选 | `30` | Chat 限流（次/分钟） | 保持 `30`（dev 曾放宽到 5000，勿带入生产） |
| `RATE_LIMIT_FEEDBACK` | 可选 | `10` | 反馈接口限流 | 保持默认 |
| `DB_POOL_SIZE` | 可选 | `5` | SQLAlchemy 连接池大小 | 生产可 `10`（RC1 验证 10+20 更稳） |
| `DB_MAX_OVERFLOW` | 可选 | `10` | 连接池溢出上限 | 生产可 `20` |
| `DB_POOL_RECYCLE` | 可选 | `1800` | 连接回收秒数 | 保持默认 |

### 2.2 数据库 / Redis

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `DATABASE_URL` | **必填**（非空校验） | — | MySQL 连接串（`mysql+pymysql://user:pass@host:port/db`） | 生产指向 MySQL 8.x；**密码避免 `@:/` 等未编码字符** |
| `REDIS_URL` | 生产必填 | `""`（API 进程可选） | Redis 连接串（RQ 队列 + lease） | `redis://redis:6379/0`（Compose）或 `redis://127.0.0.1:6379/0`（手工）；文档处理**必须配置** |

> 说明：`REDIS_URL` 对 API 进程「故意可选」（仅在派发任务时惰性打开）；但 `worker` 依赖它消费队列，生产必须配置。

### 2.3 认证 / JWT

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `JWT_SECRET_KEY` | **必填**（非空校验） | — | JWT 签名密钥 | `openssl rand -hex 32`，严禁示例值/进 git |
| `JWT_ALGORITHM` | 可选 | `HS256` | JWT 算法 | 保持默认 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 可选 | `30` | Access Token 有效期（分钟） | 按需（30 可接受） |

### 2.4 CORS / 可信主机

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `CORS_ORIGINS` | 必改 | `["http://127.0.0.1:5173","http://localhost:5173"]` | 允许跨域来源（JSON 数组） | 生产改为 `["https://app.example.com"]`；**严禁 `*` + 凭据同开** |
| `TRUSTED_HOSTS` | 必改 | `["127.0.0.1","localhost","testserver"]` | TrustedHost 中间件白名单 | 加入生产域名，否则域名访问 400 |

### 2.5 LLM（OpenAI-compatible 提供方）

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `LLM_API_KEY` | 真实模式必填 | `""` | 文本 LLM 密钥 | 只存 `backend/.env` |
| `LLM_BASE_URL` | 真实模式必填 | `""` | LLM 端点 | 提供方 base URL |
| `LLM_MODEL` | 真实模式必填 | `""` | 默认模型 | 提供方模型名 |
| `LLM_FAST_MODEL` | 可选 | `""` | 「快速」档位模型 | 按档位配置 |
| `LLM_STANDARD_MODEL` | 可选 | `""` | 「均衡」档位模型 | 按档位配置 |
| `LLM_REASONING_MODEL` | 可选 | `""` | 「深度思考」档位模型 | 按档位配置 |
| `LLM_PROVIDER_LABEL` | 可选 | `openai_compatible` | 提供方标签（`openai_compatible` / `mock`） | 生产 `openai_compatible`；`mock` 仅离线 E2E/容量 |
| `LLM_TIMEOUT` | 可选 | `30` | LLM 请求超时（秒） | 按需 |
| `AGENT_MAX_STEPS` | 可选 | `6` | Agent 最大步数 | 保持默认 |

### 2.6 Embedding（向量化）

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `EMBEDDING_API_KEY` | RAG 必填 | `""` | Embedding 密钥 | 只存 `backend/.env` |
| `EMBEDDING_BASE_URL` | RAG 必填 | `""` | Embedding 端点 | 提供方 base URL |
| `EMBEDDING_MODEL` | RAG 必填 | `""` | Embedding 模型 | 提供方模型名 |
| `EMBEDDING_TIMEOUT` | 可选 | `30` | Embedding 超时（秒） | 保持默认 |

### 2.7 Vision（图片理解，二选一来源）

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `VISION_MODEL` | 来源 A 必填 | `""` | OpenAI-compatible 视觉模型 | 如 SiliconFlow 视觉模型 |
| `VISION_MODEL_TIER` | 可选 | `standard` | 视觉计费档位 | `standard`；**绝不可跨档位**（代码注释强调） |
| `VISION_API_KEY` | 来源 A 必填 | `""` | 视觉端点密钥 | 只存 `backend/.env` |
| `VISION_BASE_URL` | 来源 A 必填 | `""` | 视觉端点 | 提供方 base URL |
| `VISION_BASE_CREDIT_COST` | 可选 | `0` | 提供方报无可用图片 token 时的保底扣费 | 按定价策略 |
| `VISION_TIMEOUT` | 可选 | `180` | 视觉超时（秒） | 视觉首 token 慢，保持较长时间 |
| `TAOTOKEN_API_KEY` | 来源 B 必填 | `""` | Taotoken 密钥 | 只存 `backend/.env` |
| `TAOTOKEN_BASE_URL` | 来源 B 必填 | `""` | Taotoken 端点 | 提供方 base URL |
| `TAOTOKEN_VISION_MODEL` | 来源 B 必填 | `""` | Taotoken 视觉模型（如 `kimi-k3`） | 见 `/models` 的 `supported_modalities` |

### 2.8 RAG / 上传

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `RAG_UPLOAD_DIR` | 可选 | `backend/data/uploads`（Compose 覆盖为 `/app/data/uploads`） | 上传文件目录 | 持久卷挂载点 |
| `RAG_MAX_UPLOAD_BYTES` | 可选 | `10485760`（10MB） | 文档上传大小上限 | 保持 10MB |
| `RAG_CHUNK_SIZE` | 可选 | `1000` | 分块大小 | 保持默认 |
| `RAG_CHUNK_OVERLAP` | 可选 | `150` | 分块重叠 | 保持默认 |
| `RAG_MAX_CONTEXT_CHARS` | 可选 | `12000` | 检索上下文上限 | 按需 |

### 2.9 Workflow / 文档异步处理

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `WORKFLOW_MAX_STEP_ATTEMPTS` | 可选 | `3` | Workflow 步骤重试上限 | 保持默认 |
| `DOCUMENT_TASK_QUEUE` | 可选 | `document-processing` | RQ 队列名 | 保持默认（worker 与 API 必须一致） |
| `DOCUMENT_TASK_MAX_RETRIES` | 可选 | `5` | 文档处理最大重试 | 保持默认 |
| `DOCUMENT_TASK_RETRY_BASE_SECONDS` | 可选 | `60` | 重试退避基数 | 保持默认 |
| `DOCUMENT_TASK_RETRY_MAX_SECONDS` | 可选 | `3600` | 重试退避上限 | 保持默认 |
| `DOCUMENT_TASK_LEASE_SECONDS` | 可选 | `300` | 处理租约（超时回收） | 保持默认 |
| `DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS` | 可选 | `5` | dispatcher 轮询间隔 | 保持默认 |

### 2.10 积分 / 计费（Credits & Billing）

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `CREDIT_GRANT_ON_REGISTER` | 可选 | `1000` | （遗留）注册赠积分 | **已无调用方**（实际生效的是 `BETA_REGISTER_CREDITS`），见 `docs/known-debt.md` |
| `CREDIT_INPUT_RATE` | 可选 | `1` | 输入 token 计费率 | 按定价策略 |
| `CREDIT_OUTPUT_RATE` | 可选 | `2` | 输出 token 计费率 | 按定价策略 |
| `CUSTOM_RECHARGE_ENABLED` | 可选 | `true` | 自定义金额充值开关 | Beta 保持 `true`（人工审核） |
| `CREDIT_PER_CNY` | 可选 | `300` | 每 CNY 兑换积分（Decimal，服务端计价） | 按定价策略，**勿用 float** |
| `CUSTOM_RECHARGE_MIN_CNY` | 可选 | `1` | 自定义充值最小金额 | 按需 |
| `CUSTOM_RECHARGE_MAX_CNY` | 可选 | `500` | 自定义充值最大金额 | 按需 |
| `CUSTOM_RECHARGE_STEP_CNY` | 可选 | `1` | 充值步进 | 按需 |
| `RECHARGE_PRICING_VERSION` | 可选 | `v1` | 定价版本号 | 变更价格时递增 |

### 2.11 Classroom Beta 门禁 / Referral

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `INVITE_REQUIRED` | **生产必填** | `true` | 注册是否强制要求邀请码 | **生产必须 `true`**（关闭自助注册刷积分 P0） |
| `BETA_REGISTER_CREDITS` | 可选 | `2000` | Classroom Beta 注册赠送积分 | 按活动策略 |
| `REFERRAL_REWARD_CREDITS` | 可选 | `0` | 邀请人奖励 | **保持 `0`**（无 IP/设备指纹，防自拉自刷） |
| `REFERRAL_NEW_USER_CREDITS` | 可选 | `0` | 被邀请新用户奖励 | **保持 `0`** |

### 2.12 聊天图片限制（config.py 定义，`.env.example` 未列，可选）

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `MAX_CHAT_IMAGE_SIZE` | 可选 | `10MB` | 单张聊天图片大小上限 | 保持默认 |
| `MAX_CHAT_IMAGES_PER_MESSAGE` | 可选 | `4` | 单条消息图片数上限 | 保持默认 |
| `MAX_CHAT_IMAGES_PER_CONVERSATION` | 可选 | `4` | 单会话图片数上限 | 保持默认 |
| `MAX_CHAT_IMAGE_BASE64_SIZE` | 可选 | `14MB` | 图片 base64 上限 | 保持默认 |

### 2.13 Analytics / 支付展示

| 变量名 | 必填 | 默认值 | 用途 | 生产建议方向 |
| --- | --- | --- | --- | --- |
| `ANALYTICS_ACTIVE_DAYS` | 可选 | `7` | 活跃用户统计窗口 | 保持默认 |
| `PAYMENT_QR_IMAGE_URL` | 可选 | `""` | 收款码图片 URL | 未配置时前端明示「暂未开放扫码充值」；配置后仍走人工审核 |

---

## 3. 前端构建变量（`VITE_*`）

| 变量名 | 来源文件 | 用途 | 生产建议方向 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | `.env.production`（默认 `/api`）；Docker 构建参数注入 | 前端请求 API 的基路径 | `/api`（同源反代） |
| `VITE_API_TIMEOUT` | `.env.production`（默认 `10000`） | 前端 axios 超时（ms） | `10000` |

> 前端只应暴露 `VITE_*`（非敏感）；**严禁**把任何 API Key 写进前端构建变量（AGENTS.md 安全红线）。

---

## 4. Go-Live 最小必填速查

| 层 | 必须设置/核对 |
| --- | --- |
| 根 `.env` | `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`（强随机且不同）；其余用默认 |
| `backend/.env` | `JWT_SECRET_KEY`（强随机）；`CORS_ORIGINS`/`TRUSTED_HOSTS`（加域名）；`LLM_*`+`EMBEDDING_*`（真实凭据，或 `LLM_PROVIDER_LABEL=mock` 仅演示）；`INVITE_REQUIRED=true`；`REFERRAL_*_CREDITS=0`；视觉 `VISION_*`/`TAOTOKEN_*`（真实视觉能力前置） |
| 覆盖项 | 容器内 `DATABASE_URL`/`REDIS_URL`/`RAG_UPLOAD_DIR` 由 `docker-compose.yml` 注入，无需在 `backend/.env` 填真实主机名 |

---

## 5. 安全注意事项

- 所有 secret（`JWT_SECRET_KEY`、`LLM_API_KEY`、`EMBEDDING_API_KEY`、`VISION_API_KEY`、`TAOTOKEN_API_KEY`、DB 密码）**只放 `backend/.env` 与根 `.env`**，两者均已 gitignore（`.gitignore` 含 `.env`、`backend/.env`）。
- `backend/data/`、`backup/`、`.env.classroom-e2e` 亦 gitignore，上传文件与备份不进入版本库。
- 日志/异常/前端一律不打印密钥（`docs/dev-startup.md` §环境变量安全）。
