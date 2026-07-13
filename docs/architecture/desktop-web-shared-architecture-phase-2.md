# OmniLit 桌面与网页共享架构第二阶段长期目标

**建议文件路径：**

```text
docs/architecture/desktop-web-shared-architecture-phase-2.md
```

**文档状态：** 长期架构目标
**执行阶段：** 知识图谱重构稳定后的第二阶段
**当前前置任务：**

```text
docs/knowledge-graph-vision.md
```

------

# 一、文档目的

本文件定义 OmniLit 在完成现有 Qt/QML 知识图谱重构后，向“桌面端与网页端共享主要产品能力”的长期架构演进目标。

本目标不是一次性重写计划，也不是要求立即放弃 Qt/QML。

长期方向是：

> 保留现有 Qt 桌面投资，把已经验证的知识图谱和其他业务能力逐步迁移为可在桌面端与网页端共享的 React 产品前端；同时将桌面原生能力、本地数据处理、图计算、云端账户、同步和协作划分为清晰、稳定、可替换的架构边界。

最终应实现：

- 一套主要产品前端，多种运行环境
- 一套业务模型，本地与云端协同
- 桌面端继续具备强大的本地和离线能力
- 网页端支持账户、同步、分享和协作
- 现有 Qt/QML 投资得到保留
- 未来是否迁移 Tauri，可以基于真实数据决定
- 不因当前技术选型锁死长期商业化能力

------

# 二、当前阶段与执行优先级

## 2.1 当前唯一最高优先级

在本文件规定的第二阶段进入条件满足之前，Codex 应继续执行：

```text
docs/knowledge-graph-vision.md
```

当前阶段的主要目标是：

- 在现有 Qt/QML 桌面应用中，把知识图谱产品做正确
- 把核心工作流做完整
- 把数据、算法和交互做稳定
- 接入真实文献数据
- 建立性能和测试基线
- 形成可以作为未来网页版本行为基准的成熟产品

Codex 不应因未来 React、WebEngine、Tauri 或网页端规划而中断当前知识图谱交付。

## 2.2 第二阶段的定位

第二阶段不重新设计知识图谱产品。

第二阶段负责：

- 复用第一阶段的数据模型
- 复用第一阶段的图算法
- 复用第一阶段的业务规则
- 复用第一阶段的视觉设计令牌
- 复用第一阶段的用户工作流
- 复用第一阶段的测试数据和验收标准
- 将已经验证的能力迁移到共享前端架构

因此：

> 第一阶段解决“OmniLit 的知识图谱应该是什么”。
> 第二阶段解决“已经验证的产品能力如何在桌面端和网页端共享”。

------

# 三、总体愿景

OmniLit 最终应形成以下产品形态：

## 3.1 桌面端

桌面端重点提供：

- 本地文献库
- 本地 PDF 阅读与管理
- 文件夹和文件系统集成
- 批量导入
- 离线检索
- 本地全文索引
- 本地 AI 和图计算
- 大型任务
- 本地数据库
- 系统菜单、托盘、快捷键
- 高隐私研究环境
- 与云端的可选同步

## 3.2 网页端

网页端重点提供：

- 用户账户
- 云端文献库
- 在线知识图谱
- 跨设备访问
- 研究集合
- 分享
- 团队协作
- 云端计算
- 研究工作空间
- 权限管理
- 在线推荐
- 轻量阅读与批注

## 3.3 共享能力

桌面端与网页端应尽量共享：

- 文献搜索页面
- 文献详情页面
- 知识图谱页面
- 研究集合页面
- 研究工作空间
- 领域概览
- 时间演化
- 聚类与趋势分析
- 多论文比较
- AI 研究工作区
- 设计系统
- 数据类型
- API Client
- 错误模型
- 用户交互规则

------

# 四、长期目标架构

```text
┌──────────────────────────────────────────────────────┐
│                 共享 React 产品前端                  │
│                                                      │
│ 文献库 │ 搜索 │ 知识图谱 │ 阅读工作区 │ 分析 │ AI │ 账户 │
└─────────────────────────┬────────────────────────────┘
                          │
                   统一 API Client
                          │
             ┌────────────┴─────────────┐
             │                          │
      Platform Bridge               Cloud API
             │                          │
   ┌─────────┴──────────┐     ┌─────────┴───────────┐
   │                    │     │                     │
Browser Bridge       Qt Bridge 用户账户             云端数据
   │                    │     同步与协作             云端任务
   │              QWebChannel 权限与分享             云端推荐
   │                    │
   │          Qt/QML Desktop Shell
   │                    │
   │        ┌───────────┴────────────┐
   │        │                        │
   │   原生桌面能力             Local Agent
   │                                 │
   │                       Python / C++ / Database
   │
浏览器运行环境
```

该架构不是要求所有部分立即存在，而是所有后续重构都应逐步朝这一结构演进。

------

# 五、核心架构原则

## 5.1 React 逐步成为主要产品前端

第二阶段开始后，新迁移的业务页面原则上使用：

- React
- TypeScript
- 统一设计系统
- 统一状态和数据协议
- 统一 API Client

React 前端必须能够：

