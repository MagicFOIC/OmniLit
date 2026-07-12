from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class LiteratureLibraryQmlTests(unittest.TestCase):
    def test_all_dropdowns_use_the_shared_styled_component(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        styled = (qml_dir / "StyledComboBox.qml").read_text(encoding="utf-8")

        self.assertIn('name: "chevron-down"', styled)
        self.assertIn("control.popup.visible", styled)
        for path in qml_dir.glob("*.qml"):
            if path.name == "StyledComboBox.qml":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?<!Styled)ComboBox\s*\{", path.name)

    def test_global_form_controls_use_theme_components(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        theme = (qml_dir / "Theme.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property color textSecondary: preset.textSecondary", theme)
        self.assertIn("readonly property int controlHeight", theme)
        self.assertIn("readonly property int controlPadding", theme)
        for component in ("StyledTextField.qml", "StyledSwitch.qml", "StyledSlider.qml"):
            self.assertTrue((qml_dir / component).exists())

        specialized_text_fields = {"AppearancePreview.qml", "AuthTextField.qml", "DatePickerField.qml", "StyledTextField.qml"}
        for path in qml_dir.glob("*.qml"):
            text = path.read_text(encoding="utf-8")
            if path.name not in specialized_text_fields:
                self.assertNotRegex(text, r"(?<!Styled)(?<!Auth)TextField\s*\{", path.name)
            if path.name != "StyledSwitch.qml":
                self.assertNotRegex(text, r"(?<!Styled)Switch\s*\{", path.name)
            if path.name != "StyledSlider.qml":
                self.assertNotRegex(text, r"(?<!Styled)Slider\s*\{", path.name)

    def test_visible_scrollbars_use_expandable_shared_style(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        styled = (qml_dir / "StyledScrollBar.qml").read_text(encoding="utf-8")
        self.assertIn("control.hovered || control.pressed", styled)
        self.assertIn("expanded ? 14 : 8", styled)
        self.assertIn("Behavior on implicitWidth", styled)
        for path in qml_dir.glob("*.qml"):
            if path.name == "StyledScrollBar.qml":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("ScrollBar.vertical: ScrollBar", text, path.name)
            self.assertNotIn("ScrollBar.horizontal: ScrollBar", text, path.name)
            self.assertNotIn("ScrollBar.vertical.policy: ScrollBar.AsNeeded", text, path.name)

    def test_library_toolbar_allocates_space_by_priority(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        toolbar = qml[qml.index("id: libraryToolbarContent") : qml.index("visible: root.libraryFiltersOpen")]

        self.assertIn("RowLayout {", toolbar)
        self.assertIn("Layout.fillWidth: true", toolbar)
        self.assertIn("Layout.minimumWidth: 220", toolbar)
        self.assertIn("id: filterCountText", toolbar)
        self.assertNotIn("width: Math.min(360", toolbar)

    def test_library_page_uses_the_shared_page_transition(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("PageMotion { target: root }", qml)

    def test_qml_exposes_keyword_group_filter_and_new_metadata_fields(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("property var selectedKeywordGroups", qml)
        self.assertIn("literatureLibraryController.keywordGroupOptions", qml)
        self.assertIn("root.selectedKeywordGroups", qml)
        self.assertIn("root.sortValues", qml)
        self.assertIn("root.journalTypeValues", qml)
        self.assertIn("literatureLibraryController.setLibraryFilters", qml)
        self.assertIn("literatureLibraryController.favoriteProjects", qml)
        self.assertIn("literatureLibraryController.toggleFavorite", qml)
        self.assertIn("literatureLibraryController.toggleCompare", qml)
        self.assertIn("literatureLibraryController.compareRecords", qml)
        self.assertIn("modelData.journalTitle", qml)
        self.assertIn("modelData.journalTypeLabel", qml)
        self.assertIn("modelData.journalName", qml)
        self.assertIn("modelData.impactFactorText", qml)
        self.assertIn("root.selectedDetails.keywordsText", qml)
        self.assertIn("root.selectedDetails.contentSummary", qml)
        self.assertIn("literatureLibraryController.ensureLoaded()", qml)
        self.assertIn("onClicked: literatureLibraryController.refresh()", qml)
        self.assertIn("model: literatureLibraryController.visibleRecords", qml)
        self.assertIn("literatureLibraryController.loadMoreVisibleRecords()", qml)
        self.assertIn("literatureLibraryController.hasMoreVisibleRecords", qml)
        self.assertIn("literatureLibraryController.records", qml)
        self.assertIn("id: filterApplyTimer", qml)
        self.assertIn("onTriggered: root.applyFiltersNow()", qml)
        self.assertIn("function applyFiltersNow()", qml)
        self.assertIn("filterApplyTimer.restart()", qml)

    def test_library_toolbar_defaults_to_simple_controls_with_collapsed_filters(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("property bool libraryFiltersOpen: false", qml)
        self.assertIn("property bool libraryToolsOpen: false", qml)
        self.assertIn('text: root.libraryFiltersOpen ? "收起筛选" : "筛选"', qml)
        self.assertIn('text: literatureLibraryController.filteredCount + " / " + literatureLibraryController.totalCount', qml)
        self.assertIn('text: root.libraryToolsOpen ? "收起更多" : "更多"', qml)
        self.assertIn("visible: root.libraryFiltersOpen", qml)
        self.assertIn("visible: root.libraryToolsOpen", qml)
        self.assertIn("cleanupPopup.open()", qml)
        self.assertIn("literatureLibraryController.previewCleanup()", qml)
        self.assertIn('text: "批量工具"', qml)
        self.assertIn('text: "文献整理"', qml)
        self.assertIn('text: "分析工具"', qml)
        self.assertIn('text: "存储维护"', qml)
        self.assertIn("if (root.libraryToolsOpen)\n                                root.libraryFiltersOpen = false", qml)
        self.assertIn("if (root.libraryFiltersOpen)\n                                root.libraryToolsOpen = false", qml)
        self.assertIn('text: "筛选条件"', qml)
        self.assertIn('text: "相关性"', qml)
        self.assertIn('text: "PDF 状态"', qml)
        self.assertIn('text: "排序方式"', qml)
        self.assertIn('text: "期刊类型"', qml)
        self.assertIn('text: "收藏分类"', qml)
        self.assertIn('text: "关键词组"', qml)
        self.assertIn('text: "重置条件"', qml)
        self.assertIn("function activeFilterCount()", qml)
        self.assertIn("function resetAdvancedFilters()", qml)
        self.assertNotIn("id: libraryToolbarFlick", qml)
        self.assertNotIn("flickableDirection: Flickable.HorizontalFlick", qml)

    def test_qml_exposes_pdf_extraction_reader_entry(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        qml = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("解析阅读", qml)
        self.assertIn("LiteratureReaderPage", qml)
        self.assertIn("literatureLibraryController.hasExtraction", qml)
        self.assertIn('parsed ? "解析阅读 ✓" : "解析阅读"', qml)
        self.assertIn("success: parsed", qml)
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        self.assertIn("pdfExtractionController", reader)
        self.assertIn("pdfExtractionController.pages", reader)
        self.assertIn("property real zoom: 1.0", reader)
        self.assertIn("Timer {", reader)
        self.assertIn("id: openRecordTimer", reader)
        self.assertIn("function openRecordNow()", reader)
        self.assertIn("WheelHandler", reader)
        self.assertIn("acceptedModifiers: Qt.ControlModifier", reader)
        self.assertIn("property var elementExportPaths", reader)
        self.assertIn("elementExportPaths: root.elementExportPaths", reader)
        self.assertIn("function rememberElementExport(elementKey, path)", reader)
        self.assertIn("selectedElementId: pdfExtractionController.selectedElement", reader)
        self.assertIn("property string selectedEngine", reader)
        self.assertIn('property string selectedEngine: "fast"', reader)
        self.assertNotIn('{ engine: "auto"', reader)
        self.assertNotIn('{ engine: "hybrid"', reader)
        self.assertNotIn("自动解析（推荐）", reader)
        self.assertNotIn("混合解析", reader)
        self.assertIn("快速解析（PyMuPDF）", reader)
        self.assertIn("深度解析（MinerU）", reader)
        self.assertIn("高精度解析（PaddleOCR-VL）", reader)
        self.assertIn('pdfExtractionController.analyzeRecordWithEngine(root.recordId, root.pdfPath, "fast")', reader)
        self.assertIn("bbox.length >= 4", reader)

        panel = (qml_dir / "PdfExtractionPanel.qml").read_text(encoding="utf-8")
        self.assertIn("property var elementExportPaths", panel)
        self.assertIn("property var index", panel)
        self.assertIn("property string exportedPath", panel)
        self.assertIn("pdfExtractionController.openExportDirectory(root.exportedPath)", panel)
        self.assertIn("root.element.engine", panel)
        self.assertIn("root.element.confidence", panel)
        self.assertIn("root.element.needsReview", panel)
        self.assertIn("root.element.latex", panel)
        self.assertIn("root.element.markdown", panel)
        self.assertIn("root.index.engineErrors", panel)
        self.assertNotIn("pdfExtractionController.exportMarkdown", panel)
        self.assertNotIn("pdfExtractionController.exportRawOutputDirectory", panel)
        self.assertIn("pdfExtractionController.engineStatus", reader)
        self.assertNotIn("pdfExtractionController.bootstrapEngine", panel)
        self.assertIn("解析引擎状态", panel)
        self.assertIn("导出目录已在文件管理器中打开。", panel)
        self.assertNotIn("复制公式图片", panel)
        self.assertNotIn("导出公式图片", panel)
        self.assertNotIn("打开公式导出目录", panel)
        self.assertIn("wrapMode: Text.WrapAnywhere", panel)
        bookmark_bar = (qml_dir / "PdfElementBookmarkBar.qml").read_text(encoding="utf-8")
        self.assertIn("property string selectedElementId", bookmark_bar)
        self.assertIn("property string filterType", bookmark_bar)
        self.assertIn('model: ["全部", "公式数据", "图数据", "表格数据"]', bookmark_bar)
        self.assertIn("function filteredElements()", bookmark_bar)
        self.assertIn("function matchesFilter(element)", bookmark_bar)
        self.assertIn('String(kind || "") === "figure" || String(kind || "") === "chart"', bookmark_bar)
        self.assertIn("property bool selected", bookmark_bar)
        self.assertIn("theme.navSelected", bookmark_bar)
        self.assertIn("border.color: itemButton.selected ? theme.accent", bookmark_bar)
        self.assertTrue((qml_dir / "PdfElementBookmarkBar.qml").exists())
        self.assertTrue((qml_dir / "PdfElementOverlay.qml").exists())
        self.assertTrue((qml_dir / "PdfExtractionPanel.qml").exists())

    def test_library_card_keeps_metadata_and_actions_in_requested_order(self) -> None:
        qml = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        downloaded = qml.index('text: modelData.localPdfPath ? "已下载"')
        journal_type = qml.index('text: modelData.journalTypeLabel || "未识别"')
        favorite = qml.index('text: modelData.isFavorite ? "已收藏" : "收藏"')
        compare = qml.index('text: modelData.inCompare ? "移出对比" : "加入对比"')
        word_cloud = qml.index("onClicked: root.openWordCloud(index, modelData, false)")
        translation = qml.index("onClicked: root.openTranslationReader(index, modelData)")
        reader = qml.index('parsed ? "解析阅读 ✓" : "解析阅读"')
        graph = qml.index("onClicked: root.openKnowledgeGraph(index, modelData)")

        self.assertLess(downloaded, journal_type)
        self.assertLess(favorite, compare)
        self.assertLess(compare, word_cloud)
        self.assertLess(word_cloud, translation)
        self.assertLess(translation, reader)
        self.assertLess(reader, graph)
        self.assertIn("onClicked: literatureLibraryController.toggleCompare(modelData.recordId)", qml)
        self.assertNotIn("recordMoreMenu", qml)
        self.assertNotIn("modelData.keywordsText || modelData.contentSummary", qml)

    def test_library_exposes_selection_translation_reader_entry(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        library = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        reader = (qml_dir / "LiteratureTranslationReaderPage.qml").read_text(encoding="utf-8")
        overlay = (qml_dir / "PdfTextSelectionOverlay.qml").read_text(encoding="utf-8")

        self.assertIn("property bool translationReaderOpen: false", library)
        self.assertIn("property string translationReaderRecordId", library)
        self.assertIn("LiteratureTranslationReaderPage", library)
        self.assertIn("function openTranslationReader(index, record)", library)
        self.assertIn("function closeTranslationReader()", library)
        self.assertIn('text: "翻译"', library)
        self.assertNotIn('text: cached ? "翻译 ✓" : "翻译"', library)
        self.assertIn("visible: !root.readerOpen && !root.graphOpen && !root.wordCloudOpen && !root.translationReaderOpen", library)
        self.assertIn("root.selectRecord(index, record)", library)

        self.assertIn("pdfExtractionController.cachedRenderedPage", reader)
        self.assertIn("pdfExtractionController.renderPageAsync", reader)
        self.assertIn("onRecordIdChanged: root.handleTargetChanged()", reader)
        self.assertIn("onPdfPathChanged: root.handleTargetChanged()", reader)
        self.assertIn("pdfExtractionController.clearPdfSession()", reader)
        self.assertIn("pdfExtractionController.preparePdfSession(root.recordId, root.pdfPath)", reader)
        self.assertIn("pdfExtractionController.loadPdfPagesForTranslation", reader)
        self.assertNotIn("pdfExtractionController.loadIndexForPdfQuick", reader)
        self.assertIn("onPageRenderReady", reader)
        self.assertIn("sourceZoomKey === root.renderZoomKey", reader)
        self.assertIn("pdfExtractionController.requestTextWordsForPdfPage", reader)
        self.assertIn("onTextWordsReady", reader)
        self.assertNotIn("pageFrame.textItems = pdfExtractionController.textWordsForPdfPage", reader)
        self.assertIn("PdfTextSelectionOverlay", reader)
        self.assertIn("selectionTranslationController.translateSelection", reader)
        self.assertIn("selectionTranslationController.retranslateSelection", reader)
        self.assertIn("selectionTranslationController.copyText", reader)
        self.assertIn('pdfExtractionController.analyzeRecordWithEngine(root.recordId, root.pdfPath, "fast")', reader)
        self.assertIn("root.selectRecord(index, record, true)", library)
        self.assertIn("if (root.translationReaderOpen)", library)

        self.assertIn("signal textSelected(string text)", overlay)
        self.assertIn("preventStealing: true", overlay)
        self.assertIn("function selectionForDrag", overlay)
        self.assertIn("function itemForPoint", overlay)
        self.assertIn("property var anchorItem", overlay)
        self.assertIn("function selectionForRect", overlay)
        self.assertIn("function idsForItems", overlay)
        self.assertTrue((qml_dir / "LiteratureTranslationReaderPage.qml").exists())
        self.assertTrue((qml_dir / "PdfTextSelectionOverlay.qml").exists())

    def test_library_selection_uses_cached_thumbnail_before_lazy_generation(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        library = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("id: thumbnailGenerationTimer", library)
        self.assertIn("onTriggered: root.requestSelectedThumbnailGeneration()", library)
        self.assertIn("function requestSelectedThumbnailGeneration()", library)
        self.assertIn("literatureLibraryController.cachedThumbnailFor(recordId)", library)
        self.assertIn("thumbnailGenerationTimer.restart()", library)
        self.assertIn("thumbnailGenerationTimer.stop()", library)
        self.assertIn("PDF 首页预览将在空闲时生成", library)

    def test_reader_keeps_feedback_and_export_state_per_element(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        panel = (qml_dir / "PdfExtractionPanel.qml").read_text(encoding="utf-8")

        self.assertIn("property var elementFeedbackTexts", reader)
        self.assertIn("elementFeedbackTexts: root.elementFeedbackTexts", reader)
        self.assertIn("function rememberElementFeedback(elementKey, text)", reader)
        self.assertIn("onElementFeedbackChanged: function(elementKey, text)", reader)
        self.assertIn("root.elementFeedbackTexts = ({})", reader)

        self.assertIn("property var elementFeedbackTexts", panel)
        self.assertIn("property string currentFeedbackText", panel)
        self.assertIn("function displayStatusText()", panel)
        self.assertIn("if (root.element && root.element.id)", panel)
        self.assertIn("function setCurrentFeedback(text)", panel)
        self.assertIn("root.elementFeedbackChanged(key, value)", panel)
        self.assertNotIn("text: root.feedbackText || root.statusText", panel)

    def test_qml_exposes_per_paper_knowledge_graph(self) -> None:
        qml_dir = ROOT / "ui" / "qml"
        library = (qml_dir / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")
        graph = (qml_dir / "KnowledgeGraphPage.qml").read_text(encoding="utf-8")
        reader = (qml_dir / "LiteratureReaderPage.qml").read_text(encoding="utf-8")

        self.assertIn('generated ? "知识图谱 ✓" : "知识图谱"', library)
        self.assertIn("KnowledgeGraphPage", library)
        self.assertIn("knowledgeGraphController.generateGraph", library)
        self.assertIn("function openComparisonKnowledgeGraph()", library)
        self.assertIn("knowledgeGraphController.generateComparisonGraph(records)", library)
        self.assertIn("onClicked: root.openComparisonKnowledgeGraph()", library)
        self.assertIn("property bool graphReturnToCompare", library)
        self.assertIn("property bool graphIsComparison", library)
        self.assertIn("knowledgeGraphController.regenerateComparisonGraph", graph)
        for component in ("KnowledgeGraphView.qml", "KnowledgeGraphPanel.qml", "GraphNodeCard.qml", "GraphFilterBar.qml"):
            self.assertTrue((qml_dir / component).is_file(), component)
        for component in ("LiteratureCompareGraphPage.qml", "ComparisonEvidencePanel.qml", "ComparisonMatrix.qml"):
            self.assertTrue((qml_dir / component).is_file(), component)
        self.assertIn("LiteratureCompareGraphPage", library)
        self.assertIn("knowledgeGraphController.generateGraphs", library)
        self.assertIn("knowledgeGraphController.focusEvidence", graph)
        self.assertIn("knowledgeGraphController.setFilterMode", graph)
        self.assertIn("knowledgeGraphController.hasGraph", library)
        self.assertIn("wordCloudController.hasCloud", library)
        self.assertIn("knowledgeGraphController.search", graph)
        self.assertIn("KnowledgeGraphView", graph)
        self.assertIn("knowledgeGraphController.regenerateGraph", graph)
        self.assertIn("knowledgeGraphController.exportGraphMarkdown", graph)
        self.assertIn("signal knowledgeGraphRequested", reader)
        self.assertIn("signal wordCloudRequested", reader)
        self.assertIn("wordCloudController.generateForRecord", library)
        self.assertIn("wordCloudController.generateForRecords", library)
        for component in ("WordCloudPage.qml", "WordCloudView.qml"):
            self.assertTrue((qml_dir / component).is_file(), component)

    def test_reader_pdf_zoom_uses_effective_zoom_and_mouse_anchor(self) -> None:
        reader = (ROOT / "ui" / "qml" / "LiteratureReaderPage.qml").read_text(encoding="utf-8")
        library = (ROOT / "ui" / "qml" / "LiteratureLibraryPage.qml").read_text(encoding="utf-8")

        self.assertIn("width: root.pageWidth(index) * root.effectiveZoom", reader)
        self.assertIn("height: root.pageHeight(index) * root.effectiveZoom", reader)
        self.assertIn("pdfExtractionController.renderPage(root.recordId, index, root.effectiveZoom)", reader)
        self.assertIn("root.adjustZoomAt(event.angleDelta.y > 0 ? 0.10 : -0.10, point.x, point.y)", reader)
        self.assertIn("function adjustZoomAt(delta, viewportX, viewportY)", reader)
        self.assertIn("pageFlick.contentX = root.clampContentX(targetX)", reader)
        self.assertIn("pageFlick.contentY = root.clampContentY(targetY)", reader)
        self.assertIn("function focusEvidence(page, bbox, elementId)", reader)
        self.assertIn("function applyPendingEvidenceFocus()", reader)
        self.assertIn("evidenceFocusTimer.restart()", reader)
        self.assertIn("readerPage.focusEvidence(page, bbox || [], elementId)", library)
        self.assertIn("function clampContentX(value)", reader)
        self.assertIn("function clampContentY(value)", reader)


if __name__ == "__main__":
    unittest.main()
