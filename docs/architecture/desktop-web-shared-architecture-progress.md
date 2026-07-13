# OmniLit 桌面与网页共享架构第二阶段进度

本文件记录 `desktop-web-shared-architecture-phase-2.md` 的可独立验收纵向切片。

## 当前阶段

`knowledge-graph-completion-audit.md` 已证明第一阶段的产品、工程和稳定性进入条件。
第二阶段从阶段 B“抽取共享协议”开始；不进行全量目录重排，也不改变当前 QML 主界面。

## 本轮交付：共享图谱协议 v1

验收目标：Graph DTO 具有唯一权威定义，Python 与 TypeScript 使用同一来源，固定数据
可以验证，不支持的协议版本产生明确错误，现有 QML 图谱继续运行。

已完成：

- 新增 `@omnilit/shared-schema`，以 JSON Schema 2020-12 作为权威协议。
- 定义 GraphData、GraphNode、GraphEdge、GraphEvidence、Paper、GraphViewState、Task、
  TaskProgress 和 APIError 的第一版跨语言 DTO。
- 协议显式携带 `protocolVersion` 和 `schemaVersion`；拒绝未知主版本与图谱版本，
  同时允许同版本未知字段以支持渐进扩展。
- 由一个确定性生成器同时生成 TypeScript 接口和 Python TypedDict，`--check` 可阻止
  手写类型漂移。
- 新增 Python 兼容适配层，在共享 GraphData 与既有 `KnowledgeGraphDocument` 之间往返；
  原 QML 使用的 `recordId`、nodes、edges、evidence 和 details 结构保持不变。
- 新增固定共享图谱夹具及契约测试，覆盖 JSON Schema 验证、未知字段容忍、版本错误、
  代码生成一致性和 QML 兼容往返。

回退方式：删除新增的 `packages/shared-schema`、代码生成器、共享协议适配层及对应测试即可；
现有 QML 和知识图谱构建链路没有被替换。

下一轮最高优先级：完成阶段 C 的最小可运行 Web 壳，包括统一设计令牌、API Client、
Browser/Mock Platform Bridge 和不依赖 Qt 的固定图谱数据入口。

## 本轮交付：独立 Web 产品壳

验收目标：React 应用不启动 Qt、不连接真实后端也能在普通浏览器独立运行，并通过统一
API Client、Platform Bridge、共享协议和设计令牌展示固定 GraphData。

已完成：

- 建立 npm workspace 和 `apps/web`，使用 React、TypeScript、Vite 与基础路由。
- 建立 `packages/design-tokens`，直接迁移 QML `scholar_light` 的浅色、深色、间距、圆角、
  动效和响应式布局规则，并支持系统深色模式与减少动效设置。
- 建立 `packages/api-client`，提供协议版本、认证注入、超时、取消、有界安全重试、共享错误
  转换、图谱/任务入口以及固定数据 transport。
- 建立 `packages/platform-bridge`，实现 Browser 和 Mock Bridge；浏览器不支持的桌面能力
  返回明确错误或降级状态，外链仅允许 HTTP/HTTPS。
- `/graph` 通过 API Client 读取共享包内固定 GraphData，具备加载、空白、错误和成功状态；
  `/library` 与 `/about` 验证基础路由与渐进迁移边界。
- 添加严格 CSP、语义化导航、键盘可访问链接、深浅色与减少动效响应。
- 建立 Vitest、TypeScript 和 Vite 门禁，并提交 npm lockfile 以固定依赖解析。

验证：

- `npm run phase2:web:check`：代码生成检查、严格类型检查、6 项测试和生产构建全部通过。
- 生产构建 JS 238.95 kB，gzip 77.53 kB；CSS 5.71 kB，gzip 1.93 kB。
- 应用内真实浏览器验证 `/graph`、`/library`、`/about`；页面有内容、无 Vite 错误覆盖层、
  无控制台错误或警告，固定图谱显示 2 个节点和 1 条关系。

桌面端影响：无。现有 QML 仍是正式桌面产品入口，没有引入 Qt WebEngine。

回退方式：删除根 npm workspace、`apps/web`、`packages/api-client`、
`packages/platform-bridge` 和 `packages/design-tokens` 即可；Python/QML 链路不依赖它们。

下一轮最高优先级：阶段 D 的第一个知识图谱纵向切片——建立共享图谱状态、渲染器接口和
可交互画布，先完成固定 GraphData 的节点选择、图例、筛选与详情，并用 QML 基准对照验收。

## 本轮交付：共享知识图谱交互基础

验收目标：同一 GraphData 在浏览器中形成真正可交互的图谱工作台；业务状态不绑定渲染库，
节点选择、图例、筛选、详情和空状态与 QML 已验证的基础行为一致。

已完成：

- 新增 `@omnilit/knowledge-graph`，集中管理 GraphData、筛选、节点/边选择和悬停状态；
  React 组件不维护互相冲突的状态副本。
- 定义完整 `GraphRenderer` 接口，并按架构约束只实现 `G6GraphRenderer`，未引入 Sigma。
- G6 使用确定性圆形布局；大型布局、图算法、聚类和抽样未放入 React 主线程。
- 实现缩放、画布拖拽、节点拖拽、适应视图、节点/边点击、选中/悬停状态与图片导出底层接口。
- 固定夹具扩展为论文、作者、方法、数据集、结果 5 类节点和 4 类正式关系。
- 实现关键词与节点类型组合筛选；只保留两个端点均可见的关系，隐藏选中节点时清空选择。
- 实现节点类型图例、当前节点/关系/证据统计、节点和关系详情、属性与原文证据文本。
- 提供可搜索、键盘可操作的节点列表作为 Canvas 替代入口，不只依赖颜色表达节点类型。
- 实现原始空图、筛选空状态与恢复操作；API 加载和错误状态继续由统一 Web 入口负责。
- 使用 `React.lazy` 拆分图谱路由，G6 不进入普通路由首包。

对照与验证：

- TypeScript/Python 共用固定 GraphData；Python 适配为 QML 兼容结构后仍为 5 节点、4 关系，
  节点类型和正式关系集合一致。
- 15 项前端测试通过，其中状态测试覆盖 100、1k、5k、10k 节点筛选上限。
- 真实浏览器验证 Canvas 点击、列表点击、详情同步、类型筛选、搜索空状态和恢复；修复
  React Strict Mode 与 G6 异步销毁竞态后，控制台错误和警告为 0。
- 应用入口约 240.10 kB（gzip 77.97 kB）；G6 异步 chunk 1,423.40 kB
  （gzip 413.00 kB），作为后续优化和大型图测试的明确基线。

桌面端影响：无。QML 图谱仍是正式桌面实现，本轮没有引入 Qt WebEngine 或改动控制器。

安全影响：共享模块不访问 Qt 全局对象、数据库、文件系统或网络；数据仍由统一 API Client
在应用入口获取。外部链接和文件能力仍由 Platform Bridge 管理。

回退方式：移除 `packages/knowledge-graph`、Web 路由接入及 workspace 依赖即可恢复上一轮
固定摘要页面；共享协议、Python/QML 和桌面应用不依赖本模块。

已知限制：本轮不是完整 Web 图谱。节点展开、文献列表联动、时间轴、聚类、趋势、保存视图、
产品级导出与真实 Local Agent 服务尚未迁移；大型 G6 可视渲染的帧率和内存也尚未验收。

下一轮最高优先级：迁移“节点展开＋文献列表双向联动”纵向切片，使用真实 Local Agent
查询接口替换固定 transport，并补充取消、分页和 1k 节点浏览器性能基线。

## 本轮交付：Local Agent 图谱探索与文献联动

验收目标：Web 图谱不复制桌面端邻居和文献业务规则，通过安全 Local Agent 查询边界完成
种子投影、可取消分页展开、去重合并，以及图谱与文献列表的双向选择。

已完成：

- 共享协议新增 `GraphNeighborPage`、`LiteratureRow` 与 `LiteraturePage`，继续由同一 JSON
  Schema 生成 Python/TypeScript 类型。
- 抽出稳定的图谱缓存 ID/路径模块；QML 控制器委托该模块，既有目录命名完全不变。
- 新增独立 `services/local_agent`，直接复用 `neighbor_page`、`seed_node_ids` 和
  `project_literature_rows`，不在 TypeScript 重写排序、方向关系或引用规则。
- HTTP 服务只绑定 IP 回环地址，使用至少 24 字符 Bearer Token、精确 Origin 白名单、
  32 MiB 图缓存、64 KiB 请求体、并发信号量、输入路径防护和不泄露内部信息的 APIError。
- API Client 新增分页邻居和文献 POST 查询，保持统一认证、超时、取消和错误规范。
- Web 首屏读取种子图；详情面板支持关系范围、展开/加载更多、取消、空白和错误状态。
- Reducer 按节点/关系 ID 合并分页，重复页不会制造副本；文献列表随可见图谱重新投影。
- 点击图谱或无障碍节点列表会同步文献选中态；点击文献会同步节点详情并调用唯一 G6
  渲染器聚焦节点。