- 独立在普通浏览器中运行
- 独立开发和调试
- 独立构建
- 独立测试
- 部署为网页应用
- 被 Qt WebEngine 加载
- 不依赖 Qt 才能启动

React 不应被设计成只能运行在 Qt 内部的嵌入页面。

## 5.2 Qt/QML 转变为桌面平台层

Qt/QML 继续作为正式商业桌面容器，负责：

- 应用生命周期
- 主窗口
- 多窗口
- 原生菜单
- 系统托盘
- 全局快捷键
- 文件拖放
- 文件关联
- 文件选择
- 操作系统通知
- 自动更新
- 本地安全存储
- Qt WebEngine
- Python/C++ 进程管理
- Local Agent 生命周期
- 现有成熟 PDF 能力
- 未迁移的稳定 QML 页面

Qt/QML 不再无限扩展新的复杂业务页面。

原则是：

> 系统级能力保留在 Qt，产品级业务页面逐步进入共享 React 前端。

## 5.3 不允许业务组件直接依赖具体平台

React 产品组件不得直接使用：

```typescript
window.qt
window.qtBridge
window.__TAURI__
window.electron
```

也不得在大量组件中散落：

```typescript
if (isDesktop) {
  // ...
} else {
  // ...
}
```

所有平台差异必须通过 Platform Bridge 隔离。

## 5.4 本地能力与云端能力分离

本地能力包括：

- 本地文件
- PDF 解析
- 本地数据库
- 本地全文索引
- 本地图计算
- 离线任务
- 系统集成

云端能力包括：

- 用户账户
- 云同步
- 分享
- 团队协作
- 云端任务
- 云端数据
- 权限
- 多租户
- 推荐
- 在线审计

二者可以协作，但不能混为一个不可拆分的实现。

## 5.5 渐进迁移，不进行全量重写

任何时候都必须保证：

- 桌面应用可以启动
- 当前核心功能可用
- 新旧模块可以短期并存
- 每次修改可以独立测试
- 每轮迁移可以回退
- 不因重构阻塞产品交付
- 不因目录调整造成长期不可运行状态

------

# 六、第一阶段必须留下的迁移友好边界

虽然第二阶段尚未开始，但当前 `knowledge-graph-vision.md` 的实现应遵守以下边界。

## 6.1 图谱数据可序列化

至少建立以下结构：

- GraphNode
- GraphEdge
- GraphData
- GraphQuery
- GraphFilter
- GraphSelection
- GraphLayout
- GraphViewState
- GraphCluster
- GraphTimeline
- NodeDetails
- AnalysisResult
- TaskProgress
- GraphError

这些结构应可以序列化为 JSON。

不得只使用无法跨进程、跨语言、跨前端复用的 QML 临时对象。

## 6.2 QML 不直接访问数据库实现

推荐调用链：

```text
QML View
   ↓
Graph ViewModel / Controller
   ↓
Graph Service
   ↓
Repository / Database / Algorithms
```

禁止：

```text
QML
 ↓
直接拼接 SQL
 ↓
直接访问数据库表
```

## 6.3 图算法与 QML 分离

以下能力应位于 Python、C++ 或服务层：

- PageRank
- 社区发现
- 最短路径
- 共被引
- 文献耦合
- 关键词共现
- 桥接节点
- 主题增长
- 趋势分析
- 突现分析
- 时间演化
- 图谱抽样
- 图谱聚合

QML 只消费算法结果，不承载核心算法实现。

## 6.4 视觉与业务配置集中管理

集中管理：

- 节点类型
- 节点颜色
- 节点形状
- 节点大小规则
- 边类型
- 边颜色
- 图例
- 缩放显示规则
- 聚类配色
- 动画时间
- 主题
- 字体
- 间距
- 状态样式

这些规则将来应能够映射到 React 设计令牌。

## 6.5 建立固定测试数据集

至少包括：

- 100 节点小型图
- 1,000 节点中型图
- 5,000 节点大型图
- 10,000 节点压力图
- 无边图
- 缺失数据图
- 多聚类图
- 时间演化图
- 多类型语义实体图
- 异常关系图
- 重复节点和实体消歧测试图

这些数据将作为未来 QML 与 React 行为一致性的基准。

------

# 七、第二阶段进入条件

只有满足以下条件后，Codex 才可以将第二阶段列为主要执行目标。

## 7.1 产品条件

知识图谱已经具备：

1. 可用的图谱探索视图。
2. 文献、作者、机构、主题等核心节点。
3. 引用、被引、作者、机构、主题等核心关系。
4. 搜索、筛选、选择和节点展开。
5. 图谱与文献详情联动。
6. 至少一种领域或主题概览。
7. 至少一种时间演化能力。
8. 至少一种聚类或趋势分析。
9. 保存和恢复图谱状态。
10. 基于真实数据运行。
11. 完整的加载、空白和错误状态。
12. 核心工作流经过实际使用验证。

## 7.2 工程条件

知识图谱已经具备：

- 明确的数据协议
- Graph Service 或等价服务层
- 图算法与 QML 解耦
- 集中管理的视觉配置
- 固定测试数据
- 自动化测试
- 性能基准
- 错误模型
- 任务进度模型
- 架构说明文档

## 7.3 稳定性条件

