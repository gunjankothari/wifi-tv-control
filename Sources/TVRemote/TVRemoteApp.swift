import SwiftUI

@main
struct TVRemoteApp: App {
    @StateObject private var store = Store()

    init() {
        NSApplication.shared.setActivationPolicy(.accessory)
    }

    /// A green TV while any TV is on, otherwise the plain outline that follows the menu bar's colour.
    private var menuIcon: NSImage {
        if store.anyTVOn {
            let config = NSImage.SymbolConfiguration(pointSize: 15, weight: .medium)
                .applying(NSImage.SymbolConfiguration(paletteColors: [.systemGreen]))
            let image = NSImage(systemSymbolName: "tv.fill", accessibilityDescription: "A TV is on")?
                .withSymbolConfiguration(config) ?? NSImage()
            image.isTemplate = false          // keep the green; template images are drawn in one colour
            return image
        }
        let image = NSImage(systemSymbolName: "tv", accessibilityDescription: "TV Remote") ?? NSImage()
        image.isTemplate = true
        return image
    }

    var body: some Scene {
        MenuBarExtra {
            ContentView(store: store)
        } label: {
            Image(nsImage: menuIcon)
        }
        .menuBarExtraStyle(.window)
    }
}
