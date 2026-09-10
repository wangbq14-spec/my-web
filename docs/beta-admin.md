# Omnixa Classroom Beta 管理员手册

本文档面向 Beta 管理员，覆盖日常运营操作：邀请码、用户、补积分、充值审核、反馈、统计、备份恢复与排障。

## 1. 登录与运营中心

- 使用管理员账号登录后，侧边栏会出现「运营中心」（普通用户不可见；直接访问 `/admin` 会被拒绝）。
- 运营中心模块：Overview、用户、充值审核、Feedback、Analytics、邀请码、附件清理。

## 2. 邀请码管理

- **创建**：填写 channel（Beta 默认 `classroom`）、最大使用次数、可选过期时间。邀请码由系统生成。
- **关闭**：点击「停用」后该码立即失效（已注册用户不受影响）。
- 查看使用情况：每个邀请码显示 used / max 与过期时间。
- 命令行查看：
  ```sql
  SELECT code, channel, used_count, max_uses, is_active, expires_at FROM invite_codes;
  ```

## 3. 用户管理

- 搜索用户；查看活跃状态、余额、注册时间。
- 用户详情：用量记录、积分流水（ledger）、反馈、充值申请。
- **补积分（Grant Credits）**：填写金额与原因，系统会写入 ledger 并带 request_id，幂等（重复提交同一原因不会重复到账）。

## 4. 充值审核

- 「充值审核」默认列出待审核申请；每行显示用户、套餐、金额、Credits、申请时间。
- **批准**：点击「批准」→「确认批准」两步入库；走服务端事务（申请单 → 积分流水 → 钱包入账）。
- 重复/并发批准会被拒绝（409）；批准后不能取消，拒绝后不能反悔。
- 到账前请先确认真实收款（Beta 人工流程）。

## 5. 反馈处理

- Feedback 页列出所有反馈（问题/建议/其他），可按状态筛选。
- 可将反馈标记为「已处理（reviewed）」或「关闭（closed）」。

## 6. Analytics

- Overview 显示今日指标与近 7 天趋势；Analytics 页可按 7d / 30d / all 查看使用统计。
- 非法的时间范围参数会返回 422。

## 7. 备份与恢复

### 备份（逻辑备份：schema + 数据 + 上传文件）

在 `backend/` 目录执行：

```powershell
$env:UV_CACHE_DIR='...\backend\.uv-cache'
uv run python data/maintenance/backup.py
```

输出到 `data/maintenance/backups/`（schema.sql、data.json、uploads.zip、manifest.json）。可用 `--out` 指定目录。

### 恢复（恢复到新库 `<db>_restore`，需要 `--yes`）

```powershell
uv run python data/maintenance/restore.py --yes
```

恢复后建议做外键完整性检查：

```powershell
uv run python data/maintenance/check_fk_integrity.py
```

> 恢复不会覆盖当前生产库，而是写入 `<db>_restore`；确认无误后再切换。

### 数据快照与重启后检查

```powershell
uv run python data/maintenance/persistence_snapshot.py   # 各表计数快照
uv run python data/maintenance/persistence_api_check.py  # 重启后 API 级检查
```

## 8. 排障：request_id

所有 API 响应头与错误体里都带 `request_id`（日志里同名字段）。查问题：

- 后端日志（`%LOCALAPPDATA%\omnixa-dev-tools\logs\api-*.log`）按 `request_id` 过滤：
  ```powershell
  Select-String -Path "$env:LOCALAPPDATA\omnixa-dev-tools\logs\api-mock5.out.log" -Pattern "你的request_id"
  ```
- 常见错误码：
  - `RATE_LIMITED` (429)：请求太频繁，稍后再试（auth 10/分钟，chat 30/分钟）。
  - 409：重复操作（重复批准充值、重复注册等）。
  - 402：积分不足。
  - 415/413：图片或文件格式/大小不符。

## 9. Worker 与文档处理

- 文档异步处理由 worker 进程执行；处理中超过租约（默认 300s）会被调度器回收重试。
- 文档状态：queued → processing → ready / failed；failed 可在前端「重新处理」或调用 retry 接口。

## 10. 注意事项

- Beta 阶段不支持自动支付；未配置收款码时用户端会提示「暂未开放扫码充值」。
- 请勿在前端或日志中放置任何 API 密钥；密钥只存在于 `backend/.env`（已被 gitignore）。
- 所有关键写入（注册赠积分、充值到账、补积分）均通过 Billing Service 记账，带 request_id 幂等。