- 当前桌面应用可以稳定启动。
- 知识图谱不存在阻断用户使用的严重缺陷。
- 主要交互方式不再频繁发生根本变化。
- 产品结构可以作为 React 迁移的行为基准。
- 数据模型已经足够稳定。
- 主要图算法结果具有可解释性。
- 性能问题已经有明确基线。

如果条件未满足，应继续完成第一阶段，而不是提前迁移前端。

------

# 八、目标仓库结构

Codex 应逐步将项目演进为类似以下结构。

不得为了目录美观一次性移动整个仓库。

```text
OmniLit/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   ├── public/
│   │   ├── tests/
│   │   ├── index.html
│   │   ├── package.json
│   │   └── vite.config.ts
│   │
│   └── desktop-qt/
│       ├── qml/
│       ├── cpp/
│       ├── resources/
│       ├── web/
│       ├── tests/
│       └── CMakeLists.txt
│
├── packages/
│   ├── ui/
│   ├── design-tokens/
│   ├── shared-schema/
│   ├── api-client/
│   ├── platform-bridge/
│   ├── knowledge-graph/
│   ├── literature-library/
│   ├── literature-search/
│   ├── research-workspace/
│   ├── paper-reader/
│   ├── analytics/
│   ├── ai-workspace/
│   └── shared-utils/
│
├── services/
│   ├── local-agent/
│   ├── cloud-api/
│   ├── graph-engine/
│   ├── ingestion-worker/
│   ├── recommendation-engine/
│   └── shared-python/
│
├── schemas/
│   ├── openapi/
│   ├── json-schema/
│   └── generated/
│
├── docs/
│   ├── knowledge-graph-vision.md
│   ├── architecture/
│   │   ├── desktop-web-shared-architecture-phase-2.md
│   │   ├── platform-bridge.md
│   │   ├── local-agent.md
│   │   └── architecture-decisions/
│   ├── api/
│   ├── migration/
│   ├── security/
│   └── performance/
│
├── tests/
│   ├── fixtures/
│   │   ├── graphs/
│   │   ├── papers/
│   │   └── api/
│   ├── contract/
│   ├── integration/
│   ├── end-to-end/
│   └── performance/
│
├── tools/
│   ├── codegen/
│   ├── build/
│   ├── packaging/
│   └── license-audit/
│
└── workspace configuration
```

目录名称可以根据现有项目调整，但模块边界不得丢失。

------

# 九、各模块职责

## 9.1 `apps/web`

负责网页应用入口：

- 浏览器路由
- 应用启动
- 认证入口
- Browser Platform Bridge 初始化
- Cloud API 配置
- 网页部署
- 网页错误监控
- 网页性能监控
- 浏览器端功能降级

业务代码应尽量位于共享 `packages` 中，而不是堆积在 `apps/web`。

## 9.2 `apps/desktop-qt`

负责桌面应用入口：

- Qt/QML Shell
- C++ 桥接
- Qt WebEngine
- QWebChannel
- 原生窗口
- 原生菜单
- 系统托盘
- 文件系统集成
- Local Agent 生命周期
- 桌面安装与更新
- 未迁移的 QML 页面

其中 `web/` 只保存或打包共享 React 构建产物，不维护另一套独立前端源码。

## 9.3 `packages/ui`

共享 UI 组件库：

- Button
- Input
- Select
- Dialog
- Drawer
- Tabs
- Tooltip
- Toolbar
- SplitPane
- ContextMenu
- EmptyState
- ErrorState
- LoadingState
- VirtualList
- DataTable
- CommandPalette

共享 UI 组件不得直接访问 Qt、文件系统或云端 API。

## 9.4 `packages/design-tokens`

集中管理：

- 颜色
- 字体
- 间距
- 圆角
- 阴影
- 层级
- 动画
- 深色主题
- 浅色主题
- 图谱节点颜色
- 图谱关系颜色
- 聚类配色
- 可访问性对比度

第一阶段 QML 中已经验证的视觉规则应迁移为统一令牌，而不是重新设计。

## 9.5 `packages/shared-schema`

保存共享类型：

- Paper
- Author
- Institution
- Venue
- Topic
- Collection
- Workspace
- Annotation
- GraphNode
- GraphEdge
- GraphQuery
- GraphFilter
- GraphViewState
- AnalysisResult
- Task
- TaskProgress
- APIError
- User
- Permission
- SyncState

共享类型应由 OpenAPI、JSON Schema 或其他权威协议约束或生成。

禁止不同模块分别手写不同含义的 `Paper` 或 `GraphNode`。

## 9.6 `packages/api-client`

统一封装：

- Cloud API
- Local Agent API
- 请求超时
- 请求取消
- 重试
- 分页
- 上传
- 下载
- 认证
- 错误转换
- 长任务状态
- WebSocket/SSE
- API 版本
- 缓存策略

业务模块不得绕过统一 API Client 直接散落调用后端。

## 9.7 `packages/platform-bridge`

保存平台抽象：

```text
PlatformBridge
BrowserPlatformBridge
QtWebChannelPlatformBridge
MockPlatformBridge
```

未来达到迁移条件后再增加：

```text
TauriPlatformBridge
```

