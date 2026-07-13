# Cloud 长任务与可观测性基线

本文记录 Phase 2 Cloud API 参考服务已经实现的长任务、指标、日志和重启恢复边界。它是可运行、可测试的服务基线，不代表生产托管或异地灾难恢复已经完成。本地加密备份与离线恢复见 `cloud-backup-recovery.md`。

## 任务协议

Cloud API 与 Local Agent 复用共享 `Task` DTO 和同一组客户端方法：

- `POST /v1/tasks`：创建任务；
- `GET /v1/tasks/{taskId}`：读取权威状态；
- `POST /v1/tasks/{taskId}:cancel`：请求取消；
- `GET /v1/tasks/{taskId}/result`：仅在成功后读取结果。

当前 Cloud API 只接受 `graph.audit`，输入只能包含一个最长 256 字符的 `recordId`。服务在入队前重新检查同租户 graph viewer ACL；任务和结果读取也始终附带租户条件，不依赖前端隐藏按钮。

状态使用 `queued`、`running`、`stopping`、`succeeded`、`failed` 和 `cancelled`。进度、消息、开始/结束时间、受控错误和结果引用均持久化到 SQLite。审计结果使用租户服务密钥进行 AES-GCM 加密；任务元数据不保存整份图谱或敏感正文。

## 有界执行与恢复

参考默认值为两个 worker、全服务最多 32 个 active 任务、单租户最多 16 个 active 任务、单任务五分钟超时。队列满返回可重试的 HTTP 503；不允许调用方提交任意函数、命令或路径。

取消先持久化 `stopping`/`cancelled`，再向 worker 发出信号，避免 worker 启动竞态留下永久 `stopping`。正常服务关停会取消排队任务并等待运行任务安全结束。进程异常退出后，下一次启动把遗留的 `queued`、`running` 或 `stopping` 明确标记为 `failed/service_restarted`，不会伪装为继续运行或成功。

当前恢复策略是“明确失败后由用户重新提交”，不是断点续算。任务结果没有保留期清理器；后续应结合 `retainCloudTaskData`、备份策略和数据治理定义生命周期。

## 指标与日志

`GET /v1/metrics` 仅允许当前租户 Owner/Admin 访问，返回服务运行时间、租户用户数、云图谱数、按状态任务数和审计事件数。它不返回其他租户统计、令牌、邮箱、图谱正文或数据库路径。

HTTP 完成日志是单行 JSON，包含 event、requestId、method、模板化 route、status 和 elapsedMs。公开分享 token、shareId、recordId、nodeId、viewId、taskId、memberId 与 ACL resourceId 都不会以原始路径值写入日志；请求体、Authorization、密码和研究内容不记录。

独立运维抓取面 `GET /internal/metrics` 只在配置至少 32 字符的
`OMNILIT_CLOUD_METRICS_TOKEN`（或 `_FILE` secret）后启用。它使用与 Cloud 用户会话完全分离的
Bearer 凭据，并仅输出模板化 route 的请求计数/状态/直方图、in-flight 请求、readiness、协作流容量、
备份启用状态、最近成功/失败时间和连续失败数。它不包含 tenantId、用户、资源 ID、路径、正文或凭据。
未配置时返回 404，错误运维凭据返回 401。

`deploy/compose.yaml --profile monitoring` 可在私有 Compose 网络启动 Prometheus；抓取凭据来自独立
Docker secret。Nginx 对 `/internal/` 固定返回 404，因此公网 Web origin 不会反向代理运维指标。
规则覆盖目标不可用、服务未就绪、5xx 比例、p95 延迟、备份失败/陈旧和协作流容量。规则和 Prometheus
配置在 CI 中由 `promtool` 校验。Prometheus 仅绑定宿主 loopback；正式环境仍需配置持久化监控平台、
外部通知接收器、值班路由、静默/升级政策和 SLO。

## Web 使用方式

账户页的 `CloudTaskPanel` 通过统一 API Client 创建、轮询、取消并读取结果。轮询使用 AbortController 和可清理定时器；组件卸载或任务状态变化时会终止旧请求。Owner/Admin 同页读取租户指标，Member 不发起指标请求。

当前选择短轮询是为了保持 HTTP 合同简单、可在 Qt WebEngine 和普通浏览器中一致运行。SSE 或 WebSocket 是后续优化，不能替代服务端持久状态、租户授权和可恢复的 GET 接口。

## 尚未完成

- 自动异地复制、恢复演练编排、跨区域灾难恢复和迁移失败回滚；
- 任务结果保留期、配额计费和数据删除计划；
- 实际外部告警投递、集中日志、分布式追踪、生产 SLO 和值班流程；
- 全局 presence、字符级 CRDT 和跨工作空间实时协作；图谱批注已经使用有界 SSE；
- 生产部署、密钥轮换、签名、公证和自动发布。
