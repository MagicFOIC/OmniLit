import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { HashRouter } from "react-router-dom"
import "@omnilit/design-tokens/theme.css"
import "@omnilit/knowledge-graph/styles.css"
import "./styles.css"
import { App } from "./App"
import { WebDiagnosticListeners } from "./WebDiagnosticListeners"
import { WebErrorBoundary } from "./WebErrorBoundary"

const root = document.getElementById("root")
if (!root) throw new Error("OmniLit Web root element is missing")

createRoot(root).render(
  <StrictMode>
    <WebErrorBoundary>
      <WebDiagnosticListeners />
      <HashRouter>
        <App />
      </HashRouter>
    </WebErrorBoundary>
  </StrictMode>
)
