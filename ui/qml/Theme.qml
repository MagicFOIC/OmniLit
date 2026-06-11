import QtQuick

QtObject {
    property bool dynamic: true
    readonly property bool preferencesAvailable: typeof preferencesController !== "undefined"
    readonly property string presetName: dynamic && preferencesAvailable ? preferencesController.effectiveThemePreset : "scholar_light"
    readonly property string modeName: dynamic && preferencesAvailable ? preferencesController.effectiveThemeMode : "light"
    readonly property var preset: presetTokens(presetName, modeName === "dark")
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
    readonly property color surfaceElevated: mix(accent, surface, dark ? 0.035 : 0.018)
    readonly property color surfaceTint: mix(accent, surface, dark ? 0.10 : 0.045)
    readonly property color sidebarSurface: mix(accent, surfaceSoft, dark ? 0.055 : 0.025)
    readonly property color sidebarBorder: mix(accent, border, dark ? 0.15 : 0.08)
    readonly property color border: highContrast ? preset.borderStrong : preset.border
    readonly property color borderStrong: highContrast ? preset.textMuted : preset.borderStrong
    readonly property color divider: mix(accent, border, dark ? 0.12 : 0.055)
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
    readonly property color presence: success
    readonly property color warning: preset.warning
    readonly property color warningSoft: mix(warning, surface, dark ? 0.18 : 0.08)
    readonly property color error: preset.error
    readonly property color errorSoft: mix(error, surface, dark ? 0.18 : 0.08)
    readonly property color errorBorder: mix(error, border, 0.42)
    readonly property color info: preset.info
    readonly property color workspaceOverlay: dark ? "#d90b1220" : "#b8f8fafc"
    readonly property color drawerScrim: dark ? "#78000000" : "#520f172a"
    readonly property color accentText: "#ffffff"
    readonly property color tooltipSurface: mix(accent, surfaceElevated, dark ? 0.08 : 0.035)
    readonly property color tooltipBorder: mix(accent, border, dark ? 0.24 : 0.18)
    readonly property color tooltipText: text
    readonly property real shadowOpacity: preset.shadowOpacity

    function mix(foreground, background, ratio) {
        return Qt.rgba(
            foreground.r * ratio + background.r * (1 - ratio),
            foreground.g * ratio + background.g * (1 - ratio),
            foreground.b * ratio + background.b * (1 - ratio),
            1
        )
    }

    function presetTokens(name, useDark) {
        const light = {
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
            },
            citation_purple: {
                mode: "light", canvas: "#f8f6fc", canvasTop: "#fcfbff", canvasBottom: "#f1ecf8",
                surface: "#ffffff", surfaceSoft: "#f7f2fc", border: "#e5d9f2", borderStrong: "#cdb9e3",
                text: "#2d1f3d", textSecondary: "#604b75", textMuted: "#806b93", disabledText: "#ad9dbb",
                accent: "#7c3aed", success: "#15803d", warning: "#c2410c", error: "#be123c", info: "#0369a1", shadowOpacity: 0.10
            },
            nordic_slate: {
                mode: "light", canvas: "#f1f5f4", canvasTop: "#f8fbfa", canvasBottom: "#e5edeb",
                surface: "#fcfefd", surfaceSoft: "#edf4f2", border: "#d2dfdc", borderStrong: "#b2c8c4",
                text: "#18312f", textSecondary: "#426461", textMuted: "#698783", disabledText: "#94aaa7",
                accent: "#0f766e", success: "#15803d", warning: "#b45309", error: "#be123c", info: "#0369a1", shadowOpacity: 0.08
            },
            focus_amber: {
                mode: "light", canvas: "#fcf8ef", canvasTop: "#fffdf8", canvasBottom: "#f5ecd8",
                surface: "#fffefb", surfaceSoft: "#faf3e4", border: "#eadbbe", borderStrong: "#d7c29b",
                text: "#3a2c17", textSecondary: "#705937", textMuted: "#8b7452", disabledText: "#b2a083",
                accent: "#d97706", success: "#4d7c0f", warning: "#b45309", error: "#b91c1c", info: "#0369a1", shadowOpacity: 0.08
            }
        }
        const dark = {
            scholar_light: {
                mode: "dark", canvas: "#0b1220", canvasTop: "#111c30", canvasBottom: "#08101d",
                surface: "#172033", surfaceSoft: "#111c2e", border: "#2b3a51", borderStrong: "#40516a",
                text: "#e5eefb", textSecondary: "#cbd5e1", textMuted: "#9aacbf", disabledText: "#718096",
                accent: "#60a5fa", success: "#34d399", warning: "#fbbf24", error: "#f87171", info: "#22d3ee", shadowOpacity: 0.22
            },
            manuscript_sepia: {
                mode: "dark", canvas: "#211b16", canvasTop: "#2b231c", canvasBottom: "#18130f",
                surface: "#30271f", surfaceSoft: "#261f19", border: "#504235", borderStrong: "#705d49",
                text: "#f3e8d4", textSecondary: "#d5c3a8", textMuted: "#b29e83", disabledText: "#88755f",
                accent: "#f59e0b", success: "#84cc16", warning: "#fbbf24", error: "#fb7185", info: "#22d3ee", shadowOpacity: 0.20
            },
            journal_blue: {
                mode: "dark", canvas: "#08162a", canvasTop: "#102440", canvasBottom: "#06101f",
                surface: "#122b4c", surfaceSoft: "#0d213b", border: "#24486d", borderStrong: "#37658f",
                text: "#e4f0ff", textSecondary: "#bdd4ee", textMuted: "#92b0d0", disabledText: "#6788aa",
                accent: "#7cb7ff", success: "#34d399", warning: "#fbbf24", error: "#fb7185", info: "#22d3ee", shadowOpacity: 0.24
            },
            arxiv_minimal: {
                mode: "dark", canvas: "#171817", canvasTop: "#202220", canvasBottom: "#101110",
                surface: "#252725", surfaceSoft: "#1d1f1d", border: "#3b403c", borderStrong: "#565d58",
                text: "#f0f2ef", textSecondary: "#ccd1cc", textMuted: "#a6ada7", disabledText: "#777e78",
                accent: "#94a3b8", success: "#4ade80", warning: "#fbbf24", error: "#fb7185", info: "#67e8f9", shadowOpacity: 0.19
            },
            nature_green: {
                mode: "dark", canvas: "#0b1d18", canvasTop: "#123129", canvasBottom: "#071511",
                surface: "#163a31", surfaceSoft: "#102d26", border: "#28574d", borderStrong: "#3c786c",
                text: "#e1f5ef", textSecondary: "#b7ded4", textMuted: "#8ebdb1", disabledText: "#628f84",
                accent: "#34d399", success: "#4ade80", warning: "#fbbf24", error: "#fb7185", info: "#67e8f9", shadowOpacity: 0.22
            },
            citation_purple: {
                mode: "dark", canvas: "#1b1028", canvasTop: "#28173c", canvasBottom: "#130b1d",
                surface: "#321d4a", surfaceSoft: "#27173b", border: "#50326c", borderStrong: "#704b91",
                text: "#f3e8ff", textSecondary: "#dac1ef", textMuted: "#b897d1", disabledText: "#87699f",
                accent: "#c084fc", success: "#4ade80", warning: "#fbbf24", error: "#fb7185", info: "#67e8f9", shadowOpacity: 0.23
            },
            nordic_slate: {
                mode: "dark", canvas: "#10201f", canvasTop: "#18302e", canvasBottom: "#0a1716",
                surface: "#203b39", surfaceSoft: "#192f2e", border: "#365654", borderStrong: "#527472",
                text: "#e4f2f0", textSecondary: "#c0d8d5", textMuted: "#98b8b4", disabledText: "#6d918d",
                accent: "#5eead4", success: "#4ade80", warning: "#fbbf24", error: "#fb7185", info: "#67e8f9", shadowOpacity: 0.20
            },
            focus_amber: {
                mode: "dark", canvas: "#21170b", canvasTop: "#32230f", canvasBottom: "#160f07",
                surface: "#3b2b17", surfaceSoft: "#302211", border: "#604924", borderStrong: "#806538",
                text: "#fff3d7", textSecondary: "#ead2a0", textMuted: "#c4a873", disabledText: "#967b4c",
                accent: "#fbbf24", success: "#84cc16", warning: "#f59e0b", error: "#fb7185", info: "#67e8f9", shadowOpacity: 0.22
            }
        }
        const values = useDark ? dark : light
        return values[name] || values.scholar_light
    }
}
