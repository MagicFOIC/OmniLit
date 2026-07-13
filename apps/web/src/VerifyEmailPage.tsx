import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import type { ApiClient } from "@omnilit/api-client"

export function VerifyEmailPage({ client }: { client: ApiClient }) {
  const { token = "" } = useParams()
  const [status, setStatus] = useState("正在验证邮箱…")
  useEffect(() => {
    const controller = new AbortController()
    void client.verifyEmail(token, controller.signal).then(() => setStatus("邮箱验证成功。现在可以登录 OmniLit。"), (error: unknown) => setStatus(error instanceof Error ? error.message : "邮箱验证失败"))
    return () => controller.abort()
  }, [client, token])
  return <section className="state-panel"><h1>账户邮箱验证</h1><p role="status">{status}</p></section>
}
