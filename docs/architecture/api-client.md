# Unified API Client

`packages/api-client` 是共享产品模块访问 Cloud API 与 Local Agent 的统一请求边界。

当前基线提供：

- 协议版本请求头；
- Bearer Token 注入入口；
- 超时和调用方取消；
- 只对 GET/HEAD 执行的有界重试；
- HTTP、网络、超时和取消错误到共享 `APIError` 的转换；
- 图谱、分页邻居、LOD/聚合投影、图内文献投影、桌面文献库查询/详情、视图保存/列表/恢复/删除，以及长任务创建、轮询、取消和结果引用入口；
- 固定路由 transport，用于离线开发和自动测试。

时间演化使用 `getGraphTimeline(timelineKey, query, signal)`，通过 `POST /v1/timelines/{timelineKey}/query` 一次取得时间事件、诊断和与当前 viewport 对应的图谱投影。调用方只能提供有界年份、viewport 和最多 50 个 pinned node ID；文件位置与算法选择不进入浏览器请求。

业务组件不得直接散落 `fetch`。图谱分页支持调用方取消；文献投影使用有大小上限的 JSON
POST，避免把大量节点 ID 放进 URL。上传、下载、SSE/WebSocket、缓存和刷新令牌将在对应
真实服务纵向切片出现时扩展，避免提前创建未被产品使用的抽象。

文献库使用 `queryLibrary(query, signal)` 与 `getLibraryRecord(recordId, signal)`。筛选、排序和
分页由 Local Agent 在桌面缓存上执行；响应只暴露 `downloaded` 与 `hasExtraction` 能力状态，
不向普通浏览器或 React 组件返回本地 PDF 路径。

集合与比较工作区使用 `getLibraryState` / `mutateLibraryState`。每个 mutation 携带
`expectedRevision`；409 冲突不自动重试，调用方应重新读取状态并提示用户。具体规则见
`sync-conflict-strategy.md`。

Cloud API 使用独立 `ApiClient` 实例和独立 token provider，不能复用 Local Agent 会话。账户、
数据控制、库同步、分享、审计、导出和删除均由统一客户端封装；浏览器访问令牌仅由当前标签页的
`sessionStorage` accessor 提供，不进入 URL、QWebChannel 或持久 fixture。`syncLibrary` 是唯一将
HTTP 409 作为 `LibrarySyncResult(status="conflict")` 返回的接口，其余 409 继续转换为
`ApiClientError`，并且 POST/PATCH/DELETE 不自动重试。

团队与权限使用 `listTeamMembers`、`createTeamInvite`、`acceptTeamInvite`、成员角色/删除方法，以及
`listResourcePermissions` / `setResourcePermission`。邀请 token 只在接受请求体中发送；资源路径参数
始终 URL 编码。业务页面不能根据角色自行推断服务端授权，UI 隐藏只是体验优化，Cloud API 每次
操作仍按 `cloud-permission-model.md` 重新检查租户和 ACL。

云图谱使用 `listCloudGraphs` / `syncCloudGraph`；读取图谱及视图继续复用既有 `getGraph` 和四个
saved-view 方法，因此业务图谱组件不区分 Local Agent 与 Cloud DTO。运行时数据源优先级为：嵌入式
Qt 页面使用 Local Agent；公网浏览器在已配置 Cloud API 时只使用 Cloud API；未配置 Cloud API 的
本地开发网页才可使用显式 Local Agent；fixture 只用于未配置真实服务的开发与自动测试。Cloud 同步 409 与文献库同步一样作为
显式业务冲突返回，其他 POST 仍不重试。普通浏览器没有 Local Agent 时只能读取已同步图谱，UI
不会允许把 fixture 演示图上传为真实云数据。

上述规则适用于全部业务页面，而不只适用于图谱。生产网页不得因 Cloud API 未登录、返回空数据或
请求失败而回退到 Local Agent/fixture。`tenantId` 只用于响应展示和诊断关联；API Client 不得把它
作为数据范围选择器，数据范围始终由 Cloud API 根据 Bearer 会话确定。桌面本地读取则不依赖云端
账户，只有用户明确发起同步时才跨越 Local Agent 与 Cloud API 的边界。

Cloud 长任务继续复用 `createTask`、`getTask`、`cancelTask` 和 `getTaskResult`，因此页面不需要第二套
任务协议。`getCloudMetrics` 读取当前租户的管理指标；服务端只允许 Owner/Admin，客户端角色判断仅
用于避免无意义请求。账户页以可取消的短轮询读取权威状态，SSE/WebSocket 留作后续传输优化，不能
取代持久任务 GET 接口。具体并发、恢复和日志脱敏边界见 `cloud-observability.md`。

图谱协作使用 `getCollaborationSnapshot`、`mutateCollaboration`、`getCollaborationEvents` 和
`streamCollaborationEvents`。SSE 由统一客户端的 fetch 流解析，以便在 Authorization header 中发送
Cloud 会话而不把 token 放入 URL；支持 Last-Event-ID、调用方取消、reset 帧和有界超时。页面遇到
409 不自动重试写入，而是重新读取快照。完整策略见 `graph-collaboration.md`。
