import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type LibraryMutationRequest, type LibraryPage as LibraryPageData, type LibraryQuery, type LibraryRecordDetail, type LibraryState, type ResearchWorkspace } from "@omnilit/shared-schema"
import { comparisonRecordTitle } from "./comparisonWorkspace"

interface LibraryPageProps { client: ApiClient; cloudClient?: ApiClient }

export function LibraryPage({ client, cloudClient = client }: LibraryPageProps) {
  const [draftQuery, setDraftQuery] = useState("")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<NonNullable<LibraryQuery["sort"]>>("relevance_desc")
  const [pdfStatus, setPdfStatus] = useState("all")
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<LibraryPageData>()
  const [error, setError] = useState("")
  const [selectedId, setSelectedId] = useState("")
  const [detail, setDetail] = useState<LibraryRecordDetail>()
  const [libraryState, setLibraryState] = useState<LibraryState>()
  const [workspace, setWorkspace] = useState<ResearchWorkspace>()
  const [collectionId, setCollectionId] = useState("all")
  const [targetCollectionId, setTargetCollectionId] = useState("to_read")
  const [newCollectionName, setNewCollectionName] = useState("")
  const [mutationStatus, setMutationStatus] = useState("")
  const [privateTarget, setPrivateTarget] = useState(false)
  const [publicTarget, setPublicTarget] = useState(false)
  const [rightsStatement, setRightsStatement] = useState("")
  const libraryRevision = libraryState?.revision ?? 0

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([client.getLibraryState(controller.signal), client.getResearchWorkspace(controller.signal)]).then(([state, nextWorkspace]) => {
      setLibraryState(state)
      setWorkspace(nextWorkspace)
      setCollectionId((current) => current === "all" || state.collections.some((item) => item.id === current) ? current : "all")
      setTargetCollectionId((current) => state.collections.some((item) => item.id === current) ? current : state.collections[0]?.id ?? "")
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setMutationStatus(reason instanceof Error ? reason.message : "集合状态加载失败") })
    return () => controller.abort()
  }, [client])

  useEffect(() => {
    const controller = new AbortController()
    setError("")
    void client.queryLibrary({ protocolVersion: PROTOCOL_VERSION, query, sort, pdfStatus, collectionId, offset, limit: 100 }, controller.signal)
      .then((result) => {
        setPage(result)
        setSelectedId((current) => result.records.some((record) => record.recordId === current) ? current : result.records[0]?.recordId ?? "")
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "文献库加载失败") })
    return () => controller.abort()
  }, [client, collectionId, libraryRevision, offset, pdfStatus, query, sort])

  useEffect(() => {
    if (!selectedId) { setDetail(undefined); return undefined }
    const controller = new AbortController()
    setDetail(undefined)
    void client.getLibraryRecord(selectedId, controller.signal).then(setDetail).catch(() => undefined)
    return () => controller.abort()
  }, [client, selectedId])

  async function mutate(action: LibraryMutationRequest["action"], values: Pick<LibraryMutationRequest, "collectionId" | "name" | "recordId"> = {}) {
    if (!libraryState) return false
    setMutationStatus("正在保存…")
    try {
      const result = await client.mutateLibraryState({ protocolVersion: PROTOCOL_VERSION, action, expectedRevision: libraryState.revision, ...values })
      setLibraryState(result.state)
      void client.getResearchWorkspace().then(setWorkspace).catch(() => undefined)
      setMutationStatus(result.changed ? "已保存" : "没有变化")
      return true
    } catch (reason) {
      setMutationStatus(reason instanceof Error ? reason.message : "保存失败")
      void client.getLibraryState().then(setLibraryState).catch(() => undefined)
      return false
    }
  }

  async function applyCloudTargets(): Promise<void> {
    if (!detail) return
    if (!privateTarget && !publicTarget) { setMutationStatus("保持仅本地；未上传任何数据。"); return }
    setMutationStatus("正在处理云端目标…")
    try {
      if (privateTarget) {
        const existing = await cloudClient.pullWorkspaceChanges(0, 500)
        const current = [...existing.changes].reverse().find((change) => change.resourceType === "literature_record" && change.resourceId === detail.recordId)
        await cloudClient.pushWorkspaceChanges({ protocolVersion: PROTOCOL_VERSION, deviceId: "desktop-web", cursor: existing.cursor, changes: [{ resourceType: "literature_record", resourceId: detail.recordId, operation: "upsert", baseRevision: current?.revision ?? 0, clientMutationId: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-private`, payload: detail }] })
      }
      if (publicTarget) {
        if (rightsStatement.trim().length < 10) throw new Error("提交公共文献库前，请填写至少 10 个字符的权利声明。")
        const submission = await cloudClient.createPublicSubmission({ protocolVersion: PROTOCOL_VERSION, sourceResourceId: detail.recordId, record: detail, publicDisplayName: "OmniLit contributor", license: { code: "cc-by", url: "https://creativecommons.org/licenses/by/4.0/", rightsStatement: rightsStatement.trim() } })
        await cloudClient.submitPublicSubmission(submission.id)
      }
      setMutationStatus(privateTarget && publicTarget ? "已同步私有副本，并提交独立公共版本等待审核。" : privateTarget ? "已同步到我的私有 Workspace。" : "已提交独立公共版本等待审核；未创建私有云端副本。")
    } catch (reason) {
      setMutationStatus(reason instanceof Error ? reason.message : "云端操作失败")
    }
  }

  return <section className="library-page">
    <header className="page-header"><div><p className="eyebrow">Shared Library</p><h1>文献库</h1></div><span>{page?.total ?? 0} 篇 · revision {libraryState?.revision ?? "—"}</span></header>
    <form className="library-toolbar" onSubmit={(event) => { event.preventDefault(); setOffset(0); setQuery(draftQuery.trim()) }}>
      <label>检索<input value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="标题、作者、摘要、DOI…" /></label>
      <label>PDF<select value={pdfStatus} onChange={(event) => { setOffset(0); setPdfStatus(event.target.value) }}><option value="all">全部</option><option value="downloaded">已下载</option><option value="no_candidate">无候选</option><option value="failed">失败</option></select></label>
      <label>研究集合<select value={collectionId} onChange={(event) => { setOffset(0); setCollectionId(event.target.value) }}><option value="all">全部集合</option>{libraryState?.collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name} ({collection.recordCount})</option>)}</select></label>
      <label>排序<select value={sort} onChange={(event) => { setOffset(0); setSort(event.target.value as NonNullable<LibraryQuery["sort"]>) }}><option value="relevance_desc">相关性</option><option value="year_desc">年份（新到旧）</option><option value="year_asc">年份（旧到新）</option><option value="downloaded_first">已下载优先</option><option value="title_asc">标题</option></select></label>
      <button type="submit">搜索</button>
    </form>
    <section className="workspace-bar" aria-label="比较工作区"><strong>比较工作区 {libraryState?.workspace.compareRecordIds.length ?? 0}/4</strong><span>{libraryState?.workspace.compareRecordIds.map((recordId) => comparisonRecordTitle(recordId, workspace)).join(" · ") || "尚未加入文献"}</span><button type="button" disabled={!libraryState?.workspace.compareRecordIds.length} onClick={() => void mutate("clear_compare")}>清空</button></section>
    {error ? <div className="state-panel state-error"><h2>无法加载文献库</h2><p>{error}</p></div> : !page ? <div className="state-panel" aria-busy="true"><h2>正在加载文献库</h2></div> : page.status === "unavailable" ? <div className="state-panel"><h2>桌面缓存尚不可用</h2><p>{page.message}</p></div> : page.records.length === 0 ? <div className="state-panel"><h2>没有匹配的文献</h2><p>{page.message}</p></div> : <div className="library-layout">
      <div><ol className="library-results" aria-label="文献结果">{page.records.map((record) => <li key={record.recordId}><button type="button" className={selectedId === record.recordId ? "selected" : ""} onClick={() => setSelectedId(record.recordId)}><strong>{record.title}</strong><span>{record.authorsText || "未知作者"} · {record.year || "未知年份"}</span><span>{record.journalTitle || record.source} · {record.relevanceLabel}</span><small>{record.downloaded ? "已下载" : record.pdfStatus || "未下载"}{record.hasExtraction ? " · 已解析" : ""}</small></button></li>)}</ol><nav className="library-pagination" aria-label="文献结果分页"><button type="button" disabled={page.offset === 0} onClick={() => setOffset(Math.max(0, page.offset - 100))}>上一页</button><span>{page.offset + 1}–{page.nextOffset} / {page.total}</span><button type="button" disabled={!page.hasMore} onClick={() => setOffset(page.nextOffset)}>下一页</button></nav></div>
      <aside className="library-detail" aria-live="polite">{detail ? <><p className="eyebrow">文献详情</p><h2>{detail.title}</h2><p>{detail.authorsText}</p><fieldset><legend>集合与工作区</legend><select aria-label="目标研究集合" value={targetCollectionId} onChange={(event) => setTargetCollectionId(event.target.value)}>{libraryState?.collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select><button type="button" disabled={!targetCollectionId} onClick={() => void mutate("toggle_collection_record", { collectionId: targetCollectionId, recordId: detail.recordId })}>{(libraryState?.favorites[detail.recordId] ?? []).includes(targetCollectionId) ? "移出集合" : "加入集合"}</button><button type="button" onClick={() => void mutate("toggle_compare_record", { recordId: detail.recordId })}>{libraryState?.workspace.compareRecordIds.includes(detail.recordId) ? "移出比较" : "加入比较"}</button></fieldset><fieldset><legend>云端目标（相互独立）</legend><label className="control-row"><input type="checkbox" checked={privateTarget} onChange={(event) => setPrivateTarget(event.target.checked)} /><span>同步到我的私有 Workspace</span></label><label className="control-row"><input type="checkbox" checked={publicTarget} onChange={(event) => setPublicTarget(event.target.checked)} /><span>提交独立副本到公共文献库</span></label>{publicTarget && <label>CC BY 权利声明<textarea value={rightsStatement} onChange={(event) => setRightsStatement(event.target.value)} placeholder="说明开放许可来源及你拥有的再分发权…" /></label>}<p>公共副本经审核后发布，不会随私有副本自动修改或删除。本地路径、密钥和缓存不会上传。</p><button type="button" onClick={() => void applyCloudTargets()}>应用云端目标</button></fieldset><dl><dt>DOI</dt><dd>{detail.doi || "—"}</dd><dt>期刊</dt><dd>{detail.journalTitle || detail.source || "—"}</dd><dt>关键词</dt><dd>{detail.keywordsText || "—"}</dd></dl><h3>摘要</h3><p>{detail.abstract || detail.summaryText || "暂无摘要"}</p></> : <p>选择文献查看详情。</p>}<form className="collection-create" onSubmit={(event) => { event.preventDefault(); const name = newCollectionName.trim(); if (name) void mutate("create_collection", { name }).then((saved) => { if (saved) setNewCollectionName("") }) }}><label>新建研究集合<input value={newCollectionName} maxLength={120} onChange={(event) => setNewCollectionName(event.target.value)} /></label><button type="submit">创建</button></form><p className="mutation-status" role="status">{mutationStatus}</p></aside>
    </div>}
  </section>
}
