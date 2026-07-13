import { useEffect, useRef } from "react"

declare global {
  interface Window {
    turnstile?: { render: (element: HTMLElement, options: { sitekey: string; callback: (token: string) => void; "expired-callback": () => void; "error-callback": () => void }) => string }
  }
}

export function TurnstileWidget({ siteKey, onToken }: { siteKey: string; onToken: (token: string) => void }) {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!siteKey || !host.current) return undefined
    let stopped = false
    let attempts = 0
    const render = () => {
      if (stopped || !host.current) return
      if (window.turnstile) {
        host.current.replaceChildren()
        window.turnstile.render(host.current, { sitekey: siteKey, callback: onToken, "expired-callback": () => onToken(""), "error-callback": () => onToken("") })
        return
      }
      if (attempts++ < 100) window.setTimeout(render, 100)
    }
    if (!document.querySelector('script[data-omnilit-turnstile="1"]')) {
      const script = document.createElement("script")
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
      script.async = true
      script.defer = true
      script.dataset.omnilitTurnstile = "1"
      document.head.appendChild(script)
    }
    render()
    return () => { stopped = true }
  }, [onToken, siteKey])
  if (!siteKey) return <p role="alert">当前部署未配置 Turnstile，开放注册不可用。</p>
  return <div ref={host} className="turnstile-widget" aria-label="人机验证" />
}
