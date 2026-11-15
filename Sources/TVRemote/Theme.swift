import SwiftUI
import AppKit

/// Design tokens shared with the feature site (docs/style.css) and the phone page (helper/web/index.html):
/// dark navy surfaces with an indigo-to-violet accent. Surfaces follow the system light/dark setting like the site does.
enum Theme {
    static let bg = adaptive(dark: 0x0b0d12, light: 0xf6f7fb)
    static let card = adaptive(dark: 0x141821, light: 0xffffff)
    static let chip = adaptive(dark: 0x1b2030, light: 0xeef1f8)
    static let line = adaptive(dark: 0x262c3d, light: 0xdde2ee)
    static let muted = adaptive(dark: 0x9aa3b8, light: 0x5a6378)

    static let accent = hex(0x5b8cff)
    static let accent2 = hex(0xa46bff)
    static let green = hex(0x3ccf91)
    static let red = hex(0xff5d6c)
    static let amber = hex(0xffb547)
    static let orange = hex(0xff7a45)
    static let lavender = adaptive(dark: 0xb9a6ff, light: 0x7a5cff)

    static let gradient = LinearGradient(colors: [accent, accent2], startPoint: .topLeading, endPoint: .bottomTrailing)

    static let radius: CGFloat = 16
    static let radiusSmall: CGFloat = 12

    static func hex(_ v: UInt32) -> Color { Color(nsColor: nsHex(v)) }

    private static func nsHex(_ v: UInt32) -> NSColor {
        NSColor(srgbRed: CGFloat((v >> 16) & 0xff) / 255, green: CGFloat((v >> 8) & 0xff) / 255,
                blue: CGFloat(v & 0xff) / 255, alpha: 1)
    }

    private static func adaptive(dark: UInt32, light: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? nsHex(dark) : nsHex(light)
        })
    }
}

/// The site's toggle: a capsule track that fills with the accent gradient when on.
struct GradientSwitch: ToggleStyle {
    @Environment(\.controlSize) private var controlSize
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let small = controlSize == .small || controlSize == .mini
        let w: CGFloat = small ? 30 : 38, h: CGFloat = small ? 18 : 22
        let track = Button { configuration.isOn.toggle() } label: {
            ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                Capsule().fill(configuration.isOn ? AnyShapeStyle(Theme.gradient) : AnyShapeStyle(Theme.line))
                Circle().fill(.white).padding(2).shadow(color: .black.opacity(0.25), radius: 1, y: 0.5)
            }
            .frame(width: w, height: h)
            .animation(.easeOut(duration: 0.15), value: configuration.isOn)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.45)
        return HStack(spacing: 8) {
            configuration.label
            track
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityValue(configuration.isOn ? "On" : "Off")
    }
}

extension View {
    /// Capsule filter pill; the selected one gets the accent gradient.
    func pill(selected: Bool) -> some View {
        self
            .background(Capsule().fill(selected ? AnyShapeStyle(Theme.gradient) : AnyShapeStyle(Theme.chip)))
            .overlay(Capsule().stroke(selected ? Color.clear : Theme.line, lineWidth: 1))
            .foregroundStyle(selected ? Color.white : Color.primary)
    }

    /// Card surface: slightly lighter than the window, rounded, with a thin border.
    func themedCard(radius: CGFloat = Theme.radius, fill: Color = Theme.card, stroke: Color = Theme.line) -> some View {
        self.background(RoundedRectangle(cornerRadius: radius, style: .continuous).fill(fill))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).stroke(stroke, lineWidth: 1))
    }
}