## 9.8 `packages/knowledge-graph`

负责共享知识图谱产品能力：

- 图谱页面
- 图谱状态
- 图谱工具栏
- 图例
- 筛选器
- 节点详情
- 文献列表联动
- 领域概览
- 时间轴
- 聚类结果
- 趋势结果
- 图谱导出
- 图谱视图保存
- GraphRenderer 接口
- 第一图谱引擎实现
- 图谱交互测试

不负责：

- 直接访问数据库
- PDF 解析
- 运行大型图算法
- Qt 窗口操作
- 用户认证实现

## 9.9 `services/local-agent`

负责桌面本地服务：

- PDF 解析
- 文献批量导入
- OCR
- 全文提取
- 本地索引
- 向量生成
- 图算法
- 本地数据库访问
- 大文件读写
- 后台任务
- 任务取消
- 进度通知
- 错误恢复

## 9.10 `services/cloud-api`

负责：

- 用户账户
- 认证
- 租户
- 权限
- 云同步
- 分享
- 团队协作
- 云端数据
- 云端任务
- 审计日志
- 数据导出
- 数据删除
- API 版本

## 9.11 `services/graph-engine`

负责可复用图分析：

- PageRank
- 社区发现
- 最短路径
- 共被引
- 文献耦合
- 关键词共现
- 作者合作
- 机构合作
- 主题聚类
- 桥接节点
- 趋势
- 突现
- 时间演化
- 图谱抽样
- 聚合
- 推荐阅读路径

第一阶段已有实现应优先封装和迁移，不应无理由重写。

## 9.12 `services/ingestion-worker`

负责：

- 文献元数据摄取
- PDF 导入
- 文本提取
- 实体抽取
- 实体消歧
- 数据清洗
- 语义结构化
- 索引建立
- 图谱增量更新

## 9.13 `schemas`

作为跨语言数据协议的权威来源：

- OpenAPI
- JSON Schema
- TypeScript 类型
- Python 模型
- 版本记录
- 兼容说明

## 9.14 `tests`

覆盖：

- 合约测试
- Local Agent 集成测试
- Qt 与 React 集成测试
- 浏览器端到端测试
- 桌面端到端测试
- QML 与 React 功能对照测试
- 图谱性能测试
- 数据迁移测试
- 云同步冲突测试
- 安全边界测试

------

# 十、统一数据协议

## 10.1 协议权威来源

必须确定唯一权威来源。

推荐：

```text
OpenAPI / JSON Schema
        ↓
TypeScript 类型
Python 模型
测试数据验证器
```

不得以某个 QML 对象或某个 TypeScript 接口作为无法验证的事实标准。

## 10.2 协议版本

协议必须支持：

- 明确版本
- 向后兼容
- 废弃字段周期
- 数据迁移
- 未知字段容忍策略
- 错误版本提示

## 10.3 图谱协议

至少覆盖：

```typescript
interface GraphNode {
  id: string
  type: string
  label: string
  attributes: Record<string, unknown>
  metrics?: Record<string, number>
}

interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  directed: boolean
  weight?: number
  attributes?: Record<string, unknown>
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  metadata?: Record<string, unknown>
}
```

实际结构可根据项目调整，但必须保持：

- 可序列化
- 可版本化
- 可跨语言
- 不包含渲染器私有对象
- 不依赖 QML 或 G6 内部结构

------

# 十一、Platform Bridge

## 11.1 目标接口

```typescript
export interface PlatformBridge {
  readonly platform:
    | "browser"
    | "qt-desktop"
    | "tauri-desktop"

  openLocalFiles(
    options?: OpenFileOptions
  ): Promise<SelectedLocalFile[]>

  saveFile(
    options: SaveFileOptions
  ): Promise<SaveFileResult>

  openExternalUrl(url: string): Promise<void>

  getAppInfo(): Promise<AppInfo>

  revealInFileManager(path: string): Promise<void>

  getLocalServiceStatus(): Promise<LocalServiceStatus>

  subscribeTaskProgress(
    listener: (event: TaskProgressEvent) => void
  ): () => void
}
```

## 11.2 Browser Bridge

负责浏览器能力：

- 浏览器文件选择
- 下载文件
- 打开外部链接
- 返回网页版本信息
- 对不支持的桌面能力返回明确错误
- 不伪造桌面路径或桌面行为

## 11.3 Qt Bridge

负责：

- 文件选择
- 保存路径
- 打开系统浏览器
- 窗口命令
- 应用版本
- 系统通知
- 本地服务状态
- 原生菜单事件

## 11.4 Mock Bridge

用于：

- 单元测试
- Storybook 或组件预览
- 浏览器开发
- 自动化场景
- 错误和取消状态模拟

------

# 十二、QWebChannel 使用边界

QWebChannel 适合：

- 轻量命令
- 事件
- 应用状态
- 文件选择结果
- 小型参数
- 本地服务状态
- 原生菜单通知

QWebChannel 不适合：

- 大型图谱
- PDF 二进制
- 超长文本
- 高频数据流
- 大型查询结果
- 长时间算法执行
- 批量数据库传输

大型数据统一通过：

- Local Agent HTTP
- WebSocket
- SSE
- 文件引用
- 分块请求

