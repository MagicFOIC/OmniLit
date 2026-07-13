import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION } from "@omnilit/shared-schema"
import { writeCloudSession } from "./cloudSession"

interface InvitePageProps {
  client: ApiClient
}

export function InvitePage({ client }: InvitePageProps) {
  const { token = "" } = useParams()
  const navigate = useNavigate()
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [status, setStatus] = useState("")
  const [busy, setBusy] = useState(false)

  async function accept(): Promise<void> {
    setBusy(true)
    try {
      const session = await client.acceptTeamInvite({ protocolVersion: PROTOCOL_VERSION, token, displayName, password })
      writeCloudSession(session)
      navigate("/account", { replace: true })
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "邀请接受失败")
    } finally {
      setBusy(false)
    }
  }

  return <section><header className="page-header"><div><p className="eyebrow">Team invitation</p><h1>加入 OmniLit 研究团队</h1></div></header><form className="account-auth info-card" onSubmit={(event) => { event.preventDefault(); void accept() }}><label>显示名称<input required maxLength={120} autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label>设置密码<input type="password" required minLength={12} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><button type="submit" disabled={busy || token.length < 20}>接受邀请</button></form><p role="status">{status}</p></section>
}