- 未配置 Local Agent 时明确显示演示模式；配置 URL/Token 后走真实服务，不静默降级。
- 新增 1k/999 关系确定性浏览器基线入口，当前已验证数据生成契约，真实可视性能采样留在
  下一切片，不提前宣称达标。

验证：

- 19 项 Web 测试、严格 TypeScript、代码生成漂移检查和生产构建通过。
- 5 项 Local Agent 专项测试覆盖种子/分页/文献、鉴权、Origin、非回环绑定和路径输入防护；
  与共享协议/QML 契约合计 11 项专项 Python 测试通过。
- 真实浏览器从 1/0 展开到 5/4，文献从 1 条更新为 2 条；引用文献反向选择详情成功，
  Canvas 存在、无 Vite 错误覆盖层，控制台错误和警告为 0。
- 构建入口 243.67 kB（gzip 79.20 kB），G6 异步 chunk 1,427.59 kB
  （gzip 414.30 kB），CSS 11.82 kB（gzip 3.02 kB）。

桌面端影响：只把控制器内部 `_safe_record_id` 委托给行为相同的纯 Python 函数；QML 页面、
控制器 API、缓存目录和正式桌面入口均未替换。全量桌面测试仍作为最终门禁。

回退方式：移除 `services/local_agent`、探索 DTO/API Client 方法、Web `dataSource` 接入和
`knowledge_graph_storage.py`，并恢复控制器内原静态 ID 函数，即可回到固定完整图切片；缓存
文件无需迁移或回滚。

已知限制：桌面进程尚未负责 Local Agent 的随机 Token 生成、拉起、健康检查、版本匹配、
崩溃重启和退出回收；长任务模型尚未接入服务。1k G6 的真实浏览器帧率、内存和交互延迟也
尚未采样。

下一轮最高优先级：完成 Local Agent 桌面生命周期管理与长任务骨架，同时使用现有
`?benchmark=1000` 入口记录 1k G6 首次渲染、交互、内存和帧率；若不达门禁，再引入后端
投影或 Worker 布局，而不是在 React 主线程增加图算法。

## 本轮交付：Local Agent 桌面生命周期

验收目标：桌面端拥有 Local Agent 子进程的完整所有权；服务启动失败不能拖垮 QML，服务
崩溃可限次恢复，桌面退出不得遗留后台进程，认证令牌不进入命令行、状态或日志。

已完成：

- 新增纯 Python `LocalAgentManager`；固定参数向量启动服务，不使用 shell，也不接收 API
  传入的命令或路径。
- 每次启动/重启生成新的 32-byte URL-safe Token，只通过子进程环境传递；公开状态不包含
  Token，启动错误也不回显可执行文件或数据根路径。
- 动态选择回环临时端口，并用带 Bearer Token 的 `/v1/health` 同时核对 service 名、ready
  状态和共享协议版本；禁用环境 HTTP 代理，避免回环健康检查离开本机。
- 开发环境固定以当前 Python 的 `-m services.local_agent` 启动；冻结发行版只允许显式配置
  的服务程序或固定 `services/omnilit-local-agent(.exe)`，缺失时返回失败状态而非阻止桌面。
- Qt 在 QML 成功加载后启动 Agent，5 秒定时健康检查并在预算内重启；`aboutToQuit` 先终止，
  超时后只强制回收管理器持有的子进程。
- Agent 继承统一 `OMNILIT_DATA_DIR`，因此读写仍在现有 Workspace 根下；QML 控制器与缓存
  格式不变。

验证：

- 生命周期专项测试用真实子进程验证启动、认证健康检查、协议、令牌轮换、崩溃重启、重启
  预算和退出回收；另验证缺失固定程序不泄露路径、命令保持参数向量、Qt 四个接线点存在。
- 与 HTTP 查询服务合计 10 项 Local Agent 测试通过；PySide6 不在当前解释器时，QML 运行时
  测试按既有策略跳过，源码接线契约仍执行。

回退方式：移除 `local_agent_manager.py` 及 `app.py` 中实例化、定时器和退出连接即可；独立
Local Agent 查询服务仍可手动运行，QML/控制器不依赖管理器对象。

已知限制：外部 Vite 开发服务器仍需显式环境变量取得 URL/Token；未来嵌入式 WebView 必须
通过窄 Platform Bridge 注入会话信息，不能写入普通可读文件。长任务 API 和 1k 真实浏览器
性能采样仍未完成。

下一轮最高优先级：实测 1k G6 门禁并实现受控长任务注册表与创建/查询/取消接口。

## 本轮交付：可恢复 Local Agent 长任务

验收目标：长操作不能占住 HTTP 请求；任务类型、并发、队列、超时和结果位置均受服务端
控制，并具有可查询进度、取消及 Agent 崩溃后的确定状态。

已完成：

- 扩展共享 `Task` 协议，加入 succeeded、消息、创建/开始/结束时间与 `resultRef`；保留
  completed 只用于旧客户端兼容，并新增 Python Task 契约校验。
- 新增 `TaskRegistry`：内部处理器白名单、2 worker、32 活跃任务默认上限、每任务 5 分钟
  默认超时、UUID ID、深拷贝输入和线程安全状态。
- 状态以临时文件替换方式原子写入 `runtime/local_agent/tasks`，结果独立写入 `results`；
  请求端不能提供输出路径。
- queued/running/stopping 状态在 Agent 重启后统一转为带 `agent_restarted` 的可重试失败，
  不会伪装成继续运行或成功。
- 实现 `POST /v1/tasks`、`GET /v1/tasks/{id}`、`POST /v1/tasks/{id}:cancel` 和
  `GET /v1/tasks/{id}/result`，全部复用 Token、Origin、请求体和并发防护。
- 首个受控真实任务 `graph.audit` 复用图谱缓存和文献投影，逐批报告元素进度，返回节点、
  关系、类型和文献计数；循环内检查取消与超时。
- API Client 增加 create/get/cancel/result 四个方法，业务端仍不直接散落 fetch。

验证：

- TaskRegistry 测试覆盖成功/进度/结果、运行中取消、类型白名单、队列上限、受控超时和
  崩溃恢复；HTTP 集成测试完成 graph.audit 创建、轮询和结果读取。
- API Client 测试验证四个任务方法的 HTTP method/path；共享协议测试验证 succeeded 与
  resultRef，并拒绝未知状态。
- 当前全量门禁为 21 项 Web 测试与生产构建通过；Python 全量 541 项通过、127 项按既有
  环境条件跳过，`git diff --check` 通过。

回退方式：移除 `task_registry.py`、四个 HTTP 路由、API Client 任务方法和 Task 可选字段；
短查询与桌面生命周期不依赖任务注册表。已生成的 task/result JSON 位于独立 runtime 目录，
可直接忽略，无需迁移知识图谱缓存。

已知限制：当前只有 graph.audit 使用长任务模型；图谱聚类、导出和批量抽取尚未逐项接入。
任务进度当前用轮询读取，SSE/WebSocket 推送将在确有产品消费者时加入。1k 优化后真实浏览器
时间、帧率和内存复测仍未完成。

下一轮最高优先级：完成 1k 复测，然后把时间轴或聚类作为下一条共享图谱纵向切片接入
Local Agent 预计算和 Task 进度模型。

## 本轮交付：大图 LOD 与聚合投影

验收目标：语义图规模不能直接等于 G6 渲染规模；Web 能请求明确层级、取消投影、查看性能
诊断并从聚合节点钻取，且复用桌面端已验证的确定性 LOD 算法。

已完成：

- 共享协议新增 `GraphProjection` 与 `GraphProjectionStatus`，分离完整语义 GraphData 和当前
  渲染图，报告预算、真实/聚合/裁剪元素、耗时及超预算状态。
- Local Agent 新增受认证 projection POST；复用 `project_render_graph` 的空间裁剪、重要性
  排序、聚合节点、聚合边、pin 保留和 overview/normal/detail 固定预算。
- 输入只接受有界 viewport、最多 200 个 pin 和 academic/overview 布局模式；不能指定文件、
  算法模块或任意预算。
- 聚合节点的 memberCount/memberSample 与聚合边 count 被保留在共享 attributes，Web 可解释
  聚合含义并用样本 pin 请求 detail 钻取。
- API Client/DataSource 新增可取消投影；Reducer 集中维护 loading/ready/error、层级、图数据
  和诊断，不在组件保存冲突图副本。
- Web 增加概览/标准/细节控件、取消、服务消息与耗时；选择聚合节点显示“展开聚合节点”，
  普通节点仍走邻居分页。
- 大图无障碍列表改为每批 100 项且搜索始终覆盖完整当前投影；G6 超过 250 节点时只显示
  高重要性标签。Canvas 的 aria 节点/关系数现随筛选变化，不再朗读未筛选总数。
