import { useEffect } from "react"
import { recordWebDiagnostic } from "./diagnostics"

export function WebDiagnosticListeners() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => recordWebDiagnostic("window", "uncaught_error", event.error)
    const onRejection = (event: PromiseRejectionEvent) => recordWebDiagnostic("promise", "unhandled_rejection", event.reason)
    window.addEventListener("error", onError)
    window.addEventListener("unhandledrejection", onRejection)
    return () => {
      window.removeEventListener("error", onError)
      window.removeEventListener("unhandledrejection", onRejection)
    }
  }, [])
  return null
}
