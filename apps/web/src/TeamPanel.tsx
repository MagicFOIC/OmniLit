import { useEffect, useState } from "react"
import type { ApiClient } from "@omnilit/api-client"
import { PROTOCOL_VERSION, type ResourcePermissionList, type TeamInvite, type TeamMemberList, type UserAccount } from "@omnilit/shared-schema"

interface TeamPanelProps {
  client: ApiClient
  account: UserAccount
}

export function TeamPanel({ client, account }: TeamPanelProps) {
  const [team, setTeam] = useState<TeamMemberList>()
  const [permissions, setPermissions] = useState<ResourcePermissionList>()
  const [resourceType, setResourceType] = useState<"library_state" | "graph">("library_state")
  const [resourceId, setResourceId] = useState("current")
  const [resourceDraft, setResourceDraft] = useState("current")
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member")
  const [invite, setInvite] = useState<TeamInvite>()
  const [pendingRemoval, setPendingRemoval] = useState("")
  const [status, setStatus] = useState("")
  const [busy, setBusy] = useState(false)
  const role = account.roles[0] ?? "member"
  const canAdminister = role === "owner" || role === "admin"
  const isOwner = role === "owner"

  useEffect(() => {
    const controller = new AbortController()
    void client.listTeamMembers(controller.signal).then(setTeam).catch((error: unknown) => {
      if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "团队加载失败")
    })
    if (isOwner) void client.listResourcePermissions(resourceType, resourceId, controller.signal).then(setPermissions).catch((error: unknown) => {
      if (!controller.signal.aborted) setStatus(error instanceof Error ? error.message : "权限加载失败")
    })
    return () => controller.abort()
  }, [client, isOwner, resourceId, resourceType])

  async function createInvite(): Promise<void> {
    setBusy(true)
    try {
      const created = await client.createTeamInvite({ protocolVersion: PROTOCOL_VERSION, email: inviteEmail, role: inviteRole, expiresInHours: 72 })
      setInvite(created)
      setInviteEmail("")
      setStatus("邀请已创建；地址只显示一次，72 小时后失效。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "邀请创建失败")
    } finally {
      setBusy(false)
    }
  }

  async function updateRole(memberId: string, nextRole: "admin" | "member"): Promise<void> {
    setBusy(true)
    try {
      setTeam(await client.updateTeamMemberRole(memberId, nextRole))
      setStatus("成员角色已更新。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "角色更新失败")
    } finally {
      setBusy(false)
    }
  }

  async function updatePermission(memberId: string, permission: "none" | "viewer" | "editor"): Promise<void> {
    setBusy(true)
    try {
      setPermissions(await client.setResourcePermission({ protocolVersion: PROTOCOL_VERSION, resourceType, resourceId, principalType: "user", principalId: memberId, permission }))
      setStatus(`${resourceType === "graph" ? "云图谱" : "文献库"}权限已更新。`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "权限更新失败")
    } finally {
      setBusy(false)
    }
  }

  async function removeMember(memberId: string): Promise<void> {
    setBusy(true)
    try {
      await client.removeTeamMember(memberId)
      setTeam((current) => current ? { ...current, members: current.members.filter((member) => member.id !== memberId) } : current)
      setPermissions((current) => current ? { ...current, permissions: current.permissions.filter((permission) => permission.principalId !== memberId) } : current)
      setPendingRemoval("")
      setStatus("成员、会话和资源授权已移除。")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "成员移除失败")
    } finally {
      setBusy(false)
    }
  }

  const memberPermission = new Map(permissions?.permissions.filter((item) => item.principalType === "user").map((item) => [item.principalId, item.permission]) ?? [])
  return (
    <section className="info-card team-panel">
      <h2>团队与文献库权限</h2>
      <p>{account.dataControls.allowTeamAccess ? "团队访问总开关已启用；成员仍需资源 ACL。" : "团队访问总开关关闭；即使存在 ACL，成员也无法读取研究数据。"}</p>
      {canAdminister && <form className="team-invite" onSubmit={(event) => { event.preventDefault(); void createInvite() }}><label>邀请邮箱<input type="email" required value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} /></label><label>角色<select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "admin" | "member")}><option value="member">成员</option>{isOwner && <option value="admin">管理员</option>}</select></label><button type="submit" disabled={busy}>创建邀请</button></form>}
      {invite && <label className="invite-result">一次性邀请地址<input readOnly value={invite.url} /></label>}
      {isOwner && <form className="acl-resource" onSubmit={(event) => { event.preventDefault(); const value = resourceDraft.trim(); if (value) setResourceId(value) }}><label>授权资源<select value={resourceType} onChange={(event) => { const next = event.target.value as "library_state" | "graph"; setResourceType(next); setResourceDraft(next === "library_state" ? "current" : "paper-001") }}><option value="library_state">云端文献库</option><option value="graph">云图谱</option></select></label><label>资源 ID<input required maxLength={256} disabled={resourceType === "library_state"} value={resourceDraft} onChange={(event) => setResourceDraft(event.target.value)} /></label><button type="submit" disabled={busy}>加载 ACL</button><span>当前：{resourceType}/{resourceId}</span></form>}
      {!team && <p aria-live="polite">正在加载团队成员…</p>}
      {team && <ul className="team-list">{team.members.map((member) => { const canRemove = isOwner ? member.role !== "owner" : role === "admin" && member.role === "member"; return <li key={member.id}><div><strong>{member.displayName}</strong><span>{member.email}</span></div><span>{member.role}</span>{isOwner && member.role !== "owner" && <><label>角色<select aria-label={`${member.displayName} 的角色`} value={member.role} disabled={busy} onChange={(event) => void updateRole(member.id, event.target.value as "admin" | "member")}><option value="member">成员</option><option value="admin">管理员</option></select></label><label>当前资源<select aria-label={`${member.displayName} 的当前资源权限`} value={memberPermission.get(member.id) ?? "none"} disabled={busy} onChange={(event) => void updatePermission(member.id, event.target.value as "none" | "viewer" | "editor")}><option value="none">无权限</option><option value="viewer">只读</option><option value="editor">编辑</option></select></label></>}{canRemove && (pendingRemoval === member.id ? <span className="remove-confirm"><button type="button" disabled={busy} onClick={() => void removeMember(member.id)}>确认移除</button><button type="button" onClick={() => setPendingRemoval("")}>取消</button></span> : <button type="button" onClick={() => setPendingRemoval(member.id)}>移除</button>)}</li> })}</ul>}
      <p className="mutation-status" role="status">{status}</p>
    </section>
  )
}