- 唯一 G6 renderer 回报 render 时长、完成时刻和元素数；基准页面内置 1 秒 RAF 与可用
  Chromium heap 采样，不依赖外部调试权限。

验证：

- Local Agent 1k 服务契约产生不超过 240 节点的概览，含可解释聚合属性且未超过 120 ms
  投影门禁；既有 100/1k/5k/10k LOD 测试继续覆盖确定性和时间/边预算。
- 真实浏览器 1k/999 首次 render 391.8 ms、完整重绘 503.2 ms、267 节点筛选 123.1 ms、
  单节点搜索 10.6 ms；DOM 按钮降至 101，控制台 warning/error 为 0。
- 演示模式真实浏览器验证层级控件、投影替换 1/0 为 6/5、诊断文本、文献同步和 Canvas；
  小图按算法正确返回 detail，即使用户从 overview 发起请求。
- 当前 Web 门禁 23 项测试和生产构建通过；LOD/服务/共享协议 17 项专项 Python 测试通过。

回退方式：移除 GraphProjection DTO、projection 路由/API Client 方法、Reducer 投影 action 和
层级控件即可回到渐进邻居图；桌面 LOD 文件和 QML 路径未修改，不需要缓存迁移。

已知限制：内置 FPS/heap 输出是在本轮浏览器验证结束后加入，数值仍待下一次读取；G6 大块
体积仍需裁剪。时间轴、保存视图、趋势和产品导出仍未迁移。

真实 viewport 后续补齐：`GraphRendererEvents` 现在回报实际画布宽高、G6 zoom 和 canvas
origin 位移，初始化、transform 完成与 size change 都会刷新快照。概览/标准/细节投影以
当前相机为基准应用 0.5×/1×/2×，并保留 pan 与 overscan；固定 960×640 只作为画布尚未
挂载时的安全回退。纯函数测试覆盖 1280×720、1.5× zoom 和非零平移，Web 类型检查、24 项
测试及生产构建通过。

下一轮最高优先级：读取内置 FPS/heap 基线；随后迁移时间轴或保存视图纵向切片。

## 本轮交付：共享图谱视图保存与恢复

验收目标：React 与 QML 使用同一版本化快照和同一桌面文件；Web 可经统一 API Client 完成
命名保存、列表、恢复和删除，并恢复图数据、筛选、选择、层级、缩放及平移。

已完成：

- 将原有宽松 `GraphViewState` 扩展为版本 2 权威协议，明确 exploration、filters、selection、
  path、viewport、summary/list/restore/mutation；生成 TypeScript 与 Python 类型。
- `normalize_snapshot` 继续兼容旧 QML 快照，并补充协议版本、Web 节点类型/待复核筛选、画布
  宽高；桌面原有保存文件无需迁移。
- Local Agent 与 QML 共用 `knowledge_graph_views.json`；新增保存、列表、读取、删除 REST，采用
  原子替换、100 项/1 MiB 上限、ID/record 校验和失效图元素 reconciliation。
- API Client 封装四个视图方法；fixture transport 支持有界前缀路由，普通浏览器演示模式也能
  完成同一工作流。
- React 新增独立 `SavedViewsPanel`，包含读取、空白、错误、重试和短操作状态；保存当前图、
  筛选、选择和相机，恢复时由 Reducer 原子替换服务端图数据并调用 renderer `setViewport`。

验证：

- 协议、Local Agent service/HTTP、API Client、Reducer 和独立 Panel 专项测试通过。
- 真实浏览器完成保存 → 筛选为空 → 恢复 → 删除：种子图保持 1/0，搜索恢复为空，G6 canvas
  存在 4 个渲染子层；相机 scale `4.3273`、pan `(-246.94, -176.32)` 前后一致。
- 浏览器验证发现并修复首次 render 前读取 G6 camera 导致画布挂载中断，以及 G6 viewport
  translate 单位受 zoom 影响导致 pan 漂移；最终页面有内容且无 Vite 错误覆盖层。
- 全量门禁最终为 27 项 Web 测试、类型检查、生成物检查和生产构建通过；Python 544 项通过、
  127 项按既有环境条件跳过。

安全与兼容：业务组件仍不直接使用 fetch、文件系统或 Qt 全局对象；Local Agent 路由继续受
Bearer Token、Origin、64 KiB 请求体和并发限制。删除只接受服务端安全 ID；旧 QML 版本 2
快照经 normalize 后仍可读取，原 QML 保存/恢复路径未删除。

回退方式：移除视图 REST 路由和 API Client/Panel 接入即可；共享 JSON 文件和 QML 控制器仍
保持原行为。GraphViewState 新字段均由 normalize 补齐，已有文件无需降级。

下一轮最高优先级：迁移共享时间轴纵向切片，并读取内置 FPS/heap 性能基线。

## 本轮交付：共享知识演化时间轴

验收目标：React 与 QML 读取同一套桌面端 `topic_map.json` / `evolution.json` 缓存；时间范围、播放年份、主题里程碑、关键引用路径与图谱窗口保持一致，并且算法不复制到浏览器主线程。

已完成：

- 权威协议新增 `GraphTimelineQuery` 与 `GraphTimeline`，覆盖年度论文、主题事件、转折点、引用、主题序列、关键路径、速度比较、诊断、时间选择以及同请求返回的 LOD `GraphData`；视口尺寸、缩放、平移和 overscan 具有明确边界。
- Local Agent 新增 `POST /v1/timelines/{timelineKey}/query`，可使用桌面集合键或 evolution cache key 定位现有缓存；复用 `build_evolution_graph` 和 `project_render_graph`，未在 React/TypeScript 中重写聚类、时间路径或 LOD 算法。
- 查询会夹紧并规范化起止年份，将播放年份吸附到最近的已知年份，以 `effectiveEndYear` 同步裁剪事件、主题点、转折点、关键路径及图谱；损坏缓存返回受控 `invalid_timeline_cache`，未知时间轴返回 404。
- API Client 增加可取消的时间轴 POST；Reducer 原子替换当前时间窗口图和时间诊断，避免时间轴与画布维护两份冲突状态。
- React 新增独立 `TimelinePanel`：起止年份选择、播放/暂停、回到起点、加载/取消/空白/错误/重试、年度论文、主题里程碑、关键引用路径与主题速度比较。
- 点击时间轴论文会选择同一 GraphData 中的论文节点；播放或范围切换会同步替换 G6 图；时间图的论文节点直接形成关联文献列表，无需把 timeline 虚拟 recordId 错当作单篇论文缓存查询。
- 新增固定 `shared-timeline-v1.json`，普通浏览器演示模式与 Local Agent 使用同一 DTO 和相同交互；真实 Agent 可通过 `VITE_TIMELINE_KEY` 指定桌面集合键或 evolution cache key。

自动化验证：

- Python 协议、Local Agent service 与 HTTP 测试覆盖固定夹具、缓存复用、cache key 查找、播放窗口裁剪和 REST 路由。
- Web 测试覆盖 API 请求 method/path/body、Reducer 图替换、播放已知年份步进、时间轴内容以及加载/取消/错误恢复状态；当前专项结果为 33 项 Web 测试通过，TypeScript 严格检查通过。
- 桌面端 QML 时间演化页面、算法和缓存格式未被替换或删除；回退只需移除 GraphTimeline 协议、Local Agent 路由和 React Panel 接入。

浏览器验收：演示时间轴首屏为 2024，显示 5 节点/5 关系和 3 篇文献；结束年份切换为 2022 后同步变为 3 节点/3 关系和 2 篇文献，路径明确标注当前窗口保留 2 篇。点击 `Contract-First Graphs` 后，详情、节点列表和文献列表三处选择一致。验收中发现并修复 timeline 虚拟 recordId 误调用单篇论文保存视图、邻居展开和普通投影接口的问题；时间图模式现在只使用自身的时间投影查询。

已知限制：本切片共享的是已有桌面演化缓存和产品交互，尚未把 React 图谱嵌入 Qt WebEngine；云端时间轴、账户同步和协作也不在本切片范围内。第二阶段长期目标仍保持进行中。

下一轮最高优先级：完成真实浏览器播放/范围/论文联动验收与全量回归；随后进入 Qt 嵌入共享 React 图谱的可回退纵向切片。

## 本轮交付：Qt WebEngine 嵌入共享 React 图谱

验收目标：桌面端继续使用现有 QML 知识图谱页面、工具栏、筛选器和详情面板，仅把中心绘图画布
替换为 React/G6；原 QML 画布保留为即时回退。静态资源、Local Agent、WebChannel 和外部导航
具有明确安全边界。

已完成：

- Vite 改为相对资源基址，路由改为 `HashRouter`；专用 `graph-canvas` 嵌入路由不渲染网页端产品
  外壳，只渲染 `GraphCanvas`。嵌入 URL 只携带 `embedded=1` 与经过验证的 recordId，不携带 Token。
