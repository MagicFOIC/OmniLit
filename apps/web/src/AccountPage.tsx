import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { ApiClientError } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type AuthSession, type LibrarySyncResult, type ShareLink, type UserAccount, type WorkspaceSummary, type WorkspaceSyncPreferences, type WorkspaceSyncStatus } from "@omnilit/shared-schema"
import { clearCloudSession, readCloudSession, updateCloudSessionUser, writeCloudSession } from "./cloudSession"
import { TeamPanel } from "./TeamPanel"
import { CloudGraphPanel } from "./CloudGraphPanel"
import { CloudTaskPanel } from "./CloudTaskPanel"
import { TurnstileWidget } from "./TurnstileWidget"

interface AccountPageProps {
  cloudClient: ApiClient
  localClient: ApiClient
  cloudConfigured: boolean
  localGraphSourceAvailable: boolean
}

const DATA_CONTROL_LABELS = {
  uploadLocalPdfs: "上传本地 PDF",
  syncAnnotations: "同步批注",
  syncFullText: "同步全文",
  useCloudAi: "使用云端 AI",
  retainCloudTaskData: "保留云端任务数据",
  allowTeamAccess: "允许团队访问",
  allowShareLinks: "允许分享链接",
  shareDiagnostics: "共享匿名崩溃诊断"
} as const
type DataControlKey = keyof typeof DATA_CONTROL_LABELS

