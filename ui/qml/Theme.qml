import QtQuick

QtObject {
    property bool dynamic: true
    readonly property bool preferencesAvailable: typeof preferencesController !== "undefined"
    readonly property string presetName: dynamic && preferencesAvailable ? preferencesController.effectiveThemePreset : "scholar_light"
    readonly property var preset: presetTokens(presetName)
    readonly property bool dark: preset.mode === "dark"
    readonly property bool highContrast: dynamic && preferencesAvailable && preferencesController.highContrast
    readonly property bool reduceMotion: dynamic && preferencesAvailable && preferencesController.reduceMotion
    readonly property real densityScale: dynamic && preferencesAvailable ? preferencesController.densityScale : 1.0
    readonly property int baseFontSize: dynamic && preferencesAvailable ? preferencesController.fontSizeBase : 14
    readonly property int radiusBase: dynamic && preferencesAvailable ? preferencesController.radiusBase : 10
    readonly property int radiusSmall: Math.max(2, radiusBase - 4)
    readonly property int radiusMedium: radiusBase
    readonly property int radiusLarge: radiusBase + 6
    readonly property real translationLineHeight: dynamic && preferencesAvailable ? preferencesController.translationLineHeightValue : 1.55
    readonly property color pdfBackground: dynamic && preferencesAvailable ? preferencesController.pdfBackgroundColor : "#faf6ed"

    readonly property color canvas: preset.canvas
    readonly property color canvasTop: preset.canvasTop
    readonly property color canvasBottom: preset.canvasBottom
    readonly property color surface: preset.surface
    readonly property color surfaceSoft: preset.surfaceSoft
    readonly property color border: highContrast ? preset.borderStrong : preset.border
    readonly property color borderStrong: highContrast ? preset.textMuted : preset.borderStrong
    readonly property color text: preset.text
    readonly property color textMuted: highContrast ? preset.textSecondary : preset.textMuted
    readonly property color disabledText: preset.disabledText
    readonly property color accent: dynamic && preferencesAvailable ? preferencesController.accentColor : preset.accent
    readonly property color accentStrong: Qt.darker(accent, 1.16)
    readonly property color accentSoft: mix(accent, surface, dark ? 0.22 : 0.10)
    readonly property color accentSofter: mix(accent, surface, dark ? 0.12 : 0.055)
    readonly property color navHover: mix(accent, surfaceSoft, dark ? 0.20 : 0.075)
    readonly property color navPressed: mix(accent, surfaceSoft, dark ? 0.30 : 0.14)
    readonly property color navSelected: mix(accent, surfaceSoft, dark ? 0.36 : 0.20)
    readonly property color success: preset.success
    readonly property color successSoft: mix(success, surface, dark ? 0.17 : 0.08)
    readonly property color successBorder: mix(success, border, 0.42)
    readonly property color warning: preset.warning
    readonly property color warningSoft: mix(warning, surface, dark ? 0.18 : 0.08)
    readonly property color error: preset.error
    readonly property color errorSoft: mix(error, surface, dark ? 0.18 : 0.08)
    readonly property color errorBorder: mix(error, border, 0.42)
    readonly property color info: preset.info
    readonly property color workspaceOverlay: dark ? "#d90b1220" : "#b8f8fafc"
    readonly property color drawerScrim: dark ? "#78000000" : "#520f172a"
    readonly property color accentText: "#ffffff"
    readonly property color tooltipSurface: dark ? "#e8f1fc" : "#172033"
    readonly property color tooltipBorder: dark ? "#bfd0e4" : "#2b3a51"
    readonly property color tooltipText: dark ? "#172033" : "#f8fbff"
    readonly property real shadowOpacity: preset.shadowOpacity

    function mix(foreground, background, ratio) {
        return Qt.rgba(
            foreground.r * ratio + background.r * (1 - ratio),
            foreground.g * ratio + background.g * (1 - ratio),
            foreground.b * ratio + background.b * (1 - ratio),
            1
        )
    }

    function presetTokens(name) {
        const values = {
            scholar_light: {
                mode: "light", canvas: "#f8fafc", canvasTop: "#fbfdff", canvasBottom: "#f1f5f9",
                surface: "#ffffff", surfaceSoft: "#f5f8fc", border: "#e2e8f0", borderStrong: "#cbd5e1",
                text: "#0f172a", textSecondary: "#475569", textMuted: "#64748b", disabledText: "#94a3b8",
                accent: "#2563eb", success: "#059669", warning: "#d97706", error: "#dc2626", info: "#0891b2", shadowOpacity: 0.10
            },
            manuscript_sepia: {
                mode: "light", canvas: "#f7f1e3", canvasTop: "#fbf7ed", canvasBottom: "#efe5d2",
                surface: "#fffdf7", surfaceSoft: "#f8f1e5", border: "#e4d8c2", borderStrong: "#cdbb9e",
                text: "#30271d", textSecondary: "#685847", textMuted: "#806f5d", disabledText: "#a99884",
                accent: "#a16207", success: "#4d7c0f", warning: "#b45309", error: "#b91c1c", info: "#0e7490", shadowOpacity: 0.08
            },
            library_dark: {
                mode: "dark", canvas: "#0f172a", canvasTop: "#111c30", canvasBottom: "#0b1220",
                surface: "#172033", surfaceSoft: "#111c2e", border: "#2b3a51", borderStrong: "#40516a",
                text: "#e5eefb", textSecondary: "#cbd5e1", textMuted: "#9aacbf", disabledText: "#718096",
                accent: "#60a5fa", success: "#34d399", warning: "#fbbf24", error: "#f87171", info: "#22d3ee", shadowOpacity: 0.22
            },
            journal_blue: {
                mode: "light", canvas: "#f3f7fb", canvasTop: "#f8fbff", canvasBottom: "#eaf1f8",
                surface: "#ffffff", surfaceSoft: "#f0f6fc", border: "#d5e1ee", borderStrong: "#b9cce0",
                text: "#10243e", textSecondary: "#365875", textMuted: "#5c7892", disabledText: "#91a7ba",
                accent: "#1e3a8a", success: "#047857", warning: "#b45309", error: "#b91c1c", info: "#0369a1", shadowOpacity: 0.11
            },
            arxiv_minimal: {
                mode: "light", canvas: "#f7f7f6", canvasTop: "#fbfbfa", canvasBottom: "#eeeeec",
                surface: "#ffffff", surfaceSoft: "#f4f4f2", border: "#e1e1de", borderStrong: "#c8c8c3",
                text: "#20201e", textSecondary: "#51514d", textMuted: "#71716b", disabledText: "#9d9d96",
                accent: "#475569", success: "#15803d", warning: "#b45309", error: "#b91c1c", info: "#0e7490", shadowOpacity: 0.07
            },
            nature_green: {
                mode: "light", canvas: "#f4f8f5", canvasTop: "#f8fcf9", canvasBottom: "#eaf3ed",
                surface: "#ffffff", surfaceSoft: "#f0f7f2", border: "#d8e7dd", borderStrong: "#bdd4c5",
                text: "#153326", textSecondary: "#3f6354", textMuted: "#668477", disabledText: "#94aaa1",
                accent: "#059669", success: "#047857", warning: "#b45309", error: "#be123c", info: "#0e7490", shadowOpacity: 0.09
            }
        }
        return values[name] || values.scholar_light
    }
}