- Local Agent 在鉴权和 Origin 校验后从只读 `/app/` 提供固定后缀、路径约束和 32 MiB 上限的
 生产构建资源；响应包含严格 CSP、`no-store`、`nosniff`、`no-referrer`、same-origin 资源策略。
  服务启动后只把本次精确随机 loopback origin 加入允许集，不使用端口或域名通配。
- 新增 `DesktopWebController`：特性开关关闭、WebEngine 模块缺失或资源缺失时保持禁用；启用时
  必须在 `QApplication` 前初始化 WebEngine。请求拦截器只对当前 Local Agent 的精确
  scheme/host/port 注入随机 Bearer Token，Token 不进入 URL、QML、状态对象或日志。
- 新增 `HybridKnowledgeGraphView.qml` 和懒加载 `SharedKnowledgeGraphCanvasWebPage.qml`。React 画布
  通过 WebChannel 读取当前 QML 筛选后的投影，并把节点/边选择、悬停和视口回传给原控制器；页面
  其余部分仍是原 QML 设计。组件加载错误、Web 加载失败、渲染进程终止或服务不可用时，会话立即
  禁用 React 画布并显示已预热的原 QML 画布。
- 普通与全屏视图互斥创建 React 画布，避免两个渲染器同时回传视口。图片导出仍复用原 QML
  导出实现，普通浏览器与 Mock Bridge 行为保持不变。
- Windows/macOS 构建先生成 Web dist，打包该目录和 QtWebChannel/QtWebEngine 模块。冻结发行版
  以同一签名 OmniLit 二进制的固定 `--local-agent` 模式启动独立子进程，不依赖漏打包的第二个
  可执行文件，也不开放 shell 命令面。

验证：

- Web 严格类型检查、62 项测试和 Vite 生产构建通过；产物使用相对 asset URL。
- 桌面嵌入与 Qt/QML 迁移 133 项聚焦 Python 测试通过，覆盖 WebEngine 路径、令牌不入 URL、
  画布懒加载、QML 回退与打包清单。
- Qt 6.9 环境实际完成 `QtWebEngineQuick.initialize()`、QML WebEngine 组件编译和控制器构造；
  控制器生成的本地 URL 可通过同源校验且不含会话 Token。OmniLit Conda 环境的既有 QML
  运行时测试仍受其 `qtquick2plugin.dll` 依赖加载故障阻塞，该故障在未加载新增页面时同样存在。

启用与回退：共享 React 图谱现已默认启用；设置 `OMNILIT_SHARED_WEB_GRAPH=0` 可显式关闭并
回到原桌面版行为。运行中任一嵌入故障会自动回退；关闭特性不需要
数据或缓存迁移。

已知限制：React 仅负责单篇文献知识图谱的绘制画布；这是明确的桌面产品边界，不计划用网页端
整页替换现有 QML 图谱界面。文献库、阅读器、设置、云端账户/同步/协作不受此画布改动影响。
第二阶段长期目标继续进行；Windows/macOS 平台签名发行包真机烟测按文末范围决策延期，下一轮
开始新的共享产品纵向切片。

## 本轮交付：共享文献库查询与详情

验收目标：React 文献库与桌面 QML 使用相同的版本 2 文献缓存和相同的搜索/排序基础语义；
浏览器通过统一 API Client 完成加载、检索、PDF 状态筛选、排序、分页、选择与详情查看，不在
前端复制下载、去重、元数据增强或本地文件系统规则。

已完成：

- 权威 Schema 新增 `LibraryQuery`、`LibraryRecordSummary`、`LibraryRecordDetail`、
  `LibraryFacets` 与 `LibraryPage`，生成 TypeScript/Python 类型；请求限制查询 500 字符、64 个
  关键词组和每页最多 200 条。
- 抽取无 Qt 的 `literature_library_shared`：读取桌面 `library_cache.json` 版本 2，集中实现搜索
  文本、年份、相关性、排序、筛选、facet、列表/详情投影及 extraction 状态。原 QML 控制器已
  改用同一搜索、年份、相关性、排序和 extraction 判断函数。
- Local Agent 新增受认证 `POST /v1/library/query` 与 `GET /v1/library/records/{recordId}`；响应
  按权威 Schema 校验，支持含 `/` 的 DOI 型不透明 recordId，缓存缺失与空筛选结果具有不同状态。
- 为避免泄露桌面文件系统，Library DTO 不包含 `localPdfPath`，只返回 `downloaded` 和
  `hasExtraction`；详情查找只在已加载缓存中比较 opaque ID，不把 ID 拼接进文件路径。
- API Client 新增可取消的查询与详情方法。React `/library` 改为独立懒加载页面，提供语义化
  检索表单、PDF 状态筛选、五种排序、服务端分页、稳定 recordId 选择和详情面板；普通浏览器
  fixture 提供相同协议和两篇确定性记录。

验证：

- 共享生成物检查、TypeScript 严格检查、36 项 Web 测试与 Vite 生产构建通过；文献库形成独立
  4.38 kB 懒加载 chunk。
- 全量 Python 553 项通过，127 项按当前默认解释器缺少可选 PySide6 条件跳过；Local Agent
  service/HTTP 测试覆盖缓存复用、搜索、下载状态、路径隐藏、DOI 型 ID、列表与详情路由。
- 本地开发服务器的 `#/library` 入口返回 HTTP 200；应用内浏览器会话未能取得该本地标签的
  控制权，因此本轮没有把自动化 DOM 交互结果作为验收证据，后续真机烟测仍需补齐。

已知限制：本切片是只读文献库基线；收藏项目/研究集合写入、比较工作区、PDF 阅读与原生打开
仍保留在 QML。下一轮继续共享集合与工作空间，并为未来 Cloud API 同步定义冲突与权限边界。

## 本轮交付：共享研究集合与比较工作区

验收目标：桌面 QML、嵌入式 React 与普通网页通过同一版本化状态和相同业务规则管理研究集合、
收藏与最多四篇文献的比较工作区；多个桌面进程或 Local Agent 并发写入时必须显式发现冲突，
不能以最后写入者静默覆盖较新的状态。

已完成：

- 权威 Schema 新增 `ResearchCollection`、`LibraryWorkspaceState`、`LibraryState`、
  `LibraryMutationRequest` 与 `LibraryMutationResult`，并为 `LibraryQuery` 增加 `collectionId`；
  TypeScript/Python 生成类型和运行时验证器保持一致。
- `library_state.json` 升级为 schema version 2，包含单调递增 `revision`、更新时间、同步状态、
  研究集合、收藏映射和比较工作区。共享无 Qt 状态存储使用同目录互斥锁、临时文件原子替换、
  陈旧 revision 拒绝和损坏文件 `.bak` 备份恢复；所有业务写入统一经过 mutation。
- QML 文献库控制器改用共享状态存储；Local Agent 新增受认证 `GET /v1/library/state` 与
  `POST /v1/library/state/mutations`。变更请求必须携带 `expectedRevision`，冲突返回 409，
  缺失集合和非法操作具有受控错误，不自动重试非幂等写入。
- 共享规则覆盖创建、重命名、删除自定义集合、增删集合文献、增删/清空比较工作区；内置集合
  禁止删除，比较工作区最多四篇。文献查询可按集合筛选并返回一致的服务端分页结果。
- React `/library` 加入集合筛选、目标集合写入、比较栏和冲突后重新加载；新增懒加载
  `/collections` 管理页，支持新建、重命名、删除、记录计数和比较工作区清空。fixture transport
  与 API Client 使用同一 DTO 和路径，页面不直接访问文件系统或散落调用 `fetch`。
- `sync-conflict-strategy.md` 明确本地权威、`local_only`/`pending_sync`/`synced`/`conflict`/
  `deleting` 状态、未来 Cloud API 合并规则，以及分享 ACL 与比较工作区的同步边界。

验证：

- 共享生成物检查、TypeScript 严格检查、38 项 Web 测试和 Vite 生产构建通过；集合管理页形成
  独立 3.19 kB 懒加载 chunk。构建仍报告 G6 主图 chunk 大于 500 kB，属于后续拆包事项。
- 全量 Python 560 项通过，127 项按当前默认解释器缺少可选 PySide6 条件跳过；新增测试覆盖
  两个状态存储实例的可见性、并发写入仅一方成功、陈旧 revision、比较上限、内置集合保护、
  损坏状态恢复，以及 Local Agent service/HTTP 的查询、变更和 409 冲突契约。

已知限制：本轮只实现本地权威状态与未来同步契约，尚未提供真实用户账户、Cloud API、远端持久化、
分享链接、ACL 或多人实时协作；PDF 阅读和原生打开仍由桌面能力承担。第二阶段长期目标继续进行，
下一轮进入账户、Cloud API、同步、分享与权限纵向切片。