export function AccountPage({ cloudClient, localClient, cloudConfigured, localGraphSourceAvailable }: AccountPageProps) {
  const [session, setSession] = useState<AuthSession | undefined>(() => readCloudSession())
  const [account, setAccount] = useState<UserAccount | undefined>(session?.user)
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [tenantName, setTenantName] = useState("")
  const [cloudRevision, setCloudRevision] = useState(0)
  const [conflict, setConflict] = useState<LibrarySyncResult | undefined>()
  const [share, setShare] = useState<ShareLink | undefined>()
  const [auditCount, setAuditCount] = useState(0)
  const [confirmation, setConfirmation] = useState("")
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState("")
  const [workspace, setWorkspace] = useState<WorkspaceSummary>()
  const [syncPreferences, setSyncPreferences] = useState<WorkspaceSyncPreferences>()
  const [syncStatus, setSyncStatus] = useState<WorkspaceSyncStatus>()
  const [turnstileToken, setTurnstileToken] = useState("")

  useEffect(() => {
    if (!session) return undefined
    const controller = new AbortController()
    const requests: Array<Promise<unknown>> = [
      cloudClient.getAccount(controller.signal).then((updated) => { setAccount(updated); updateCloudSessionUser(updated) }),
      cloudClient.getCloudLibrary(controller.signal).then((result) => setCloudRevision(result.cloudRevision))
      , cloudClient.getWorkspaceSummary(controller.signal).then(setWorkspace)
      , cloudClient.getWorkspaceSyncPreferences(controller.signal).then(setSyncPreferences)
      , cloudClient.getWorkspaceSyncStatus(controller.signal).then(setSyncStatus)
    ]
    if (session.user.roles.some((role) => role === "owner" || role === "admin")) requests.push(cloudClient.getAuditEvents(controller.signal).then((page) => setAuditCount(page.events.length)))
    void Promise.allSettled(requests).then((results) => {
      const accountResult = results[0]
      if (!controller.signal.aborted && accountResult?.status === "rejected" && accountResult.reason instanceof ApiClientError && accountResult.reason.payload.code === "unauthorized") {
        clearCloudSession()
        setSession(undefined)
        setAccount(undefined)
      }
    })
    return () => controller.abort()
  }, [cloudClient, session])

  async function authenticate(): Promise<void> {
    setBusy(true)
    setStatus("")
    try {
      const next = mode === "login"
        ? await cloudClient.login({ email, password })
        : await cloudClient.registerAccount({ email, password, displayName, tenantName, turnstileToken })
      if (typeof next.accessToken !== "string") {
        setMode("login")
        setPassword("")
        setTurnstileToken("")
        setStatus(`验证邮件已发送到 ${next.email}；验证后即可登录。`)
        return
      }
      const authenticated = next as AuthSession
      writeCloudSession(authenticated)
      setSession(authenticated)
      setAccount(authenticated.user)
      setPassword("")
      setStatus("账户会话已建立。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "认证失败")
    } finally {
      setBusy(false)
    }
  }

  async function updateControl(name: DataControlKey, checked: boolean): Promise<void> {
    if (!account) return
    setBusy(true)
    try {
      const updated = await cloudClient.updateCloudDataControls({ ...account.dataControls, [name]: checked })
      setAccount(updated)
      updateCloudSessionUser(updated)
      setStatus("云端研究数据控制已更新。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "数据控制更新失败")
    } finally {
      setBusy(false)
    }
  }

  async function syncLibrary(baseRevision = cloudRevision): Promise<void> {
    setBusy(true)
    setStatus("")
    try {
      const localState = await localClient.getLibraryState()
      const result = await cloudClient.syncLibrary({ protocolVersion: PROTOCOL_VERSION, deviceId: "web", baseCloudRevision: baseRevision, state: localState })
      setCloudRevision(result.cloudRevision)
      if (result.status === "conflict") {
        setConflict(result)
        setStatus("发现云端新版本。请选择保留云端，或明确使用当前本地副本覆盖。")
      } else {
        setConflict(undefined)
        setStatus(`同步完成，云端版本 ${result.cloudRevision}。`)
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "同步失败")
    } finally {
      setBusy(false)
    }
  }

  async function updateWorkspaceSync(enabled: boolean): Promise<void> {
    const categories = syncPreferences?.categories ?? { literature: true, collections: true, graphs: true, views: true, settings: true, annotations: false, pdfs: false, fullText: false, extractions: false }
    setBusy(true)
    try {
      const updated = await cloudClient.updateWorkspaceSyncPreferences({ protocolVersion: PROTOCOL_VERSION, enabled, categories, updatedAt: syncPreferences?.updatedAt ?? "" })
      setSyncPreferences(updated)
      setSyncStatus(await cloudClient.getWorkspaceSyncStatus())
      setStatus(enabled ? "已明确开启个人 Workspace 增量同步；PDF、全文和批注仍保持关闭。" : "已停止个人 Workspace 同步；本地和云端副本均未删除。")
    } catch (error) { setStatus(error instanceof Error ? error.message : "同步设置更新失败") }
    finally { setBusy(false) }
  }

  async function createShare(): Promise<void> {
    setBusy(true)
    try {
      const created = await cloudClient.createShare({ protocolVersion: PROTOCOL_VERSION, resourceType: "library_state", resourceId: "current", permission: "viewer" })
      setShare(created)
      setStatus("只读分享链接已创建；链接只显示一次。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "分享创建失败")
    } finally {
      setBusy(false)
    }
  }

  async function revokeShare(): Promise<void> {
    if (!share) return
    setBusy(true)
    try {
      await cloudClient.revokeShare(share.id)
      setShare(undefined)
      setStatus("分享链接已撤销。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "撤销失败")
    } finally {
      setBusy(false)
    }
  }

  async function exportData(): Promise<void> {
    setBusy(true)
    try {
      const data = await cloudClient.exportAccount()
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }))
      const link = document.createElement("a")
      link.href = url
      link.download = "omnilit-account-export.json"
      link.click()
      URL.revokeObjectURL(url)
      setStatus("账户数据导出已生成。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "导出失败")
    } finally {
      setBusy(false)
    }
  }

  async function deleteAccount(): Promise<void> {
    if (!account || confirmation !== account.email) return
    setBusy(true)
    try {
      await cloudClient.deleteAccount(confirmation)
      clearCloudSession()
      setSession(undefined)
      setAccount(undefined)
      setConfirmation("")
      setStatus("账户及其租户数据已删除。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "账户删除失败")
    } finally {
      setBusy(false)
    }
  }

  if (!session || !account) return (
    <section className="account-page">
      <header className="page-header"><div><p className="eyebrow">Cloud API</p><h1>{mode === "login" ? "登录 OmniLit" : "创建研究账户"}</h1></div><span className="status-pill">{cloudConfigured ? "Cloud API" : "本地演示服务"}</span></header>
      <form className="account-auth info-card" onSubmit={(event) => { event.preventDefault(); void authenticate() }}>
        <label>邮箱<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>密码<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {mode === "register" && <><label>显示名称<input autoComplete="name" required maxLength={120} value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label>研究团队<input required maxLength={120} value={tenantName} onChange={(event) => setTenantName(event.target.value)} /></label><TurnstileWidget siteKey={import.meta.env.VITE_TURNSTILE_SITE_KEY ?? ""} onToken={setTurnstileToken} /></>}
        <div className="account-actions"><button type="submit" disabled={busy}>{mode === "login" ? "登录" : "创建账户"}</button><button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>{mode === "login" ? "创建账户" : "返回登录"}</button></div>
      </form>
      <p role="status">{status}</p>
    </section>
  )

  const controls = account.dataControls
  const isOwner = account.roles.includes("owner")
  return (
    <section className="account-page">
      <header className="page-header"><div><p className="eyebrow">{account.tenantId}</p><h1>{account.displayName}</h1><p>{account.email} · {account.roles.join(", ")}</p></div><button type="button" onClick={() => { clearCloudSession(); setSession(undefined); setAccount(undefined) }}>退出登录</button></header>
      <div className="account-grid">
        <section className="info-card"><h2>研究数据控制</h2><p>所有上传、AI、团队与分享能力默认关闭，并由你逐项启用。</p>{Object.entries(DATA_CONTROL_LABELS).map(([name, label]) => { const key = name as DataControlKey; return <label className="control-row" key={key}><input type="checkbox" checked={controls[key]} disabled={busy} onChange={(event) => void updateControl(key, event.target.checked)} /><span>{label}</span></label> })}</section>
        <section className="info-card"><h2>个人 Workspace 同步</h2><p>{workspace?.name ?? "个人 Workspace"} · {workspace ? `${(workspace.quotaBytes / 1024 ** 3).toFixed(1)} GB 配额` : "正在读取配额"}</p><p>同步默认关闭，登录不会上传研究数据。当前 cursor：{syncStatus?.cursor ?? 0}，资源：{syncStatus?.resourceCount ?? 0}。</p><label className="control-row"><input type="checkbox" checked={syncPreferences?.enabled ?? false} disabled={busy} onChange={(event) => void updateWorkspaceSync(event.target.checked)} /><span>明确开启结构化数据增量双向同步</span></label><p>PDF、全文、提取结果和批注需要在研究数据控制中另外授权。</p><h3>旧版集合快照</h3><p>当前云端版本：{cloudRevision}。此兼容入口仅发送集合、收藏和比较工作区状态。</p><button type="button" disabled={busy} onClick={() => void syncLibrary()}>同步当前本地状态</button>{conflict && <div className="conflict-panel" role="alert"><strong>同步冲突 {conflict.conflictId}</strong><p>云端版本 {conflict.cloudRevision} 已保留，未发生静默覆盖。</p><button type="button" onClick={() => { setConflict(undefined); setStatus("已保留云端版本，本地状态未修改。") }}>保留云端</button><button type="button" onClick={() => void syncLibrary(conflict.cloudRevision)}>使用本地副本覆盖</button></div>}</section>
        <section className="info-card"><h2>分享与审计</h2><p>当前会话可见审计事件：{auditCount}</p><button type="button" disabled={busy || !controls.allowShareLinks || cloudRevision === 0} onClick={() => void createShare()}>创建只读分享链接</button>{share && <div className="share-result"><label>一次性分享地址<input readOnly value={share.url} /></label><button type="button" onClick={() => void revokeShare()}>撤销链接</button></div>}</section>
        {isOwner && <section className="info-card danger-zone"><h2>导出与删除</h2><button type="button" disabled={busy} onClick={() => void exportData()}>导出账户数据</button><label>输入账户邮箱确认删除<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label><button type="button" disabled={busy || confirmation !== account.email} onClick={() => void deleteAccount()}>永久删除账户</button></section>}
        <TeamPanel client={cloudClient} account={account} />
        <CloudGraphPanel cloudClient={cloudClient} localClient={localClient} localSourceAvailable={localGraphSourceAvailable || !cloudConfigured} />
        <CloudTaskPanel client={cloudClient} account={account} />
      </div>
      <p className="mutation-status" role="status">{status}</p>
    </section>
  )
}
