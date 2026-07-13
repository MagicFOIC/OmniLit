import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type PublicLibraryPage as PublicLibraryPageData, type PublicSubmission } from "@omnilit/shared-schema"

interface PublicLibraryPageProps { client: ApiClient }

export function PublicLibraryPage({ client }: PublicLibraryPageProps) {
  const [draft, setDraft] = useState("")
  const [query, setQuery] = useState("")
  const [page, setPage] = useState<PublicLibraryPageData>()
  const [submissions, setSubmissions] = useState<PublicSubmission[]>([])
  const [status, setStatus] = useState("")

  useEffect(() => {
    const controller = new AbortController()
    void client.queryPublicLibrary({ protocolVersion: PROTOCOL_VERSION, searchText: query, offset: 0, limit: 100 }, controller.signal)
      .then(setPage)
      .catch((error: unknown) => { if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "公共文献库加载失败") })
    void client.listPublicSubmissions(controller.signal).then((result) => setSubmissions(result.submissions)).catch(() => undefined)
    return () => controller.abort()
  }, [client, query])

  return <section className="public-library-page">
    <header className="page-header"><div><p className="eyebrow">Public Workspace</p><h1>公共文献库</h1><p>公共版本是经过许可审核的独立副本，不会随私有 Workspace 自动修改或删除。</p></div><span>{page?.total ?? 0} 篇已公开</span></header>
    <form className="library-toolbar" onSubmit={(event) => { event.preventDefault(); setQuery(draft.trim()) }}><label>检索公共元数据<input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="标题、作者、DOI…" /></label><button type="submit">搜索</button></form>
    <div className="account-grid">
      <section className="info-card"><h2>已审核文献</h2>{page?.records.length ? <ol className="library-results">{page.records.map((item) => <li key={item.id}><article><strong>{String(item.record.title ?? "未命名文献")}</strong><p>{String(item.record.authorsText ?? "未知作者")}</p><small>{item.license.code} · {item.contributorName} · v{item.version}</small></article></li>)}</ol> : <p>暂无匹配的公共文献。</p>}</section>
      <section className="info-card"><h2>我的投稿</h2>{submissions.length ? <ul>{submissions.map((submission) => <li key={submission.id}><strong>{String(submission.record.title ?? submission.sourceResourceId)}</strong><span className="status-pill">{submission.status}</span>{submission.reviewNote && <p>{submission.reviewNote}</p>}</li>)}</ul> : <p>尚未提交公共版本。请在文献详情中选择“提交公共文献库”。</p>}</section>
    </div>
    <p className="mutation-status" role="status">{status}</p>
  </section>
}
