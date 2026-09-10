# Omnixa 备份与恢复（Beta 最小可执行方案）

> 目标不是高级灾备。目标是：**Beta 数据真丢了，我知道怎么恢复。**
> Omnixa 的持久化数据只有两类：MySQL 数据库 + `backend/data/uploads`（RAG 文档 + 聊天图片）。

## 需要备份什么

| 数据 | 位置 | 内容 |
| --- | --- | --- |
| 数据库 | MySQL `my_web` 库 | 用户 / 项目 / 会话 / 消息 / 附件元数据 / 文档 / chunks / 钱包 / 账本 / 用量 / 充值 / 反馈 / 邀请码 / workflow |
| 上传文件 | `backend/data/uploads/` | RAG 原始文档（`.txt/.md/.pdf`，UUID 命名）+ `chat_attachments/{user_id}/` 聊天图片（UUID 命名） |

> 注意：向量 chunks 存在 MySQL 里（`document_chunks` 表 + 向量存储），因此备份 MySQL + uploads 即可完整恢复。

## 备份

### 1. 备份 MySQL

```bash
# 开发环境（Windows PowerShell，mysqldump 需在 PATH 或使用完整路径）
mysqldump -h 127.0.0.1 -P 3306 -u root -p my_web \
  --single-transaction --routines --triggers \
  > backup/my_web_$(date +%Y%m%d_%H%M%S).sql
```

- 数据库连接参数从 `backend/.env` 的 `DATABASE_URL` 读取（`mysql+pymysql://USER:PASSWORD@HOST:PORT/DB`）。
- `--single-transaction`：InnoDB 一致性快照，备份期间不锁表。
- Windows 若 `mysqldump` 不在 PATH，用完整路径（如 `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe`）。

### 2. 备份上传文件

```bash
# Windows PowerShell
Compress-Archive -Path backend\data\uploads -DestinationPath backup\uploads_$(Get-Date -Format yyyyMMdd_HHmmss).zip
```

## 一键备份脚本

`scripts/backup.ps1`（Windows 开发环境）：

```powershell
.\scripts\backup.ps1
```

脚本会：解析 `backend/.env` 的 `DATABASE_URL` → 执行 mysqldump → 压缩 uploads → 输出到 `backup/` 目录。

## 恢复

### 前置：停止写入

恢复前停止 backend / worker（避免恢复期间写入）：

```powershell
# 停止 uvicorn 与 worker 进程，或
docker compose stop backend worker   # 若使用 Docker
```

### 1. 恢复 MySQL

```bash
# 用备份覆盖 my_web 库（会清空现有数据，请先确认）
mysql -h 127.0.0.1 -P 3306 -u root -p -e "DROP DATABASE IF EXISTS my_web; CREATE DATABASE my_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -h 127.0.0.1 -P 3306 -u root -p my_web < backup/my_web_XXXX.sql
```

### 2. 恢复上传文件

```powershell
# 解压覆盖
Expand-Archive -Path backup\uploads_XXXX.zip -DestinationPath backend\data -Force
```

### 3. 迁移与启动

```bash
cd backend
uv run python -m alembic upgrade head   # 确认 schema 对齐
# 重启 backend + worker
```

## 验证恢复成功

```powershell
# 1. 实体数量应与备份时一致
uv run python data/maintenance/count_entities.py
# 2. 抽查一个文档可读、一张图片可访问
```

## 定时备份（可选，最小 cron 示例）

```bash
# Linux crontab：每天 03:00 备份
0 3 * * * cd /path/to/omnixa && ./scripts/backup.sh >> backup/backup.log 2>&1
```

## 注意事项

- **恢复是破坏性操作**（DROP DATABASE），执行前二次确认备份文件完整（`.sql` 非空、末尾有 `-- Dump completed`）。
- **Redis 不备份**：Redis 只存 RQ 任务队列（临时）+ 可能的缓存。文档处理由 MySQL 的 `next_retry_at`/`processing_lease_expires_at` 驱动，Redis 重启后 dispatcher 会从 MySQL 重新入队。
- **向量无需单独备份**：向量存在 MySQL 的向量存储表里，随 MySQL 备份。
- 生产（Docker）备份：`docker compose exec mysql mysqldump ...`，或挂载 `backup/` 卷到宿主机。