## 本轮交付：Cloud API、账户与版本快照同步基线

验收目标：账户和云端研究数据必须位于独立服务边界；Local Agent 与 Cloud API 凭据不能混用；
跨租户访问、陈旧同步和未授权分享必须被服务端拒绝；用户能够显式控制上传/AI/团队/分享权限，
并能导出或删除自己的账户数据。

已完成：

- 权威 Schema 新增 `CloudDataControls`、`UserAccount`、`AuthSession`、`LibrarySyncRequest`、
  `LibrarySyncResult`、`ShareLink` 与 `AuditEventPage`，重新生成 TypeScript/Python 类型并增加
  Python 边界验证器。
- 新建独立 `services/cloud_api` 参考服务：SQLite 外键和每查询租户条件提供隔离；密码使用
  PBKDF2-SHA256 600,000 次迭代，访问令牌和分享令牌只保存 SHA-256 哈希，研究集合快照使用
  AES-GCM 加密存储。加密密钥必须由环境注入，没有开发默认值。
- 服务实现注册/登录、八小时会话、逐项研究数据控制、库快照读取/同步、分享创建/撤销/公开解析、
  租户审计、账户导出和邮箱确认删除。`baseCloudRevision` 陈旧时返回 HTTP 409、当前密文解出的
  服务端副本和冲突 ID，不覆盖任何一方。
- HTTP 边界限制 128 KiB JSON、精确 Origin、CORS 预检、每路由/来源分钟限流、安全响应头和
  受控错误；非 loopback 绑定必须显式声明可信 TLS 终止。CLI 从环境读取数据库、32 字节密钥、
  允许源和公开地址。
- API Client 新增账户、数据控制、同步、分享、审计、导出与删除方法，并允许且仅允许同步接口
  把 409 作为业务冲突 DTO 返回。Cloud API 与 Local Agent 分别实例化，云会话只保存在当前标签
  `sessionStorage`，不进入 URL、Qt Bridge 或本地持久 fixture。
- React 新增懒加载 `/account`：登录/注册、七项隐私控制、Local Agent 状态手动同步、明确的
  “保留云端/使用本地副本覆盖”冲突选择、只读分享及撤销、审计计数、JSON 导出和邮箱确认删除。
  普通浏览器 fixture 提供同一工作流，并明确标注为本地演示服务。

验证：

- Web 生成物检查、TypeScript 严格检查、41 项测试和生产构建通过；账户页为独立 7.26 kB
  懒加载 chunk。React 最佳实践复核覆盖单组件文件、effect 取消/依赖、语义化表单、稳定 key、
  路由懒加载和不在渲染内容中暴露 token。
- Python 全量 568 项通过，127 项按可选 PySide6 条件跳过；Cloud API 8 项专项覆盖凭据哈希、
  密文落盘、陈旧版本、精确租户隔离、显式分享开关、跨租户撤销拒绝、撤销后失效、审计、导出、
  确认删除、CORS 预检、安全响应头和非 TLS 外部绑定拒绝。

已知限制：这是可运行且有安全测试的参考服务，不代表生产网页已经部署。邮件验证、密码重置、
刷新令牌/会话撤销、成员邀请与资源级 ACL、细粒度操作日志合并、云端图谱/任务、实时协作、外部
监控、自动备份和灾难恢复仍未完成；这些是第二阶段“网页端正式上线”里程碑的后续工作。

## 本轮交付：团队邀请与资源级 ACL

验收目标：基础协作不能只依赖前端角色按钮或匿名分享；邀请必须单次、限时且不可从数据库恢复；
非 Owner 读取或修改研究数据必须同时满足同租户、Owner 团队总开关和明确资源 ACL，跨租户 principal
不能被授权。

已完成：

- 权威 Schema 新增 `TeamMemberList`、`TeamInviteCreateRequest`、`TeamInviteAcceptRequest`、
  `TeamInvite`、`ResourcePermissionMutation` 与 `ResourcePermissionList`，并重新生成双语言类型和
  Python 验证器。
- Cloud API 新增 `team_invites` 与 `resource_permissions` 表。邀请使用 32 字节随机 token，数据库
  只保存哈希；旧邀请被替代、过期或首次接受后均不可复用。公开接受入口使用与登录相同的每来源/
  路由 10 次每分钟限制，成功后创建独立密码哈希与会话。
- 角色矩阵区分 Owner/Admin/Member：Admin 只能邀请和移除 Member；只有 Owner 能创建 Admin、修改
  角色、管理 ACL、导出或删除租户。Owner 不可通过成员接口删除，移除成员同步清理其会话和用户 ACL。
- 研究数据访问采用三层判断：会话租户、Owner 的 `allowTeamAccess` 总开关、用户或 team principal
  的 viewer/editor ACL。Admin 不自动获得研究数据；viewer 不能同步写入，editor 可以同步和创建
  不超过自身资源边界的分享；跨租户用户 ID 返回受控 404。
- HTTP 新增成员列表、邀请、公开接受、角色修改、成员删除、ACL 列表/变更路由。API Client 完整
  封装这些路径；普通浏览器 fixture 使用同一 DTO。
- React 账户页抽出独立 `TeamPanel`，支持邀请、一次性地址、角色、文献库 ACL 和二次确认移除；
  新增懒加载 `#/invite/:token` 接受页。Member 不显示 Owner 的租户导出/删除，Admin 不显示服务端
  必然拒绝的其他 Admin 移除操作。

验证：

- Web 生成物检查、严格类型检查、44 项测试和生产构建通过；邀请页为独立 1.22 kB chunk，账户/
  团队页为 11.51 kB chunk。React 最佳实践复核覆盖组件拆分、effect AbortController、派生权限状态、
  语义表单、稳定成员 ID key 和双阶段破坏性操作。
- Python 全量 572 项通过，127 项按可选 PySide6 条件跳过；Cloud 专项覆盖邀请 token 不落明文、
  单次使用、Owner/Admin 边界、viewer/editor 差异、团队总开关、跨租户 principal 拒绝、成员删除后
  会话失效、HTTP 路由和公开邀请限流。

已知限制：当前用户只属于一个租户，已注册邮箱不能接受第二租户邀请；尚未实现租户切换、Owner
转移、邮件投递/验证、密码重置、外部 IdP、云图谱资源存储和多人实时编辑。下一轮继续云图谱保存/
同步和云任务，复用本轮 ACL 判定而不建立第二套权限逻辑。

## 本轮交付：云图谱保存、查询与共享视图

验收目标：配置 Cloud API 的真实网页不能继续读取演示图；桌面/Local Agent 图谱必须通过显式
revision 同步进入加密云存储，冲突不静默覆盖；网页能使用同一 GraphData 和 GraphViewState 完成
图谱读取、邻居展开、文献联动、视图保存/恢复，并复用团队 graph ACL。

已完成：

- 权威 Schema 新增 `CloudGraphSyncRequest`、`CloudGraphSyncResult`、`CloudGraphSummary` 与
  `CloudGraphList`，并将 `graph` 加入分享和 ACL 资源类型；双语言类型和边界验证器重新生成。
- Cloud API 新增 `cloud_graphs` 与 `cloud_graph_views`：GraphData/GraphViewState 使用 AES-GCM
  加密，按 `(tenantId, recordId)` 保存单调 cloudRevision；路径 recordId 与 payload 不一致直接 409。
  单图限制 10,000 节点、40,000 关系、16 MiB 请求和 24 MiB 密文，单图视图最多 100 个。
- 新增云图谱列表、读取、同步、分页邻居、当前可见文献投影，以及视图列表/保存/恢复/删除 HTTP
  路由。非法分页返回 400；视图恢复对当前图谱做 reconciliation，不恢复已消失元素。
- graph viewer 可读图谱、邻居、文献和视图；editor 可同步、保存/删除视图和创建分享。graph_view
  分享先解析父图谱并检查 graph editor；公开 graph/graph_view 分享返回对应加密资源解密后的 DTO，
  不再错误投影为文献库状态。
- API Client 新增云图谱列表和接受 409 的 revision 同步方法；原 getGraph/邻居/文献/视图方法直接
  复用。Web 数据源按 Local Agent → Cloud API → fixture 选择；Cloud 模式不声明尚未实现的投影/
  时间轴能力，Local Agent 保持完整 LOD 与时间轴。
- React 账户页新增独立 `CloudGraphPanel`：列出有 ACL 的云图谱、从 Local Agent 显式上传、显示
  revision 冲突并要求用户选择；真实普通浏览器没有 Local Agent 时隐藏上传，杜绝演示图污染云数据。
  `TeamPanel` 可选择文献库或具体 graph recordId 管理 viewer/editor ACL。

验证：

- Web 生成物、严格类型检查、46 项测试和生产构建通过；测试覆盖统一客户端图谱路径、409 业务结果、
  无 Local Agent 时禁止上传和云端数据源选择。React 复核覆盖独立组件、effect 取消、派生 revision、
  稳定 recordId key、语义表单和显式冲突操作。
