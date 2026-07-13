import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type LibraryMutationRequest, type LibraryState, type ResearchWorkspace } from "@omnilit/shared-schema"
import { comparisonRecordTitle } from "./comparisonWorkspace"

interface CollectionsPageProps { client: ApiClient }

export function CollectionsPage({ client }: CollectionsPageProps) {
  const [state, setState] = useState<LibraryState>()
  const [workspace, setWorkspace] = useState<ResearchWorkspace>()
  const [status, setStatus] = useState("")
  const [newName, setNewName] = useState("")
  const [editingId, setEditingId] = useState("")
  const [editingName, setEditingName] = useState("")

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([client.getLibraryState(controller.signal), client.getResearchWorkspace(controller.signal)])
      .then(([nextState, nextWorkspace]) => { setState(nextState); setWorkspace(nextWorkspace) })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setStatus(reason instanceof Error ? reason.message : "集合加载失败") })
    return () => controller.abort()
  }, [client])

  async function mutate(action: LibraryMutationRequest["action"], values: Pick<LibraryMutationRequest, "collectionId" | "name"> = {}) {
    if (!state) return false
    setStatus("正在保存…")
    try {
      const result = await client.mutateLibraryState({ protocolVersion: PROTOCOL_VERSION, action, expectedRevision: state.revision, ...values })
      setState(result.state)
      if (action === "clear_compare") setWorkspace((current) => current ? { ...current, status: "empty", records: [] } : current)
      setStatus(result.changed ? "已保存" : "没有变化")
      return true
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "保存失败")
      void client.getLibraryState().then(setState).catch(() => undefined)
      return false
    }
  }

  return <section className="collections-page">
    <header className="page-header"><div><p className="eyebrow">Research Collections</p><h1>研究集合</h1></div><span>revision {state?.revision ?? "—"} · {state?.syncState ?? "local_only"}</span></header>
    <form className="collection-create collection-create-wide" onSubmit={(event) => { event.preventDefault(); const name = newName.trim(); if (name) void mutate("create_collection", { name }).then((saved) => { if (saved) setNewName("") }) }}><label>集合名称<input value={newName} maxLength={120} onChange={(event) => setNewName(event.target.value)} placeholder="例如：催化剂方法综述" /></label><button type="submit">新建集合</button></form>
    {!state ? <div className="state-panel" aria-busy="true"><h2>正在加载研究集合</h2><p>{status}</p></div> : <div className="collections-grid">
      <section className="info-card"><h2>集合</h2><ul className="collection-list">{state.collections.map((collection) => <li key={collection.id}><div><strong>{collection.name}</strong><span>{collection.recordCount} 篇 · {collection.builtIn ? "内置" : "自定义"}</span></div>{editingId === collection.id ? <form onSubmit={(event) => { event.preventDefault(); const name = editingName.trim(); if (name) void mutate("rename_collection", { collectionId: collection.id, name }).then((saved) => { if (saved) setEditingId("") }) }}><input aria-label={`重命名 ${collection.name}`} value={editingName} maxLength={120} onChange={(event) => setEditingName(event.target.value)} /><button type="submit">保存</button><button type="button" onClick={() => setEditingId("")}>取消</button></form> : <div className="collection-actions"><button type="button" onClick={() => { setEditingId(collection.id); setEditingName(collection.name) }}>重命名</button><button type="button" disabled={collection.builtIn} onClick={() => void mutate("delete_collection", { collectionId: collection.id })}>删除</button></div>}</li>)}</ul></section>
      <section className="info-card"><h2>比较工作区</h2><p>最多同时保留四篇文献，供后续多论文比较页面使用。</p><ol>{state.workspace.compareRecordIds.map((recordId) => <li key={recordId}>{comparisonRecordTitle(recordId, workspace)}</li>)}</ol>{state.workspace.compareRecordIds.length === 0 ? <p>尚未加入文献。</p> : <button type="button" onClick={() => void mutate("clear_compare")}>清空工作区</button>}</section>
    </div>}
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
