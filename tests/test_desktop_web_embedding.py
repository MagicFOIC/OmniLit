from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopWebEmbeddingContractTests(unittest.TestCase):
    def test_webengine_initializes_before_qapplication_and_bridge_is_registered(self) -> None:
        source = (ROOT / "omnilit_qt" / "app.py").read_text(encoding="utf-8")
        self.assertLess(source.index("initialize_qt_webengine()"), source.index("QApplication(sys.argv)"))
        self.assertIn('"desktopWebController": desktop_web', source)
        self.assertIn("desktop_web.refresh", source)

    def test_shared_web_graph_is_default_on_with_explicit_opt_out(self) -> None:
        source = (ROOT / "omnilit_qt" / "desktop_web_controller.py").read_text(encoding="utf-8")
        self.assertIn('{"0", "false", "no", "off"}', source)
        self.assertNotIn('not in {"1", "true", "yes", "on"}', source)

    def test_conda_source_runtime_configures_webengine_support_paths(self) -> None:
        source = (ROOT / "omnilit_qt_app.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.setdefault("QTWEBENGINEPROCESS_PATH"', source)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH"', source)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_LOCALES_PATH"', source)
        self.assertIn('qt_root / "QtWebEngineProcess.exe"', source)

    def test_token_is_injected_only_by_same_origin_request_interceptor(self) -> None:
        source = (ROOT / "omnilit_qt" / "desktop_web_controller.py").read_text(encoding="utf-8")
        self.assertIn("setHttpHeader(b\"Authorization\"", source)
        self.assertIn("target.host() == endpoint.host()", source)
        self.assertIn("target.port() == endpoint.port()", source)
        self.assertNotIn("access_token)", source[source.index("def graphUrl"):source.index("def isAllowedNavigation")])
        self.assertIn('startswith("/app/")', source)

    def test_webengine_canvas_is_lazy_inside_the_existing_qml_graph_page(self) -> None:
        library = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        page = (ROOT / "ui" / "qml" / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        hybrid = (ROOT / "ui" / "qml" / "HybridKnowledgeGraphView.qml").read_text(encoding="utf-8")
        embedded = (ROOT / "ui" / "qml" / "SharedKnowledgeGraphCanvasWebPage.qml").read_text(encoding="utf-8")
        self.assertIn("visible: root.graphOpen && !root.graphIsComparison", library)
        self.assertNotIn("SharedKnowledgeGraphWebPage.qml", library)
        self.assertIn("HybridKnowledgeGraphView", page)
        self.assertIn('source: active ? "SharedKnowledgeGraphCanvasWebPage.qml" : ""', hybrid)
        self.assertIn("clip: true", hybrid)
        self.assertIn("clip: true", embedded)
        self.assertIn("backgroundColor: theme.canvas", embedded)
        self.assertIn("KnowledgeGraphView", hybrid)
        self.assertIn("status === Loader.Error", hybrid)
        self.assertIn("WebEngineNavigationRequest.IgnoreRequest", embedded)
        self.assertIn("LoadFailedStatus", embedded)
        self.assertIn("onRenderProcessTerminated", embedded)
        self.assertIn('recordDiagnostic("webengine"', embedded)
        self.assertIn("canvas_render_process_terminated", embedded)
        self.assertIn('registerObject("knowledgeGraphController", knowledgeGraphController)', embedded)
        self.assertIn("root.channelReady = true", embedded)
        self.assertIn("onRecordIdChanged: loadCanvas()", embedded)

    def test_shared_business_pages_use_allowlisted_same_origin_routes(self) -> None:
        controller = (ROOT / "omnilit_qt" / "desktop_web_controller.py").read_text(encoding="utf-8")
        workspace = (ROOT / "ui" / "qml" / "Workspace.qml").read_text(encoding="utf-8")
        embedded = (ROOT / "ui" / "qml" / "SharedBusinessWebPage.qml").read_text(encoding="utf-8")
        self.assertIn("def routeUrl", controller)
        self.assertIn('"workspace", "statistics", "ai"', controller)
        self.assertIn('source: active ? "SharedBusinessWebPage.qml" : ""', workspace)
        self.assertIn('item.route = "workspace"', workspace)
        self.assertIn("desktopWebController.routeUrl(root.route)", embedded)
        self.assertIn("WebEngineNavigationRequest.IgnoreRequest", embedded)

    def test_release_builds_include_web_assets_and_qt_webengine(self) -> None:
        windows = (ROOT / "build_omnilit_exe.bat").read_text(encoding="utf-8")
        macos = (ROOT / "build_omnilit_macos.sh").read_text(encoding="utf-8")
        for source in (windows, macos):
            self.assertIn("web:build", source)
            self.assertIn("apps", source)
            self.assertIn("web", source)
            self.assertIn("dist", source)
            self.assertIn("PySide6.QtWebChannel", source)
            self.assertIn("PySide6.QtWebEngineCore", source)
            self.assertIn("PySide6.QtWebEngineQuick", source)

    def test_browser_csp_allows_only_loopback_local_agent_connections(self) -> None:
        source = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("connect-src 'self' ws:", source)
        for origin in ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"):
            self.assertIn(origin, source)
        self.assertIn("https://challenges.cloudflare.com", source)
        self.assertNotIn("connect-src *", source)


if __name__ == "__main__":
    unittest.main()