------

# 十三、Local Agent

## 13.1 生命周期

Local Agent 应由 Qt 桌面端负责：

- 启动
- 健康检查
- 会话认证
- 重启
- 关闭
- 异常恢复
- 版本兼容检查

## 13.2 安全要求

Local Agent 必须：

- 只监听本机地址
- 使用随机会话令牌或等价机制
- 限制允许来源
- 验证所有输入
- 防止目录遍历
- 限制文件类型
- 限制文件大小
- 限制并发任务
- 支持超时
- 支持取消
- 日志脱敏
- 不允许任意命令执行
- 不允许任意路径读取

## 13.3 任务模型

长任务统一支持：

- taskId
- type
- status
- progress
- message
- createdAt
- startedAt
- finishedAt
- error
- cancel
- result reference

任务状态至少包括：

```text
queued
running
succeeded
failed
cancelled
```

------

# 十四、知识图谱共享模块

## 14.1 渲染器抽象

业务逻辑不得完全绑定某一图谱库。

```typescript
export interface GraphRenderer {
  mount(container: HTMLElement): void
  setData(data: GraphData): void
  updateData(change: GraphDataChange): void
  setSelection(selection: GraphSelection): void
  setFilters(filters: GraphFilters): void
  focusNode(nodeId: string): void
  fitView(options?: FitViewOptions): void
  exportImage(options: ExportOptions): Promise<Blob>
  destroy(): void
}
```

## 14.2 第一实现

第一阶段 Web 图谱引擎建议只选择一个。

推荐：

```text
G6GraphRenderer
```

当基准测试证明必要时，再评估：

```text
SigmaGraphRenderer
```

禁止第一轮同时维护两套图谱引擎。

## 14.3 计算与渲染分离

以下能力不应直接放在 React 主线程：

- 社区发现
- PageRank
- 最短路径
- 共被引
- 文献耦合
- 关键词共现
- 大型布局
- 图谱抽样
- 图谱聚合

根据规模使用：

- Web Worker
- Local Agent
- Cloud Graph Engine

## 14.4 图谱状态

统一管理：

- 当前查询
- 当前中心节点
- 节点和边
- 选中状态
- 悬停状态
- 筛选条件
- 布局
- 时间范围
- 聚类模式
- 缩放和视口
- 详情面板
- 操作历史
- 保存视图
- 分析结果

不得让多个组件维护互相冲突的状态副本。

------

# 十五、迁移实施阶段

## 阶段 A：冻结第一阶段行为基准

完成：

- 记录 QML 知识图谱功能
- 保存典型截图
- 保存测试数据
- 保存性能数据
- 保存交互清单
- 保存视觉规则
- 保存错误和空白状态
- 建立验收脚本

目的：

> React 迁移以成熟行为为基准，而不是重新猜测产品需求。

## 阶段 B：抽取共享协议

完成：

- Graph DTO
- Paper DTO
- Task DTO
- Error DTO
- GraphViewState
- API 版本
- JSON Schema/OpenAPI
- TypeScript 类型生成
- Python 模型映射

此阶段不改变主要 UI。

## 阶段 C：建立独立 Web 应用

完成：

- React
- TypeScript
- Vite
- 基础路由
- 设计令牌
- API Client
- Platform Bridge
- Mock Bridge
- 测试框架
- 独立浏览器运行入口

验收：

- 不启动 Qt 也能运行
- 不连接真实后端也能用固定测试数据验证
- 不直接依赖 Qt 对象
- 类型检查通过

## 阶段 D：迁移知识图谱为第一个共享模块

完成：

- 图谱画布
- 图例
- 筛选
- 节点选中
- 节点展开
- 详情面板
- 文献列表联动
- 时间轴
- 聚类结果
- 趋势结果
- 保存视图
- 导出
- 错误和空白状态

验收：

- 浏览器可以独立运行
- 使用真实 Graph DTO
- 主要行为与 QML 基准一致
- 有自动化测试
- 性能达到基线

## 阶段 E：Qt WebEngine 集成

完成：

- Qt WebEngine 容器
- 本地前端资源加载
- Qt Bridge
- QWebChannel
- Platform Bridge Qt 实现
- Local Agent 状态接入
- 桌面开发调试流程
- 构建和打包流程

验收：

- 同一 React 图谱运行在浏览器和桌面端
- 外部链接交给系统浏览器
- 高权限桥接页面不加载任意远程网页
- 本地资源可离线运行

## 阶段 F：双版本并行验证

短期保留：

- QML 稳定版
- React 新版

通过功能开关选择。

对比：

- 数据一致性
- 图算法结果
- 交互行为
- 导出结果
- 内存
- 启动速度
- 图谱帧率
- 崩溃恢复
- 用户体验

并行期不得无限延长。

React 版本验收后：

- 新功能只进入 React
- QML 图谱进入维护状态
- 确认回退机制后再删除旧实现

## 阶段 G：网页端上线

完成：

- 用户账户
- Cloud API
- 云端图谱查询
- 图谱视图保存
- 研究集合
- 云同步
- 分享
- 权限
- 基础团队协作
- 云端任务
- 监控
- 安全策略

