import { useMemo, useState } from "react"
import type { GraphData, GraphNode } from "@omnilit/shared-schema"

const TYPE_LABELS: Record<string, string> = {
  paper: "论文", citation: "引用文献", author: "作者", institution: "机构", topic: "主题", method: "方法",
  dataset: "数据集", result: "结果", model: "模型", metric: "指标", cluster: "聚合节点"
}

interface MindMapPartition { recordId: string; rootNodeId: string; nodeIds: string[] }
interface MindMapGroup { key: string; label: string; nodes: GraphNode[] }
interface MindMapBranch { key: string; root: GraphNode; groups: MindMapGroup[] }

export interface NodeMindMapProps {
  data: GraphData
  nodes: readonly GraphNode[]
  totalCount: number
  selectedNodeId?: string
  onSelect: (nodeId: string) => void
  onLoadMore?: () => void
}

function partitionsFrom(data: GraphData): MindMapPartition[] {
  const raw = data.metadata.graphPartitions
  if (!Array.isArray(raw)) return []
  return raw.flatMap((value) => {
    if (!value || typeof value !== "object") return []
    const item = value as Record<string, unknown>
    if (typeof item.recordId !== "string" || typeof item.rootNodeId !== "string" || !Array.isArray(item.nodeIds)) return []
    return [{ recordId: item.recordId, rootNodeId: item.rootNodeId, nodeIds: item.nodeIds.filter((id): id is string => typeof id === "string") }]
  })
}

export function buildMindMapBranches(data: GraphData, nodes: readonly GraphNode[]): MindMapBranch[] {
  const visible = new Map(nodes.map((node) => [node.id, node]))
  const allNodes = new Map(data.nodes.map((node) => [node.id, node]))
  const parsed = partitionsFrom(data)
  const partitions = parsed.length ? parsed : [{
    recordId: data.recordId,
    rootNodeId: data.nodes.find((node) => node.type === "paper")?.id ?? data.nodes[0]?.id ?? "",
    nodeIds: data.nodes.map((node) => node.id)
  }]
  const ownerCounts = new Map<string, number>()
  partitions.forEach((partition) => partition.nodeIds.forEach((nodeId) => ownerCounts.set(nodeId, (ownerCounts.get(nodeId) ?? 0) + 1)))
  return partitions.flatMap((partition) => {
    const root = allNodes.get(partition.rootNodeId)
    if (!root) return []
    const members = partition.nodeIds.flatMap((nodeId) => nodeId === root.id ? [] : visible.get(nodeId) ? [visible.get(nodeId) as GraphNode] : [])
    if (!visible.has(root.id) && members.length === 0) return []
    const groups = new Map<string, GraphNode[]>()
    members.forEach((node) => {
      const key = (ownerCounts.get(node.id) ?? 0) > 1 ? "shared" : node.type
      groups.set(key, [...(groups.get(key) ?? []), node])
    })
    return [{
      key: partition.recordId,
      root,
      groups: [...groups].map(([key, groupedNodes]) => ({ key, label: key === "shared" ? "文献交集" : TYPE_LABELS[key] ?? key, nodes: groupedNodes }))
    }]
  })
}

export function NodeMindMap({ data, nodes, totalCount, selectedNodeId, onSelect, onLoadMore }: NodeMindMapProps) {
  const branches = useMemo(() => buildMindMapBranches(data, nodes), [data, nodes])
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set())
  const toggleGroup = (key: string) => setCollapsedGroups((current) => {
    const next = new Set(current)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })
  return <section className="kg-node-list kg-mind-map" aria-labelledby="node-list-title">
    <div><div><p className="kg-kicker">XMind 式结构视图</p><h2 id="node-list-title">节点思维导图</h2></div><small>显示 {nodes.length.toLocaleString()} / {totalCount.toLocaleString()}</small></div>
    <ul className="kg-mind-roots">{branches.map((branch) => <li className="kg-mind-root" key={branch.key}>
      <button type="button" className="kg-mind-root-node" aria-pressed={selectedNodeId === branch.root.id} onClick={() => onSelect(branch.root.id)}><span className="kg-legend-dot kg-type-paper" /><span><strong>{branch.root.label}</strong></span></button>
      {branch.groups.length > 0 ? <ul className="kg-mind-groups">{branch.groups.map((group) => { const groupId = `${branch.key}:${group.key}`; const collapsed = collapsedGroups.has(groupId); return <li className="kg-mind-group" key={group.key} data-branch-type={group.key}><button type="button" className="kg-mind-branch-label" aria-expanded={!collapsed} onClick={() => toggleGroup(groupId)}><span>{group.label}</span><small>{group.nodes.length}</small><i aria-hidden="true">{collapsed ? "+" : "−"}</i></button>{!collapsed && <ul>{group.nodes.map((node) => <li key={`${branch.key}:${node.id}`}><button type="button" className="kg-mind-leaf" aria-pressed={selectedNodeId === node.id} onClick={() => onSelect(node.id)}><span className={`kg-legend-dot kg-type-${node.type}`} /><span>{node.label}<small>{TYPE_LABELS[node.type] ?? node.type} · 置信度 {Math.round((node.metrics?.confidence ?? 1) * 100)}%</small></span></button></li>)}</ul>}</li> })}</ul> : <p className="kg-mind-empty">当前筛选下没有邻居节点</p>}
    </li>)}</ul>
    {nodes.length < totalCount && onLoadMore && <button type="button" className="kg-load-more-nodes" onClick={onLoadMore}>再显示 {Math.min(100, totalCount - nodes.length)} 个节点</button>}
  </section>
}