- Python 全量 574 项通过，127 项按可选 PySide6 条件跳过；Cloud 专项覆盖密文不含论文标题、版本
  冲突、路径/payload 一致性、容量边界、图谱列表/读取、邻居/文献、视图 CRUD/reconciliation、
  graph viewer/editor 差异、公开 graph 分享和非法分页。

回退方式：移除 CloudGraph DTO、`cloud_graphs`/`cloud_graph_views` 路由与 `CloudGraphPanel`，运行时
即可继续使用 Local Agent 或 fixture；桌面缓存、QML 图谱和本地保存视图均未迁移或改写。

已知限制：Cloud API 尚未执行服务端 LOD/聚合投影、时间演化、云端图计算、全文检索或实时协作；
云图谱当前是完整加密快照而非细粒度操作日志。下一轮进入受控云任务和可观测性/恢复基础设施。

## 本轮交付：受控云任务与可观测性/重启恢复基线

验收目标：Cloud 长任务不能是进程内不可追踪线程；创建、进度、取消、结果和错误必须使用共享 Task
协议并持久化，跨租户任务 ID 不得形成读取旁路；队列、并发和超时必须有界；服务重启后遗留任务
必须恢复或明确失败；日志和指标不能泄露凭据、分享令牌或研究内容。

已完成：

- 权威 Schema 新增 `CloudServiceMetrics`，双语言生成类型和 Python 边界验证器保持一致；Cloud 与
  Local Agent 继续复用 `Task` DTO，不建立第二套状态模型。
- Cloud API 新增持久化 `cloud_tasks`、两个受控 worker、全局 32/单租户 16 个 active 任务上限和
  五分钟超时。当前只允许 `graph.audit(recordId)`，入队时复用 graph viewer ACL；结果使用 AES-GCM
  加密，任务列表、取消和结果均按 tenantId 查询。
- 任务支持 queued/running/stopping/succeeded/failed/cancelled、进度、取消和结果引用。取消顺序经过
  竞态测试；正常关停取消排队任务并安全停止 worker，异常重启把遗留 active 任务明确标记为可重试的
  `service_restarted`，不伪造断点续算。
- HTTP 新增任务四路由和 Owner/Admin `GET /v1/metrics`。指标只返回当前租户用户、图谱、任务状态和
  审计计数；完成日志使用单行 JSON 与 requestId，分享 token、资源/图谱/节点/视图/任务/成员 ID 均
  使用模板化 route，不记录请求体或 Authorization。
- API Client 新增 `getCloudMetrics`，任务创建/轮询/取消/结果继续复用现有方法。普通浏览器 fixture
  提供相同任务和指标路径。
- React 账户页新增独立 `CloudTaskPanel`，支持图谱审计创建、进度轮询、安全取消、结果摘要及管理
  指标。轮询同时清理 AbortController 和 timer；Member 不发起无权限的指标请求。
- 新增 `cloud-observability.md`，明确短轮询、并发、超时、重启失败、日志脱敏和未完成生产能力边界。

验证：

- Web 生成物检查、严格 TypeScript、47 项测试和 Vite 生产构建通过；React 最佳实践复核覆盖组件
  边界、effect 清理、派生权限、语义表单和原生 progress。
- Python 全量 577 项通过，127 项按可选 PySide6 条件跳过；新增测试覆盖加密结果、任务成功与审计、
  队列上限、可靠取消、重启恢复、viewer ACL、管理指标权限、跨租户 get/cancel/result 404、HTTP
  契约和分享 token 日志脱敏。

回退方式：移除 CloudServiceMetrics、`cloud_tasks` 与任务/metrics 路由、`CloudTaskPanel` 即可回到
上一轮云图谱快照；Local Agent 任务、桌面缓存、QML 页面和图谱数据不会被改写。

已知限制：当前 `graph.audit` 是验证任务基础设施的只读受控计算，不是任意云算法平台；尚无断点续算、
结果保留期清理、SSE/WebSocket、外部监控和告警。网页端正式上线仍缺自动备份/恢复演练、生产部署与
密钥轮换；多人实时协作和自动更新也未完成。商业发布签名/公证按文末范围决策延期，不再阻塞
第二阶段长期目标。

## 本轮交付：Cloud 加密自动备份与离线恢复基线

验收目标：在线 SQLite 不能通过直接复制主文件得到不确定快照；备份必须独立加密、可检测错误密钥
和篡改、原子落盘并有保留上限。恢复必须先验证再替换，默认不能覆盖现有数据库，也不能在残留 WAL
的在线目标上执行。

已完成：

- 新增 `CloudBackupManager`：使用 SQLite online backup API 生成事务一致的内存快照，执行
  `integrity_check`，规范化 WAL header 后以独立 32 字节备份密钥进行 AES-256-GCM 整体加密；中间
  明文数据库不落盘。
- 备份 envelope 认证格式版本、创建时间、明文长度和 SHA-256；读取同时验证 GCM、长度、摘要和
  SQLite 完整性。错误密钥、单字节篡改、非法 header 和非 SQLite 内容均返回受控失败。
- 原子临时文件替换和命名范围内 retention 清理确保目录只保留最新 N 份。`CloudBackupScheduler`
  在显式配置备份密钥后立即备份并按间隔执行，服务关闭时有界等待 worker。
- 备份密钥必须与研究数据加密密钥不同。服务新增目录、间隔和保留数环境配置；备份密钥仍没有开发
  默认值，也不会写入日志或备份文件。
- 新增管理终端 `backup`、`verify`、`restore` 命令，不开放远程 HTTP 恢复面。恢复要求离线且目标无
  WAL/SHM，默认拒绝覆盖；`--force` 先原子保存旧数据库，再校验并替换新库，失败时回放安全副本。
- `cloud-backup-recovery.md` 记录双密钥托管、恢复演练、异地不可变存储和仍缺能力的运维边界。

验证：

- 4 项专项测试覆盖在线加密快照、明文/凭据不可见、错误密钥、篡改、verify、保留上限、自动调度、
  默认覆盖拒绝、强制恢复安全副本、管理 CLI，以及恢复后原会话、账户和云图谱端到端可读。
- Python 全量 581 项通过，127 项按可选 PySide6 条件跳过；Web 生成物检查、严格 TypeScript、47 项
  测试与 Vite 生产构建继续通过。`git diff --check` 仅报告现有 CRLF 转换提示。

已知限制：当前是单实例完整快照，不提供增量/PITR、复制集故障转移、跨区域自动复制、KMS/HSM
轮换、不可变对象存储或自动恢复演练。生产上线仍需外部监控与告警；实时协作和商业发布体系也仍在
第二阶段后续范围内。

## 本轮交付：图谱团队批注与有界 SSE 实时协作

验收目标：基础团队协作必须进入真实共享图谱入口；多人写入不得静默覆盖，网络重试不得重复写入；
事件流不能把 Cloud token 放进 URL，也不能形成无限长连接；正文必须加密、受 graph ACL 和隐私开关
约束，并能删除、导出和随租户清理。

已完成：

- Schema 新增 CollaborationAnnotation/Event/Snapshot/Mutation/EventPage DTO，双语言生成类型与验证器
  一致；Snapshot 分别声明 graph 写权限和 Owner 批注同步开关。
- Cloud API 新增 per-graph revision、annotation 和加密 operation event 三表。单图最多 500 条有效批注，
  事件保留最近 10,000 条，恢复页最多 200 条。
- `baseRevision` 显式检测 409；UUID `clientMutationId` 使成功请求重放幂等。graph/node/edge 目标写前验证，
  同图写入事务串行，跨租户保持 404。
- viewer 可读 snapshot/event/SSE，editor 可写；Member 仍需 `allowTeamAccess`，新增/更新还必须启用
  `syncAnnotations`。关闭同步后保留读取和删除能力。
- 删除擦除当前密文正文并重写历史 upsert event 去除正文；账户导出仅包含有效批注，租户删除级联
  清理全部协作表。
- HTTP 新增 snapshot/mutation/恢复事件与 SSE。流使用 Authorization header、Last-Event-ID、25 秒等待、
  心跳/reset 帧和默认 64 个全局槽位；断连不二次发送 JSON。日志不含 recordId、targetId 或正文。
- API Client 封装 REST 与 SSE fetch 流解析、取消、超时和 reset；Cloud 协作可叠加在 Local Agent 图谱
  上，Local/Cloud token 不混用。
- `CollaborationPanel` 接入真实 `KnowledgeGraphPage`，支持节点/关系/整图批注、实时列表、删除、
  只读/同步关闭状态、退避重连和冲突刷新；timeline 与 fixture 不伪装协作。
- `graph-collaboration.md` 明确 revision、幂等、数据控制、容量、删除、恢复和非 CRDT 边界。