## 阶段 H：迁移其他业务页面

建议顺序：

1. 文献搜索
2. 文献详情
3. 研究集合
4. 研究工作空间
5. 统计分析
6. AI 工作区
7. 账户
8. 云同步
9. 团队协作
10. 设置中的业务页面

每次只迁移一个可独立验收的纵向切片。

## 阶段 I：商用工程化

完成：

- Windows 代码签名
- macOS 签名和公证
- 自动更新
- 崩溃收集
- 日志脱敏
- SBOM
- 第三方许可证清单
- 依赖漏洞扫描
- 安全更新策略
- 数据备份
- 数据恢复
- 用户数据导出
- 用户数据删除
- API 审计
- 隐私设置
- 企业部署准备

## 阶段 J：桌面容器评估

达到条件后，才评估 Tauri。

比较：

- 启动时间
- 内存
- 安装包大小
- WebGL 一致性
- PDF 能力
- 自动更新
- 本地服务通信
- 多平台差异
- 安全模型
- 维护成本
- Qt 许可成本
- Rust 团队能力
- 迁移风险

评估完成前：

> Qt 仍是正式桌面容器。

------

# 十六、仓库迁移顺序

推荐顺序：

```text
shared-schema
    ↓
Graph DTO 与测试数据
    ↓
api-client
    ↓
platform-bridge
    ↓
独立 web 应用
    ↓
knowledge-graph 共享模块
    ↓
Qt WebEngine 集成
    ↓
Local Agent 标准化
    ↓
Cloud API
    ↓
其他业务模块
```

规则：

1. 不一次性移动全部目录。
2. 不创建大量空包。
3. 只有实际迁移功能时才建立包。
4. 移动文件时保留兼容入口。
5. 每次迁移后项目必须可运行。
6. 新旧结构允许短期并存。
7. 模块迁移完成后再清理旧代码。
8. 不为形式上的 monorepo 美观牺牲稳定性。

------

# 十七、测试策略

## 17.1 单元测试

覆盖：

- 数据转换
- Graph DTO 验证
- API 错误转换
- Platform Bridge
- 图谱状态
- 筛选逻辑
- 任务状态
- 权限判断

## 17.2 合约测试

验证：

- Cloud API
- Local Agent
- Graph Engine
- TypeScript 类型
- Python 模型
- 错误结构
- 版本兼容

## 17.3 集成测试

验证：

- React 与 Local Agent
- React 与 Qt Bridge
- Qt 与 Local Agent
- 数据库与图服务
- 图谱查询和详情
- 长任务取消
- 本地与云端切换

## 17.4 端到端测试

至少覆盖：

- 搜索论文
- 打开图谱
- 展开节点
- 使用筛选器
- 查看详情
- 切换时间范围
- 保存视图
- 导出图片
- 导入 PDF
- 查看任务进度
- 取消任务
- 登录和同步
- 网页分享

## 17.5 对照测试

QML 与 React 图谱应使用相同测试数据验证：

- 节点数量
- 边数量
- 节点类型
- 关系类型
- 聚类结果
- 时间轴范围
- 筛选结果
- 节点详情
- 保存视图
- 导出结果

------

# 十八、性能基线

## 18.1 图谱规模

至少测试：

- 100 节点
- 1,000 节点
- 5,000 节点
- 10,000 节点

超过合理可视范围时，不强制全部显示。

应使用：

- 按需加载
- 聚类
- 聚合节点
- 语义缩放
- 标签优先级
- 抽样
- Web Worker
- 后端预计算
- 分层细节

## 18.2 前端指标

记录：

- 首次加载时间
- 页面切换时间
- 图谱可交互时间
- 图谱帧率
- 内存占用
- React 重渲染
- 筛选响应时间
- 搜索响应时间
- 导出时间
- 时间轴切换时间

## 18.3 桌面指标

记录：

- 冷启动
- 热启动
- Qt WebEngine 初始化
- Local Agent 启动
- 空闲内存
- 图谱内存
- 安装包大小
- 更新包大小
- WebEngine 崩溃恢复
- Local Agent 崩溃恢复

## 18.4 性能决策原则

不得因为某个库“理论上更快”而迁移。

所有性能决策必须基于：

- 固定数据集
- 固定设备
- 固定操作流程
- 可重复测量
- 记录的基准结果

------

# 十九、安全要求

## 19.1 Qt WebEngine

必须：

- 默认加载本地打包资源
- 严格限制远程导航
- 外部链接交给系统浏览器
- 对高权限页面设置严格 CSP
- QWebChannel 只暴露最小接口
- 不允许任意本地文件访问
- 验证所有参数
- 对高风险操作进行权限检查
- 不让不可信内容获得桌面桥接权限

## 19.2 Local Agent

必须：

- 只监听本机
- 具备会话认证
- 限制来源
- 参数验证
- 文件路径验证
- 文件类型和大小限制
- 并发限制
- 超时
- 取消
- 资源限制
- 日志脱敏
- 错误信息不暴露敏感路径和密钥

## 19.3 Cloud API

必须：

- 身份认证
- 租户隔离
- 权限检查
- 限流
- 审计日志
- 加密传输
- 敏感数据加密存储
- 文件安全检查
- API 版本管理
- 数据备份
- 灾难恢复
- 用户数据导出
- 用户数据删除

