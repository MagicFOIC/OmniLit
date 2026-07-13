import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type CloudGraphList, type CloudGraphSyncResult } from "@omnilit/shared-schema"

interface CloudGraphPanelProps {
  cloudClient: ApiClient
  localClient: ApiClient
  localSourceAvailable: boolean
}

export function CloudGraphPanel({ cloudClient, localClient, localSourceAvailable }: CloudGraphPanelProps) {
  const [graphs, setGraphs] = useState<CloudGraphList>()
  const [recordId, setRecordId] = useState("paper-001")
  const [conflict, setConflict] = useState<CloudGraphSyncResult>()
  const [status, setStatus] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void cloudClient.listCloudGraphs(controller.signal).then(setGraphs).catch((error: unknown) => {
      if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "云图谱列表加载失败")
    })
    return () => controller.abort()
  }, [cloudClient])

  async function sync(baseRevision?: number): Promise<void> {
    if (!localSourceAvailable || !recordId.trim()) return
    setBusy(true)
    setStatus("")
    try {
      const graph = await localClient.getGraph(recordId.trim())
      const knownRevision = graphs?.graphs.find((item) => item.recordId === graph.recordId)?.cloudRevision ?? 0
      const result = await cloudClient.syncCloudGraph(graph.recordId, { protocolVersion: PROTOCOL_VERSION, deviceId: "desktop-web", baseCloudRevision: baseRevision ?? knownRevision, graph })
      if (result.status === "conflict") {
        setConflict(result)
        setStatus("云图谱已有新版本；未覆盖任何一方。")
      } else {
        setConflict(undefined)
        setGraphs((current) => ({ protocolVersion: PROTOCOL_VERSION, graphs: [{ recordId: result.recordId, cloudRevision: result.cloudRevision, updatedAt: result.syncedAt, nodeCount: result.serverGraph.nodes.length, edgeCount: result.serverGraph.edges.length }, ...(current?.graphs.filter((item) => item.recordId !== result.recordId) ?? [])] }))
        setStatus(`图谱已同步为云端版本 ${result.cloudRevision}。`)
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "云图谱同步失败")
    } finally {
      setBusy(false)
    }
  }

  return <section className="info-card cloud-graph-panel"><h2>云图谱与共享视图</h2><p>图谱快照在云端加密保存；共享视图沿用同一 graph ACL 和 GraphViewState 协议。</p>{localSourceAvailable ? <form className="cloud-graph-sync" onSubmit={(event) => { event.preventDefault(); void sync() }}><label>本地图谱 recordId<input required maxLength={256} value={recordId} onChange={(event) => setRecordId(event.target.value)} /></label><button type="submit" disabled={busy}>同步到云端</button></form> : <p>当前普通浏览器没有 Local Agent 图谱源；可读取已同步图谱，但不能把演示数据上传为真实研究数据。</p>}{conflict && <div className="conflict-panel" role="alert"><strong>图谱同步冲突 {conflict.conflictId}</strong><p>云端版本 {conflict.cloudRevision} 已保留。</p><button type="button" onClick={() => { setConflict(undefined); setStatus("已保留云端图谱，本地副本未修改。") }}>保留云端</button><button type="button" disabled={busy} onClick={() => void sync(conflict.cloudRevision)}>使用本地副本覆盖</button></div>}<h3>可访问的云图谱</h3>{!graphs && <p aria-live="polite">正在加载云图谱…</p>}{graphs?.graphs.length === 0 && <p>尚无可访问的云图谱。</p>}{graphs && graphs.graphs.length > 0 && <ul className="cloud-graph-list">{graphs.graphs.map((graph) => <li key={graph.recordId}><div><strong>{graph.recordId}</strong><span>v{graph.cloudRevision} · {graph.nodeCount} 节点 · {graph.edgeCount} 关系</span></div><Link to={`/graph?recordId=${encodeURIComponent(graph.recordId)}`}>打开图谱</Link></li>)}</ul>}<p className="mutation-status" role="status">{status}</p></section>
}