验证：

- Web 生成物检查、严格 TypeScript、52 项测试和 Vite 生产构建通过；React 最佳实践复核覆盖独立组件、
  effect 依赖、AbortController/timer 清理、稳定 annotation ID、语义 form/list/time 和状态提示。
- Cloud/Schema 32 项专项通过，覆盖密文、同步开关、viewer/editor、跨租户 404、幂等、等待唤醒、409、
  删除正文擦除、账户导出、event reset、SSE 帧/认证/容量、日志脱敏和协议上限。
- Python 全量 584 项通过，127 项按可选 PySide6 条件跳过；`git diff --check` 仅有现存 CRLF 提示。

性能与安全：单 SSE 请求最多等待 25 秒、默认全局 64 槽；事件批量 200、历史 10,000、批注 500。
SSE token 只在 header，正文不进入 URL、日志或明文数据库。

回退方式：移除 Collaboration DTO/表/路由、API Client 方法和 `CollaborationPanel`；Cloud Graph、
GraphView、ACL、任务、备份、Local Agent、Qt/QML 都不需数据回退。

已知限制：这是图谱批注级实时协作，不含 presence、光标、字符级 CRDT、离线 outbox、附件、@mention、
通知和多图工作空间协作。第二阶段继续生产部署、外部监控告警、SBOM/许可证与发布工程基线；
真实平台签名/公证按文末范围决策延期。

## 本轮交付：生产运行与可复现部署基线

验收目标：网页与 Cloud API 不能只存在开发构建产物；数据库版本、进程存活、服务就绪和停止流程必须可被编排器判断；Cloud API 不直接暴露到公网，生产密钥不能硬编码进镜像、Compose 文件或普通环境清单；每次变更必须自动执行 Web、Cloud 和镜像构建门禁。

已完成：

- Cloud SQLite 新增事务化 schema baseline：`PRAGMA user_version` 与 `schema_migrations` 在建表事务中一起写入；旧服务遇到更高版本数据库会在启动时明确拒绝，而不是继续读写未知结构。
- 新增 `/v1/health/live` 和 `/v1/health/ready`，原 `/v1/health` 保持为 readiness 别名。就绪检查真实验证数据库连接、schema 版本和任务服务状态，停止中的实例返回 503；响应不包含租户、路径或密钥信息。
- Cloud 运行入口处理 SIGINT/SIGTERM，停止 HTTP 接入、唤醒协作等待者、结束任务执行器和备份调度器并关闭服务；启动与停止原因使用结构化、无凭据日志。
- 数据密钥与备份密钥支持互斥的 `_FILE` secret 注入。新增非 root Cloud 镜像、React 静态镜像、同源 Nginx 反向代理和加固 Compose：Cloud 只在私有网络暴露，容器移除 capabilities、启用 no-new-privileges 与只读根文件系统，数据使用独立卷。
- `production-deployment.md` 固化 TLS edge、精确 Origin、初次部署、探针、schema 回滚、备份前置和外部监控边界；明确当前产物不等于已经托管上线。
- 新增 Phase 2 CI：Web 生成物/类型/测试/构建、Cloud API 服务/HTTP/备份/运行时测试，以及两个部署镜像的真实构建均为独立门禁；在注册表、来源证明和签名策略完成前不自动发布镜像。

验证：

- Python `unittest` 全量 589 项通过、127 项按当前默认解释器缺少可选 PySide6 条件跳过；新增 5 项覆盖 schema 持久化/新版本拒绝、停止 readiness、secret 文件和 SIGTERM 优雅停机。
- Cloud 定向 28 项通过；Web 生成物检查、严格 TypeScript、52 项测试和 Vite 生产构建通过；Compose 配置解析与 `git diff --check` 通过。
- 本机 Docker Desktop 守护进程未运行，因此无法在本机完成镜像实构建；CI 已配置真实 BuildKit 构建作为合并门禁。Web 构建仍报告 G6 主图 chunk 约 1.45 MB，属于后续拆包事项。

已知限制：尚未完成真实生产托管、DNS/TLS edge、外部监控告警接入、异地不可变备份复制与恢复演练、镜像发布/来源证明、SBOM/第三方许可证清单、依赖漏洞策略和崩溃收集。桌面签名/公证与签名更新自动发布按文末范围决策延期；其缺失不再阻塞第二阶段长期目标。

## 本轮交付：源码 SBOM、许可证与漏洞扫描门禁

验收目标：依赖清单、许可证和漏洞结果必须在每次发布持续生成并可归档；未知或未经审查的许可证、缺失完整性值和未精确固定的 Cloud 依赖必须使机器门禁失败；无法证明的桌面原生依赖、资产许可和项目自身许可必须成为显式发布阻断项，而不是被空白清单掩盖。

已完成：

- 新增确定性合规生成器和显式许可证 allow-list。它从 npm lockfile v3 提取精确版本、purl、SHA 完整性、开发范围和许可证表达式，从 Cloud 精确直接依赖及已安装元数据提取 Python 组件和许可证正文。
- 每次运行生成 CycloneDX 1.6 `omnilit-source.cdx.json`、`THIRD_PARTY_NOTICES.txt` 和 `compliance-report.json`；依赖指纹与输出顺序稳定，未知许可证、缺失 npm integrity、非精确 Python 版本和安装版本偏差由 `--strict` 阻断。
- `--release` 额外阻断根 LICENSE、Python 传递依赖哈希锁、许可证正文缺口，以及 Qt/PySide6、QtWebEngine Chromium、PyInstaller/native、logo/font/icon 和平台签名身份人工审查。当前报告不会宣称可正式发布。
- CI 新增独立 compliance job，安装 npm 与 Cloud Python 依赖后生成并归档合规证据；Web job 执行高危阈值 `npm audit`，Cloud job 执行 `pip-audit`，扫描失败不会被改写为成功。
- `release-supply-chain.md` 记录证据结构、当前阻断项、正式发布七项门禁和不得在缺少注册表/签名身份时自动发布的边界。

验证：

- 离线生成 252 个源码组件（npm 251、Cloud Python 1），机器可验证违规为 0；确定性输出、关键依赖/许可证正文和 release 阻断行为测试通过。
- Python `unittest` 全量 590 项通过、127 项按可选 PySide6 条件跳过；Cloud/合规定向 29 项通过。
- 当前正式发布仍被缺失根 LICENSE、`requirements.lock`、桌面原生/Chromium/资产审查及上游未附许可证正文阻断。PyPI 哈希锁解析因本次外部访问批准额度不可用而未执行，未伪造哈希。

已知限制：源码 SBOM 不包含容器基础 OS 和 PyInstaller 实际冻结的 native 文件；正式商业发布仍需最终镜像/桌面包扫描、漏洞处置政策、来源证明与平台签名。真实外部监控和崩溃收集仍未完成；Windows/macOS 签名/公证和签名更新自动发布按文末范围决策延期，不计入第二阶段完成度。

## 本轮交付：受保护运维指标与告警规则基线

验收目标：外部监控不能复用用户/租户会话，不能把租户或资源 ID 放入 Prometheus label，也不能通过公网 Web 代理暴露；请求可用性、错误率、延迟、协作流容量和加密备份新鲜度必须有可抓取证据及持续告警规则。

已完成：

- 新增独立 `/internal/metrics` Prometheus 抓取面，仅在配置至少 32 字符的独立运维 token 后启用；未配置返回 404，错误 token 返回 401，Cloud 用户 access token 无权访问。
- 指标覆盖 readiness、in-flight、模板化 route/status 请求计数、延迟直方图、协作 SSE active/capacity、自动备份启用状态、最近成功/失败时间和连续失败数；不使用 tenant、用户、recordId、路径或正文 label。
- 备份调度器记录线程安全的成功/失败状态；失败日志只包含固定事件和异常类型，不输出可能携带路径或后端细节的异常正文。
- Compose 新增独立 metrics secret 与可选 `monitoring` profile。Prometheus 仅绑定宿主 loopback，在私有网络抓取 Cloud；Nginx 对 `/internal/` 固定 404，浏览器同源入口不能访问运维指标。
- 新增七项规则：目标不可用、alive 但 not-ready、5xx 比例、p95 延迟、备份连续失败、25 小时无成功备份和协作流 90% 饱和；CI 使用 `promtool` 检查规则与配置。
- 更新可观测性和生产部署文档，明确本地规则不是已经配置的外部通知、SLO、值班或集中日志服务。

验证：

- Cloud HTTP/备份/运行时/部署定向 19 项通过，覆盖运维凭据隔离、指标脱敏、备份成功/失败状态、私有端口、Nginx 阻断和七类告警规则。
- Compose 解析、监控 YAML 解析与 `git diff --check` 通过；本机 Docker daemon 未运行，真实 `promtool` 容器校验由 CI 门禁执行。

