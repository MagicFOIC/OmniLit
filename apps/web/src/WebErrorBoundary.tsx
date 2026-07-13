import { Component, type ErrorInfo, type ReactNode } from "react"
import { recordWebDiagnostic } from "./diagnostics"

interface WebErrorBoundaryProps {
  children: ReactNode
}

interface WebErrorBoundaryState {
  failed: boolean
}

export class WebErrorBoundary extends Component<WebErrorBoundaryProps, WebErrorBoundaryState> {
  state: WebErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): WebErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch(error: Error, _info: ErrorInfo): void {
    recordWebDiagnostic("react", "render_error", error)
  }

  render(): ReactNode {
    if (this.state.failed) {
      return <main className="fatal-error" role="alert"><section className="state-panel state-error"><span className="state-icon" aria-hidden="true" /><h1>页面遇到错误</h1><p>已在当前标签页记录不含正文、路径或堆栈的诊断指纹。可以安全地重新加载页面。</p><button type="button" onClick={() => window.location.reload()}>重新加载</button></section></main>
    }
    return this.props.children
  }
}