## 19.4 用户研究数据

必须提供明确控制：

- 是否上传本地 PDF
- 是否同步批注
- 是否同步全文
- 是否使用云端 AI
- 是否保留云端任务数据
- 是否允许团队访问
- 是否允许分享链接
- 删除账户时如何处理数据

------

# 二十、商用与许可证管理

项目应建立持续许可证管理机制。

至少包括：

- Qt 许可策略
- Chromium 第三方许可证
- npm 依赖许可证
- Python 依赖许可证
- C++ 依赖许可证
- 图谱库许可证
- 字体和图标许可证
- SBOM
- THIRD_PARTY_NOTICES
- 依赖版本和来源记录
- 商用限制审查
- 发布包许可证归档

不得仅在第一次发布时检查许可证。

每次正式发布都应自动生成或验证：

- 依赖清单
- 许可证清单
- 漏洞扫描结果
- SBOM
- 版权声明

------

# 二十一、可观测性与故障恢复

## 21.1 日志

日志应：

- 结构化
- 分级
- 可关联任务 ID
- 可关联请求 ID
- 不记录 API Key
- 不记录密码
- 不记录完整敏感文献内容
- 不记录未经处理的用户路径

## 21.2 崩溃和错误

应区分：

- React 页面错误
- WebEngine 渲染进程错误
- Qt 主进程错误
- Local Agent 错误
- Cloud API 错误
- 图算法错误
- 数据库错误
- 同步错误

## 21.3 恢复策略

必须支持：

- 页面重新加载
- WebEngine 重新初始化
- Local Agent 重启
- 未完成任务恢复或明确失败
- 图谱视图自动保存
- 用户操作草稿保存
- 同步冲突提示
- 数据库迁移失败回滚

------

# 二十二、数据同步与冲突策略

桌面端和网页端共享后，需要明确数据归属。

至少区分：

- 仅本地数据
- 仅云端数据
- 已同步数据
- 待同步数据
- 冲突数据
- 删除中的数据

同步对象可能包括：

- 文献记录
- 研究集合
- 图谱视图
- 标签
- 笔记
- 批注
- 阅读状态
- 搜索历史
- 工作空间
- 分享权限

冲突不得静默覆盖。

应根据数据类型使用：

- 最后写入
- 字段级合并
- 版本号
- 操作日志
- 用户选择
- 保留副本

具体策略必须写入文档和测试。

------

# 二十三、无障碍与国际化

共享前端应逐步支持：

- 键盘导航
- 焦点状态
- 屏幕阅读器标签
- 合理颜色对比
- 不仅依赖颜色表达节点类型
- 可缩放文字
- 动效减弱设置
- 中文与英文界面
- 日期和数字本地化
- 长标题和多语言排版

图谱至少提供：

- 可搜索列表替代入口
- 节点详情文本
- 图例
- 键盘定位
- 筛选状态描述
- 分析结果文本解释

------

# 二十四、Codex 每轮持续执行规则

Codex 每次执行本长期目标时，只选择一个可独立交付的纵向切片。

## 24.1 开始前

Codex 必须：

1. 阅读当前架构文档。
2. 确认是否已经满足第二阶段进入条件。
3. 阅读相关代码和测试。
4. 确认当前完成阶段。
5. 检查是否已有相同类型、接口或组件。
6. 找到本轮最有价值的最小目标。
7. 明确验收条件。
8. 明确回退方式。
9. 限制无关修改范围。

## 24.2 实施中

Codex 必须：

1. 优先复用已有代码。
2. 优先建立兼容层。
3. 先定义接口和数据，再替换实现。
4. 使用真实入口接入功能。
5. 同时处理加载、空白、错误和取消状态。
6. 补充测试。
7. 更新文档。
8. 保持桌面应用可运行。
9. 保持网页应用可运行。
10. 保持迁移可回退。

## 24.3 每轮结束时

Codex 应输出：

- 本轮目标
- 完成内容
- 修改的主要文件
- 新增或调整的接口
- 数据协议变化
- 桌面端影响
- 网页端影响
- 本地服务影响
- 云端影响
- 测试结果
- 性能影响
- 安全影响
- 兼容性影响
- 已知限制
- 回退方式
- 下一轮最高优先级

------

# 二十五、Codex 禁止事项

Codex 不得：

- 在第一阶段未完成时强行启动全面 React 迁移
- 一次性重写全部 QML 页面
- 同时迁移多个完整业务模块
- 让 React 组件直接依赖 QWebChannel
- 在组件中散落平台判断
- 通过 QWebChannel 传输大型图谱或 PDF
- 同时引入多个同类状态管理框架
- 第一轮同时实现 G6 和 Sigma.js
- 未经测试就删除 QML 稳定版
- 为目录整洁移动全部代码
- 创建大量空包
- 复制两套相同业务逻辑
- 让 QML 或 React 直接拼接 SQL
- 将云端认证逻辑放入 Qt 组件
- 使用任意远程页面获得高权限桥接
- 在没有基准测试时声称新架构更快
- 在未满足条件时迁移 Tauri
- 为追求技术新颖性破坏正式发布能力
- 删除现有功能却不给出等价替代
- 留下无法构建、无法启动或无法测试的仓库

