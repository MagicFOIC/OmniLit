# 图谱团队批注与实时协作基线

本切片为已经同步到 Cloud API 的单篇图谱提供团队批注。共享 React 图谱在普通浏览器和 Qt WebEngine 中使用同一 DTO、统一 API Client 和相同 Cloud 权限，不通过 QWebChannel 传输高频事件。

## 数据与权限边界

批注可以绑定整个图谱、节点或关系。正文最多 4,000 字符；单图最多 500 条有效批注。服务端在写入前确认目标仍存在于当前 Cloud Graph，正文、当前批注和操作事件均使用租户服务密钥 AES-GCM 加密。

读取快照或事件要求 graph viewer；新增、更新或删除要求 graph editor。非 Owner 还必须满足 Owner 的 `allowTeamAccess`。新增和更新额外要求 Owner 启用 `syncAnnotations`；关闭后仍允许读取和删除既有云数据，避免隐私开关阻碍数据清理。Cloud API 每次 snapshot、mutation 和事件流重连都重新检查租户与 ACL。

## revision、幂等与冲突

每个图谱具有独立、单调递增的 collaboration revision。Mutation 携带 `baseRevision`、UUID `clientMutationId`、action 和目标参数。服务先检查 mutation ID：成功请求的网络重放直接返回原事件；不同 mutation 的陈旧版本返回 HTTP 409 `collaboration_conflict`，不执行最后写入者覆盖。React 面板收到冲突后重新读取权威快照，并要求用户重新提交。

本基线使用对象级乐观并发，不进行字符级 CRDT 合并。不同成员同时修改时保留明确冲突，适合短研究批注；富文本、离线 outbox 和长文档协作需要后续独立协议。

## 快照、事件与 SSE

- `GET /v1/graphs/{recordId}/collaboration`：当前 revision、权限能力和有效批注；
- `POST /v1/graphs/{recordId}/collaboration`：幂等 mutation；
- `GET /v1/graphs/{recordId}/collaboration/events`：最多 200 条恢复事件；
- `GET /v1/graphs/{recordId}/collaboration/events/stream`：带认证的 SSE 长轮询。

API Client 使用 fetch 流而非 EventSource，因此 Bearer Token 不进入 URL。订阅携带 `Last-Event-ID`，单连接最多等待 25 秒；Cloud HTTP 服务默认最多 64 个并发等待流。客户端心跳后重连，临时错误一秒退避，组件卸载时取消流、重试 timer 和 mutation。

每图保留最近 10,000 个事件。客户端落后于最早事件时服务发送 reset 帧，面板重新读取快照，不从不完整日志推断状态。事件日志不是数据库备份，仍由 Cloud 加密备份覆盖。

## 删除和导出

删除批注会在同一事务中把当前行替换为无正文 tombstone、从历史 upsert 事件移除正文、写入无正文 delete 事件并增加 revision。账户导出只包含仍有效批注；Owner 删除租户时外键级联清理协作表。HTTP 日志不记录正文、recordId、targetId 或访问令牌。

## 桌面与网页行为

只有配置真实 Cloud API 的单图数据源声明 collaboration。桌面嵌入式 React 可以从 Local Agent 读取图谱，同时通过独立 Cloud Client 订阅已同步图谱批注；两种 token 不混用。fixture 模式不显示虚假协作，时间演化聚合图也不显示单篇批注。

## 已知限制和回退

当前不包含 presence、光标、字符级 CRDT、离线 outbox、附件、富文本、@mention、推送通知或多图工作空间协作。生产代理仍需关闭该路由缓冲并配置连接/空闲超时。

回退时移除 Collaboration DTO、三张表及路由、API Client 方法和 `CollaborationPanel`。Cloud Graph、视图、ACL、任务、备份、Local Agent 与 QML 图谱无需回滚。
