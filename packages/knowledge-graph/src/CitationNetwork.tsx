import { useMemo } from "react"
import type { CSSProperties } from "react"
import type { GraphData, LiteratureRow } from "@omnilit/shared-schema"

interface CitationNode { row: LiteratureRow; x: number; y: number }
interface CitationLink { id: string; source: CitationNode; target: CitationNode }
interface CitationNetworkData { nodes: CitationNode[]; links: CitationLink[] }

export interface CitationNetworkProps {
  data: GraphData
  rows: LiteratureRow[]
  loading: boolean
  error: string
  selectedNodeId?: string
  onSelect: (nodeId: string) => void
}

export function buildCitationNetwork(data: GraphData, rows: LiteratureRow[]): CitationNetworkData {
  const nodes = rows.map((row, index): CitationNode => {
    if (rows.length === 1) return { row, x: 50, y: 50 }
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / rows.length
    return { row, x: 50 + Math.cos(angle) * 38, y: 50 + Math.sin(angle) * 34 }
  })
  const byId = new Map(nodes.map((node) => [node.row.nodeId, node]))
  const links = data.edges.flatMap((edge) => {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target || !/(cit|referenc)/i.test(edge.type)) return []
    return [{ id: edge.id, source, target }]
  })
  return { nodes, links }
}

export function CitationNetwork({ data, rows, loading, error, selectedNodeId, onSelect }: CitationNetworkProps) {
  const network = useMemo(() => buildCitationNetwork(data, rows), [data, rows])
  return <section className="kg-literature kg-citation" aria-labelledby="literature-list-title">
    <div><p className="kg-kicker">图谱 ↔ 文献</p><h2 id="literature-list-title">引用关系网络</h2></div>
    {loading && <p role="status">正在更新引用关系网络…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && rows.length === 0 && <p role="status">当前可见节点中没有关联文献。</p>}
    {!loading && !error && rows.length > 0 && <div className="kg-citation-stage" aria-label={`${rows.length} 篇文献、${network.links.length} 条引用关系`}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="kg-citation-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" /></marker></defs>{network.links.map((link) => <line key={link.id} x1={link.source.x} y1={link.source.y} x2={link.target.x} y2={link.target.y} markerEnd="url(#kg-citation-arrow)" />)}</svg>
      {network.nodes.map(({ row, x, y }) => <button type="button" key={row.nodeId} aria-pressed={selectedNodeId === row.nodeId} style={{ "--citation-x": `${x}%`, "--citation-y": `${y}%` } as CSSProperties} onClick={() => onSelect(row.nodeId)} title={row.title}><strong>{row.title}</strong><span>{[row.authors, row.year].filter(Boolean).join(" · ") || row.kind}</span></button>)}
    </div>}
    {!loading && !error && rows.length > 1 && network.links.length === 0 && <p className="kg-citation-note" role="status">这些文献之间暂无已记录的直接引用关系。</p>}
  </section>
}