------

# 二十六、每个模块的完成定义

一个共享模块只有满足以下条件才算完成：

- 浏览器中独立运行
- Qt 桌面端正常运行
- 不直接依赖平台全局对象
- 使用统一协议
- 使用统一 API Client
- 有单元测试
- 有集成测试
- 有端到端测试
- 有加载状态
- 有空白状态
- 有错误状态
- 长任务可取消
- 平台差异有明确降级
- 不破坏原有桌面功能
- 性能达到基线
- 安全边界清楚
- 文档完整
- 有回退方案

------

# 二十七、第二阶段里程碑验收

## 里程碑 1：共享协议建立

验收：

- Graph DTO 有权威定义
- TypeScript 和 Python 模型一致
- 固定测试数据通过验证
- 协议版本机制存在
- 现有 QML 仍可使用

## 里程碑 2：独立 Web 前端建立

验收：

- React 应用可独立运行
- Browser Bridge 可用
- API Client 可用
- 设计令牌可用
- 类型检查和测试通过

## 里程碑 3：知识图谱 Web 版完成

验收：

- 浏览器可完成核心图谱工作流
- 与 QML 基准基本一致
- 使用真实服务
- 性能达到要求
- 错误、空白、加载完整

## 里程碑 4：知识图谱嵌入 Qt

验收：

- 同一代码运行于 Qt
- Qt Bridge 可用
- Local Agent 可用
- 离线资源可加载
- 安全边界通过检查

## 里程碑 5：QML 图谱退出主开发

验收：

- React 版本稳定
- 对照测试通过
- 回退路径存在
- 新功能不再进入 QML 版本
- 旧版本安全归档或删除

## 里程碑 6：网页端正式上线

验收：

- 账户可用
- 云端数据可用
- 图谱保存和同步可用
- 分享和权限可用
- 监控、安全和备份可用

## 里程碑 7：主要业务页面共享

验收：

- 文献搜索、详情、集合和工作空间至少完成共享
- 桌面和网页不再重复维护主要业务逻辑
- 平台差异集中在 Bridge 和服务层

## 里程碑 8：商业发布体系成熟

验收：

- 自动化发布
- 签名与公证
- 更新机制
- 崩溃监控
- SBOM
- 许可证清单
- 隐私和数据治理
- 备份与恢复

------

# 二十八、Tauri 的最终评估条件

只有同时满足以下条件后，才允许正式建立 Tauri 原型：

- 主要业务页面已经迁移到 React
- QML 只剩平台能力
- Platform Bridge 已稳定
- Local Agent 已稳定
- 网页端已经上线
- Qt WebEngine 成本形成真实问题
- 团队具备 Rust 维护能力
- 有明确迁移预算
- 有性能和包体基准
- 有桌面端回归测试

Tauri 评估结果可以是：

- 继续 Qt
- 部分产品使用 Tauri
- 新版桌面端迁移 Tauri
- Qt 与 Tauri 长期并存

不得预设 Tauri 必然优于 Qt。

------

# 二十九、最终完成定义

当 OmniLit 达到以下状态时，本长期目标才算基本完成：

1. `knowledge-graph-vision.md` 已完成并稳定。
2. 知识图谱数据、算法、规则与 QML 渲染层分离。
3. React 知识图谱可独立在浏览器运行。
4. 同一 React 知识图谱可运行在 Qt 桌面端。
5. 桌面端和网页端使用统一协议。
6. 桌面端和网页端使用统一 API Client。
7. 产品组件不直接依赖 Qt。
8. Qt/QML 主要负责桌面和原生能力。
9. Local Agent 负责大型本地任务。
10. Cloud API 负责账户、同步和协作。
11. 知识图谱和主要业务页面实现共享。
12. 用户可以安全选择本地、云端或混合工作方式。
13. 桌面端和网页端具有独立可靠的发布流程。
14. 商用许可、隐私、安全和依赖得到持续管理。
15. QML 旧图谱已安全退出主开发。
16. Tauri 是否采用可以基于真实数据决定。

最终状态应体现：

> 一套共享产品前端，支持桌面与网页；
> 一套稳定业务协议，连接本地与云端；
> Qt 保留成熟桌面能力，React 承载共享产品体验；
> Python 和 C++ 继续提供高价值计算能力；
> OmniLit 可以持续商业化，而不被单一前端框架锁定。

------

# 三十、当前立即执行指令

在第二阶段进入条件满足前，Codex 的执行原则是：

```text
继续完成 knowledge-graph-vision.md
```

同时只遵守以下五项未来迁移约束：

1. 图谱数据必须可序列化。
2. 图算法必须与 QML 分离。
3. QML 不得直接依赖数据库实现。
4. 图谱样式和业务规则必须集中管理。
5. 建立固定图谱测试数据和性能基线。

除上述边界外，不提前开展：

- 全面 React 迁移
- Qt WebEngine 大规模集成
- Tauri 迁移
- Electron 迁移
- 完整 monorepo 重排
- 网页端全面开发

只有知识图谱产品真正稳定后，第二阶段才正式启动。