已知限制：尚未接入真实外部 Prometheus/托管监控、Alertmanager 通知接收器、集中日志、追踪、生产 SLO 和值班流程；监控数据仍为单实例进程级。崩溃收集继续属于第二阶段未完成范围；签名/公证、正式商业发行和签名更新自动发布按文末范围决策延期。

## 本轮交付：桌面发行门禁与更新链防回退基线

验收目标：更新清单、下载传输和替换回滚必须形成连续信任链；启用正式商业发行时，平台签名必须接入该信任链。旧签名清单不得通过“同版本不同 SHA”回放旧程序；正式发布不得回退到仓库旁的开发私钥，也不得在 tag 上生成看似正式的未签名 macOS 包。

已完成：

- 保留并强化现有 Ed25519 全清单签名、嵌入公钥、强制 SHA-256、临时下载、替换前后校验和 `.old` 回滚；更新 source 和最终 redirect 均只允许无内嵌凭据的 HTTPS。
- 清单限制 1 MiB、更新包限制 2 GiB，Content-Length 非法或流式实际大小越界均清理临时文件并失败；版本仅允许一至四段数字。
- 同版本 SHA 不同仍显示安全状态，但 `update_available=false`；任何变更必须提升版本号，旧的同版本签名清单不能诱导回退。
- `.dockerignore` 明确排除 `.release`，本地更新私钥不再进入 Docker build context；formal mode 必须显式提供 `OMNILIT_UPDATE_SIGNING_KEY_FILE`，不会使用忽略目录内的开发密钥。
- Windows 正式构建要求 Authenticode 证书，先 `signtool sign`/`verify`，再计算 SHA 并签更新清单；macOS 正式构建要求 hardened runtime codesign、Gatekeeper 验证、notarytool、staple 与 validate 后才打最终 zip。
- 原 macOS 未签名构建工作流改为仅手动触发，artifact 明确命名 `unsigned-smoke`，tag push 不再自动产出未签名发行外观包。

验证：

- 纯更新安全测试与原 UpdateCore 测试各 10 项通过，覆盖仓库清单签名、同版本重放拒绝、HTTP/重定向降级、大小上限、formal 平台签名顺序、私钥 build-context 排除和 tag 工作流限制。

已知限制：代码已具备 fail-closed 正式构建入口，但当前没有可用的 Windows/macOS 发行证书、Apple notarization profile、受保护 CI signing environment 或签名后的真机验收证据；因此不能宣称已完成签名发行。自动正式发布和跨平台自动更新仍被合规报告与外部凭据阻断。

## 范围决策：平台签名与公证延期到正式商业发行前

当前阶段不购买或配置 Windows/macOS 平台发行身份。第二阶段继续保留并验证已有 fail-closed 签名/
公证入口、更新清单签名、完整性校验、防回退、替换回滚和未签名产物标识，但不要求：

- 真实 Authenticode/Developer ID 证书和 Apple 公证凭据
- 受保护 CI 签名环境
- 真实签名、公证产物及其跨平台真机验收
- 已签名更新包的自动正式发布

这些事项不再计入第二阶段长期目标和里程碑 8 的完成度；它们成为面向公众正式分发桌面安装包之前
必须关闭的独立发行门禁。在门禁关闭前，Windows/macOS 产物只能作为明确标识的开发、测试或
`unsigned-smoke` 构建，不得宣称为正式商业发行。

## 本轮交付：隐私安全的崩溃诊断与显式授权上传

验收目标：React、WebEngine、Qt 与 Local Agent 故障必须能按来源分类并支持恢复；崩溃采集不得保存异常正文、堆栈、URL、用户路径、token 或文献内容；任何云端发送必须默认关闭，并由用户逐项明确授权。

已完成：

- 桌面端新增有界本地诊断 spool，覆盖 startup、Qt 主线程/工作线程、QML、WebEngine 与 Local Agent；每份报告只保存固定分类、异常类型、单向指纹和平台版本信息，最多保留 20 份。
- 旧 startup diagnostic 不再写完整 traceback、cwd、argv 或 QML 路径；全局主线程/工作线程异常钩子保持原默认处理，采集失败不阻断应用。
- React 新增 Error Boundary、全局 error/unhandledrejection 监听和当前标签页 `sessionStorage` spool；StrictMode 下监听器会正确清理，错误界面提供语义化重新加载入口。
- 权威共享 Schema 新增 `shareDiagnostics`、`DiagnosticReportCreateRequest` 与 `DiagnosticReceipt`；上传协议拒绝 message、stack、URL、path、任意 context 和额外字段。
- Cloud schema 升至 v2，新增无 actor/user/email 列的租户诊断表和 v1→v2 事务升级；`POST /v1/diagnostics` 必须认证且用户显式开启开关，并限制 24 小时 100 条、租户 500 条、保留 30 天。
- 诊断数据随账户导出，租户删除通过外键级联；网页在每次事件发生时重新读取当前会话授权，撤销授权立即停止发送。账户控制响应会同步写回当前标签页会话，无需重新登录。
- 新增 `crash-diagnostics.md`，明确当前 React 已接云端 opt-in，桌面报告仍只保存在本地且绝不隐式上传；外部事件平台、通知、SLO 和值班仍属于部署工作。

已知限制：桌面端尚未实现 Cloud 账户传输及“审阅后发送”界面，因此桌面本地诊断不会上传；真实外部崩溃聚合/告警服务、通知接收器和生产 SLO 尚未接入。该切片建立了采集、脱敏、授权、配额、保留、导出与删除边界，但不宣称外部事故响应体系已经上线。

验证：

- Python `unittest` 全量 610 项通过、127 项按当前默认解释器缺少可选 PySide6 条件跳过；Cloud/共享协议定向 36 项通过。
- Web 生成物检查、严格 TypeScript、55 项 Vitest 和 Vite 生产构建通过；React 监听清理、无 DOM 环境和诊断 sink 行为均有回归覆盖。
- 合规生成仍为 252 个组件、机器违规 0；正式发布继续被根 LICENSE、Cloud 哈希锁、native/Chromium/资产审查和真实签名身份阻断。

## 本轮交付：D — 研究工作空间、统计、AI 与业务设置共享页面

验收目标：完成剩余主要 React 业务页的纵向切片，同时保持浏览器独立运行、Qt 桌面可嵌入、业务规则不在 React 重复、AI 内容外发默认关闭、密钥不进入网页或设置存储。完成后按用户决策暂停 A、B、C、E、F。

已完成：

- 共享 schema 新增研究工作空间、统计桶、业务设置/更新请求、研究简报请求/结果 DTO，并同步生成 TypeScript 与 Python 类型和验证器。
- 新增纯 Python 共享业务层：从同一 LibraryState 和文献缓存投影最多四篇比较文献、统计聚合、修订式业务设置，以及可取消研究简报。
- Local Agent 新增 `/v1/workspace`、`/v1/statistics`、`/v1/settings/business` 和 `research.brief` 任务；API Client 新增对应强类型方法。
- React 新增研究工作空间、统计分析、AI 工作区和业务设置路由。比较/统计可通过 Platform Bridge 导出；主题、密度、减少动效、高对比度和启动页偏好可即时应用。
- AI 默认仅生成确定性本地证据编排并明确警告不是模型输出。远程模式要求内容外发授权、无内嵌凭据的 HTTPS 端点、模型 ID 和 Local Agent 环境密钥 `OMNILIT_AI_API_KEY`；密钥不持久化、不返回网页。
- 普通浏览器无服务时提供明确 fixture 演示，不宣称 Cloud 持久化。Qt 桌面新增 allowlist 共享业务 route 和研究工作空间导航，WebEngine 不可用或失败时回到稳定 QML 文献库。
- 新增 `desktop-web-shared-architecture-deferred-rebuild-roadmap.md`，基于当前真实进展将 A、B、C、E、F 重写为可在未来任意时刻独立恢复的目标、门禁、证据和回滚路线。

验证：

- Python `unittest` 全量 615 项通过，127 项按当前默认解释器缺少可选 PySide6 条件跳过；20 项研究业务、Local Agent HTTP/任务和桌面嵌入定向测试通过。
- Web 共享生成物检查、严格 TypeScript、59 项 Vitest 和 Vite 生产构建通过；新增页面具备语义化 loading/empty/error 边界，effect、AbortController、timer 与 AI 任务结果读取完成清理复核。
- Vite 仍报告 G6 主图 chunk 约 1.45 MB；这不阻断 D，但已进入后续重建路线的性能评估项。

已知限制与暂停决策：

- 普通浏览器的 D 页面尚无真实 Cloud 文献目录/统计/设置持久化；无 Local Agent 时仍是 fixture。该闭环归入暂缓 A。
- 桌面诊断审阅上传、最终产物合规、真实平台签名/公证、外部事故响应与恢复演练分别归入暂缓 B、C、E、F。
- 本轮到此停止，不自动实施任何暂缓目标。
