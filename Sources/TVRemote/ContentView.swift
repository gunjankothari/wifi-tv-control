import SwiftUI
import Charts

// MARK: - Button styles

struct CircleKey: ButtonStyle {
    var size: CGFloat = 44
    var tint: Color = .primary
    var filled = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: size * 0.38, weight: .semibold))
            .foregroundStyle(filled ? Color.white : tint)
            .frame(width: size, height: size)
            .background(Circle().fill(filled ? tint : Color.primary.opacity(configuration.isPressed ? 0.20 : 0.08)))
            .scaleEffect(configuration.isPressed ? 0.92 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .contentShape(Circle())
    }
}

struct Tile: ButtonStyle {
    var color: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 38)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(color.gradient))
            .opacity(configuration.isPressed ? 0.75 : 1)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.primary.opacity(0.05)))
    }
}

// MARK: - Main view

struct ContentView: View {
    @ObservedObject var store: Store
    @State private var newChannel = ""
    @State private var newBlocked = ""
    @State private var scrub: Double?
    @State private var volDrag: Double?
    @State private var limitDrag: Double?

    private var tv: TV? { store.status?.tvs.first { $0.id == store.selectedTV } }
    private var rules: RuleSet? { store.status?.rules[store.selectedTV] }
    private var parent: ParentState? { store.status?.parent[store.selectedTV] }

    var body: some View {
        VStack(spacing: 12) {
            header
            if parent?.active == true, let tv { parentBanner(tv) }
            if let tv {
                Picker("", selection: $store.tab) {
                    Text("Remote").tag(0)
                    Text("Search").tag(1)
                    Text("Rules").tag(2)
                    Text("History").tag(3)
                }
                .pickerStyle(.segmented).labelsHidden()
                if store.tab == 0 {
                    nowPlaying(tv)
                    controls(tv)
                    apps
                    cameraCard(tv)
                    mediaCard(tv)
                } else if store.tab == 1 {
                    searchSection(tv)
                } else if store.tab == 2 {
                    rulesView
                } else {
                    historyView
                }
            } else {
                Card {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text(store.error ?? "Connecting…").foregroundStyle(.secondary)
                    }
                }
            }
            footer
        }
        .padding(14)
        .frame(width: 340)
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 8) {
            ForEach(store.status?.tvs ?? []) { t in
                let selected = t.id == store.selectedTV
                Button { store.selectedTV = t.id } label: {
                    HStack(spacing: 6) {
                        Circle().fill(dotColor(t)).frame(width: 7, height: 7)
                        if store.status?.parent[t.id]?.active == true {
                            Image(systemName: "person.fill.checkmark").font(.system(size: 9))
                        }
                        VStack(alignment: .leading, spacing: 1) {
                            Text(t.name).font(.system(size: 12, weight: .semibold))
                            Text(t.ip).font(.system(size: 9).monospacedDigit()).opacity(0.65)
                        }
                        .lineLimit(1).fixedSize()
                    }
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(Capsule().fill(selected ? Color.accentColor.opacity(0.9) : Color.primary.opacity(0.08)))
                    .foregroundStyle(selected ? Color.white : Color.primary)
                }
                .buttonStyle(.plain)
            }
            Spacer()
            Button {
                if tv?.online == true && tv?.on == true { store.key("POWER") } else { store.wake() }
            } label: { Image(systemName: "power") }
                .buttonStyle(CircleKey(size: 32, tint: .red, filled: tv?.on == true))
                .disabled(tv == nil)
                .help(tv?.on == true ? "Turn off" : "Wake the TV")
        }
    }

    private func dotColor(_ t: TV) -> Color {
        switch t.power {
        case "standby": return .orange
        case "deep_sleep": return .yellow
        case "off": return .gray
        default: return !t.online ? .gray : (t.on == false ? .orange : .green)
        }
    }

    // MARK: Now playing

    private func hms(_ seconds: Double) -> String {
        let s = Int(max(0, seconds))
        return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60)
                         : String(format: "%d:%02d", s / 60, s % 60)
    }

    private func nowPlaying(_ tv: TV) -> some View {
        let canControl = tv.online && tv.on == true && tv.appKey != "home" && tv.app != "Screensaver"
        let cam = store.status?.camera
        let cameraHere = cam?.on == true && cam?.tv == tv.id
        return VStack(spacing: 8) {
            if cameraHere {
                TVSet { cameraScreen }
            } else {
                Button { store.playback("toggle") } label: {
                    TVSet {
                        nowPlayingCard(tv).overlay(alignment: .topLeading) { statusBadge(tv) }
                            .overlay { pausedMark(tv) }
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canControl)
                .help(tv.playerState == "PLAYING" ? "Click to pause" : "Click to play")
            }
            if canControl, !cameraHere, let d = tv.duration, d > 0 { playerBar(tv, duration: d) }
        }
    }

    @ViewBuilder
    private func statusBadge(_ tv: TV) -> some View {
        let info: (String, String, Color)? = {
            switch tv.playerState {
            case "PLAYING": return ("play.fill", "Playing", .green)
            case "PAUSED": return ("pause.fill", "Paused", .orange)
            case "BUFFERING": return ("hourglass", "Buffering", .yellow)
            default: return nil
            }
        }()
        if let (symbol, text, color) = info, tv.on != false {
            HStack(spacing: 5) {
                Image(systemName: symbol).font(.system(size: 9))
                Text(text).font(.system(size: 10, weight: .bold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(Capsule().fill(color.opacity(0.85)))
            .padding(10)
        }
    }

    @ViewBuilder
    private func pausedMark(_ tv: TV) -> some View {
        if tv.playerState == "PAUSED" && tv.on != false {
            Image(systemName: "play.circle.fill").font(.system(size: 52)).foregroundStyle(.white.opacity(0.92))
                .shadow(radius: 6)
        }
    }

    private func playerBar(_ tv: TV, duration d: Double) -> some View {
        Card {
            TimelineView(.periodic(from: .now, by: 1)) { ctx in
                let elapsed = tv.playing == true ? ctx.date.timeIntervalSince(store.statusAt) : 0
                let pos = min(d, max(0, (tv.position ?? 0) + elapsed))
                let shown = scrub ?? pos
                VStack(spacing: 6) {
                    Slider(value: Binding(get: { shown }, set: { scrub = $0 }), in: 0...max(d, 1)) { editing in
                        if !editing, let v = scrub { store.playback("seek", position: v); scrub = nil }
                    }
                    .disabled(tv.canSeek != true)
                    HStack {
                        Text("\(hms(shown)) played").frame(maxWidth: .infinity, alignment: .leading)
                        Text("\(hms(d)) total").frame(maxWidth: .infinity, alignment: .center)
                        Text("\(hms(d - shown)) left").frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .font(.system(size: 10, weight: .medium)).monospacedDigit().foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        skipButton("gobackward.30", -30, tv)
                        skipButton("gobackward.10", -10, tv)
                        Button { store.playback("toggle") } label: {
                            Image(systemName: tv.playerState == "PLAYING" ? "pause.fill" : "play.fill")
                        }
                        .buttonStyle(CircleKey(size: 40, tint: .accentColor, filled: true))
                        skipButton("goforward.10", 10, tv)
                        skipButton("goforward.30", 30, tv)
                    }
                }
            }
        }
    }

    private func skipButton(_ symbol: String, _ seconds: Double, _ tv: TV) -> some View {
        Button { store.playback("skip", delta: seconds) } label: { Image(systemName: symbol) }
            .buttonStyle(CircleKey(size: 34))
            .disabled(tv.canSeek != true)
    }

    @ViewBuilder
    private func nowPlayingCard(_ tv: TV) -> some View {
        ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color.primary.opacity(0.06))
            if let thumb = tv.thumb, let url = URL(string: thumb), tv.on != false {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image): image.resizable().aspectRatio(contentMode: .fill)
                    default: placeholder(tv)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                LinearGradient(colors: [.clear, .black.opacity(0.8)], startPoint: .center, endPoint: .bottom)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                caption(tv, onImage: true)
            } else if tv.on != false, tv.online, let b = brand(tv.appKey) {
                RoundedRectangle(cornerRadius: 16, style: .continuous).fill(b.color.gradient)
                Image(systemName: b.symbol)
                    .font(.system(size: 54, weight: .light)).foregroundStyle(.white.opacity(0.9))
                    .frame(maxWidth: .infinity, maxHeight: .infinity).padding(.bottom, 30)
                caption(tv, onImage: true)
            } else {
                placeholder(tv)
                caption(tv, onImage: false)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipped()
    }

    /// TVs report a video preview only for YouTube, so every other app gets its branded card.
    private func brand(_ key: String?) -> (symbol: String, color: Color)? {
        switch key {
        case "youtube": return ("play.rectangle.fill", Color(red: 0.92, green: 0.12, blue: 0.14))
        case "primevideo": return ("play.fill", Color(red: 0.0, green: 0.66, blue: 0.88))
        case "netflix": return ("n.square.fill", Color(red: 0.55, green: 0.0, blue: 0.08))
        case "hotstar": return ("star.fill", Color(red: 0.08, green: 0.12, blue: 0.35))
        case "sonyliv": return ("tv.fill", Color(red: 0.25, green: 0.25, blue: 0.30))
        case "zee5": return ("5.square.fill", Color(red: 0.45, green: 0.15, blue: 0.70))
        case "home": return ("house.fill", Color(red: 0.20, green: 0.25, blue: 0.35))
        case "other": return ("square.grid.2x2.fill", Color(red: 0.30, green: 0.32, blue: 0.38))
        default: return nil
        }
    }

    private func placeholder(_ tv: TV) -> some View {
        VStack(spacing: 6) {
            Image(systemName: icon(tv)).font(.system(size: 34, weight: .light)).foregroundStyle(.secondary)
            if tv.on == false || !tv.online { Text(tv.powerLabel).font(.callout).foregroundStyle(.secondary) }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 34)
    }

    private func icon(_ tv: TV) -> String {
        if !tv.online { return "wifi.slash" }
        if tv.on == false { return "tv.slash" }
        switch tv.app {
        case "YouTube": return "play.rectangle.fill"
        case "Prime Video", "Netflix": return "film"
        default: return "tv"
        }
    }

    private func caption(_ tv: TV, onImage: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let title = tv.title, tv.on != false {
                Text(title).font(.system(size: 13, weight: .semibold)).lineLimit(2)
                Text([tv.channel, tv.app].compactMap { $0 }.joined(separator: " · "))
                    .font(.system(size: 11)).opacity(0.8)
                if let d = tv.duration, d > 0, let p = tv.position {
                    ProgressView(value: min(p, d), total: d).tint(onImage ? Color.white : Color.accentColor)
                }
            } else {
                Text(tv.online && tv.on != false ? (tv.app ?? "On") : tv.powerLabel)
                    .font(.system(size: 13, weight: .semibold))
                Text(tv.online && tv.on != false ? tv.ip : (tv.sinceLabel ?? tv.ip)).font(.system(size: 11)).opacity(0.8)
            }
        }
        .foregroundStyle(onImage ? Color.white : Color.primary)
        .padding(12)
    }

    // MARK: Controls

    private func controls(_ tv: TV) -> some View {
        Card {
            VStack(spacing: 12) {
                HStack(spacing: 14) {
                    dpad
                    VStack(spacing: 10) {
                        Button { store.key("BACK") } label: { Image(systemName: "arrow.uturn.backward") }
                            .buttonStyle(CircleKey(size: 40))
                        Button { store.key("HOME") } label: { Image(systemName: "house.fill") }
                            .buttonStyle(CircleKey(size: 40, tint: .accentColor, filled: true))
                    }
                    Spacer(minLength: 0)
                    volume(tv)
                }
            }
        }
        .disabled(!tv.online || tv.on == false)
        .opacity(tv.online && tv.on != false ? 1 : 0.5)
    }

    private var dpad: some View {
        Grid(horizontalSpacing: 4, verticalSpacing: 4) {
            GridRow { spacer; dpadKey("chevron.up", "DPAD_UP"); spacer }
            GridRow {
                dpadKey("chevron.left", "DPAD_LEFT")
                Button { store.key("DPAD_CENTER") } label: { Text("OK").font(.system(size: 12, weight: .bold)) }
                    .buttonStyle(CircleKey(size: 38, tint: .accentColor, filled: true))
                dpadKey("chevron.right", "DPAD_RIGHT")
            }
            GridRow { spacer; dpadKey("chevron.down", "DPAD_DOWN"); spacer }
        }
    }

    private var spacer: some View { Color.clear.frame(width: 34, height: 34) }

    private func dpadKey(_ symbol: String, _ code: String) -> some View {
        Button { store.key(code) } label: { Image(systemName: symbol) }
            .buttonStyle(CircleKey(size: 34))
    }

    private func volume(_ tv: TV) -> some View {
        let level = Double(tv.volume?.level ?? 0)
        let shown = volDrag ?? level
        return VStack(spacing: 4) {
            Button { store.key("VOLUME_UP") } label: { Image(systemName: "plus") }
                .buttonStyle(CircleKey(size: 26))
            Text(tv.volume?.muted == true && volDrag == nil ? "Mute" : "\(Int(shown))")
                .font(.system(size: 12, weight: .semibold, design: .rounded)).monospacedDigit()
                .frame(width: 34)
            verticalSlider(shown)
            Button { store.key("VOLUME_DOWN") } label: { Image(systemName: "minus") }
                .buttonStyle(CircleKey(size: 26))
            Button { store.key("MUTE") } label: {
                Image(systemName: tv.volume?.muted == true ? "speaker.slash.fill" : "speaker.wave.2.fill")
            }
            .buttonStyle(CircleKey(size: 26, tint: .orange, filled: tv.volume?.muted == true))
        }
    }

    /// A vertical volume slider drawn by hand (loudest at the top); drag or tap anywhere on it.
    private func verticalSlider(_ shown: Double) -> some View {
        let height: CGFloat = 96, thumb: CGFloat = 18
        let travel = height - thumb
        return ZStack(alignment: .bottom) {
            Capsule().fill(Color.primary.opacity(0.18)).frame(width: 8)
            Capsule().fill(Color.accentColor).frame(width: 8, height: thumb / 2 + travel * CGFloat(shown / 100))
            Circle().fill(.white).overlay(Circle().stroke(Color.primary.opacity(0.3), lineWidth: 1))
                .shadow(color: .black.opacity(0.25), radius: 1.5, y: 1)
                .frame(width: thumb, height: thumb)
                .offset(y: -travel * CGFloat(shown / 100))
        }
        .frame(width: 34, height: height)
        .contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance: 0)
            .onChanged { g in
                let frac = 1 - (g.location.y - thumb / 2) / travel
                volDrag = (min(max(Double(frac), 0), 1) * 100).rounded()
            }
            .onEnded { _ in
                guard let v = volDrag else { return }
                store.setVolume(Int(v))
                Task {                                     // hold the dragged value until the TV reports the new level
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    volDrag = nil
                }
            })
    }

    // MARK: Apps

    private var apps: some View {
        Grid(horizontalSpacing: 8, verticalSpacing: 8) {
            GridRow {
                appTile("Prime", "play.fill", "primevideo", Color(red: 0.0, green: 0.66, blue: 0.88))
                appTile("YouTube", "play.rectangle.fill", "youtube", Color(red: 0.92, green: 0.12, blue: 0.14))
                appTile("Netflix", "n.square.fill", "netflix", Color(red: 0.55, green: 0.0, blue: 0.08))
            }
            GridRow {
                appTile("Hotstar", "star.fill", "hotstar", Color(red: 0.08, green: 0.12, blue: 0.35))
                appTile("SonyLIV", "tv.fill", "sonyliv", Color(red: 0.25, green: 0.25, blue: 0.30))
                appTile("ZEE5", "5.square.fill", "zee5", Color(red: 0.45, green: 0.15, blue: 0.70))
            }
        }
        .disabled(tv?.online != true || tv?.on == false)
    }

    private func appTile(_ label: String, _ symbol: String, _ app: String, _ color: Color) -> some View {
        Button { store.launch(app) } label: { Label(label, systemImage: symbol) }
            .buttonStyle(Tile(color: color))
    }

    // MARK: Camera

    private func cameraCard(_ tv: TV) -> some View {
        let cam = store.status?.camera
        let live = cam?.on == true
        let liveHere = live && cam?.tv == tv.id
        let liveElsewhere = live && !liveHere
        return Card {
            VStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: live ? "video.fill" : "video")
                    .font(.system(size: 18))
                    .foregroundStyle(live ? Color.red : Color.accentColor)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Show my camera").font(.system(size: 13, weight: .semibold))
                    Text(liveHere ? "Live on \(tv.name), shown on the TV above" :
                         liveElsewhere ? "Live on the other TV — switch to move it here" :
                         "Mac camera and mic, a few seconds behind")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("", isOn: Binding(
                    get: { liveHere },
                    set: { store.setCamera($0) }))
                .toggleStyle(.switch).labelsHidden()
                .disabled(!tv.online || tv.on == false)
            }
            }
        }
    }

    private func mediaCard(_ tv: TV) -> some View {
        let media = store.status?.media
        let live = media?.on == true && media?.tv == tv.id
        let elsewhere = media?.on == true && media?.tv != tv.id
        return Card {
            HStack(spacing: 10) {
                Image(systemName: live ? "play.rectangle.on.rectangle.fill" : "play.rectangle.on.rectangle")
                    .font(.system(size: 18)).foregroundStyle(Color.accentColor).frame(width: 22)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Play from this Mac").font(.system(size: 13, weight: .semibold))
                    Text(live ? "\(media?.name ?? "Playing") on \(tv.name)" :
                         elsewhere ? "Playing on the other TV" : "A video or photos, shown on \(tv.name)")
                        .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                if live {
                    Button("Stop") { store.stopMedia() }.buttonStyle(.borderedProminent).tint(.red).controlSize(.small)
                } else {
                    Button("Choose…") { store.chooseMedia() }.controlSize(.small)
                        .disabled(!tv.online || tv.on == false)
                }
            }
        }
    }

    /// The camera as the TV is showing it (same stream, same delay), drawn on the TV screen above.
    private var cameraScreen: some View {
        ZStack(alignment: .topLeading) {
            CameraPreview(muted: store.previewMuted)
            HStack(spacing: 4) {
                Circle().fill(.red).frame(width: 6, height: 6)
                Text("LIVE camera").font(.system(size: 10, weight: .bold))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(Capsule().fill(.black.opacity(0.6))).padding(8)
            HStack {
                Spacer()
                VStack {
                    Spacer()
                    Button { store.previewMuted.toggle() } label: {
                        Image(systemName: store.previewMuted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                    }
                    .buttonStyle(CircleKey(size: 28, tint: .orange, filled: !store.previewMuted))
                    .help(store.previewMuted ? "Hear the preview (may echo with the TV)" : "Mute preview")
                    .padding(8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
    }

    // MARK: Search

    private func searchSection(_ tv: TV) -> some View {
        let canPlay = tv.online && tv.on != false
        return VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField(tv.searchApp.map { "Search \($0) on \(tv.name)" } ?? "Open an app on the TV to search",
                          text: $store.query)
                    .textFieldStyle(.plain)
                    .disabled(tv.searchApp == nil)
                    .onSubmit { tv.appKey == "youtube" ? store.search() : store.typeOnTV(openSearch: true) }
                if store.searching {
                    ProgressView().controlSize(.small)
                } else if !store.query.isEmpty {
                    Button {
                        store.query = ""; store.results = []; store.searchError = nil
                    } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12).padding(.vertical, 9)
            .background(Capsule().fill(Color.primary.opacity(0.08)))
            .opacity(tv.searchApp == nil ? 0.5 : 1)

            if tv.searchApp == nil {
                Text(tv.on == false ? "The TV is off." : "Search follows the app that's open on the TV. Open one first.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if tv.appKey != "youtube" {
                HStack(spacing: 8) {
                    Button { store.typeOnTV(openSearch: true) } label: {
                        Label("Search", systemImage: "magnifyingglass")
                    }
                    .buttonStyle(Tile(color: .accentColor))
                    Button { store.typeOnTV(openSearch: false) } label: {
                        Label("Type only", systemImage: "keyboard")
                    }
                    .buttonStyle(Tile(color: .gray))
                }
                Text("Search presses the TV's search key, then types for you. If the search screen is already open, use Type only. Results show on the TV, because \(tv.searchApp ?? "the app") doesn't share them.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let err = store.searchError, tv.appKey == "youtube" {
                Text(err).font(.caption).foregroundStyle(.secondary)
            }
            if tv.appKey == "youtube", !store.results.isEmpty {
                ScrollView {
                    VStack(spacing: 6) {
                        ForEach(store.results) { r in
                            Button { store.play(r.id) } label: { resultRow(r) }
                                .buttonStyle(.plain)
                                .disabled(!canPlay)
                        }
                    }
                }
                .frame(height: 340)
                .opacity(canPlay ? 1 : 0.5)
            }
        }
    }

    private func resultRow(_ r: SearchResult) -> some View {
        HStack(spacing: 10) {
            ZStack(alignment: .bottomTrailing) {
                AsyncImage(url: URL(string: r.thumb)) { phase in
                    if case .success(let image) = phase {
                        image.resizable().aspectRatio(contentMode: .fill)
                    } else {
                        Color.primary.opacity(0.08)
                    }
                }
                .frame(width: 96, height: 54)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                if let d = r.duration {
                    Text(d).font(.system(size: 9, weight: .semibold)).foregroundStyle(.white)
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(Capsule().fill(.black.opacity(0.75))).padding(3)
                }
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(r.title).font(.system(size: 12, weight: .medium)).lineLimit(2)
                Text(r.channel).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 0)
            Image(systemName: "play.circle.fill").foregroundStyle(Color.accentColor).font(.system(size: 18))
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.primary.opacity(0.05)))
        .contentShape(Rectangle())
    }

    // MARK: Kid filter

    private var filterCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.system(size: 18)).foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Kid filter").font(.system(size: 13, weight: .semibold))
                        Text("Sends Home when a YouTube title is flagged")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Toggle("", isOn: Binding(
                        get: { rules?.titleFilter.enabled ?? false },
                        set: { store.setRule("title_filter", ["enabled": $0]) }))
                    .toggleStyle(.switch).labelsHidden()
                    .disabled(store.status == nil)
                }
                let blocked = Array((store.status?.filter.blocked ?? []).filter { $0.tv == tv?.name }.prefix(3))
                if !blocked.isEmpty {
                    Divider()
                    ForEach(blocked) { b in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Image(systemName: "hand.raised.fill").font(.system(size: 9)).foregroundStyle(.red)
                            Text(b.title).lineLimit(1)
                            Spacer(minLength: 4)
                            Text(b.time).foregroundStyle(.secondary)
                        }
                        .font(.system(size: 11))
                    }
                }
            }
        }
    }

    // MARK: Rules

    private var rulesView: some View {
        ScrollView {
            VStack(spacing: 10) {
                parentCard
                Text("Rules for \(tv?.name ?? "this TV")")
                    .font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                VStack(spacing: 10) {
                    filterCard
                    adultCard
                    volumeCapCard
                    screenTimeCard
                    bedtimeCard
                    allowChannelsCard
                    blockChannelsCard
                    shortsCard
                }
                .opacity(parent?.active == true ? 0.45 : 1)       // paused while parent mode is on
            }
        }
        .frame(height: 470)
    }

    // MARK: Parent mode

    private func timeLeftText(_ seconds: Int) -> String {
        let m = (seconds + 59) / 60
        return m >= 60 ? "\(m / 60) h \(m % 60) min" : "\(max(m, 1)) min"
    }

    /// Shown on every tab while parent mode is on, with a live countdown.
    private func parentBanner(_ tv: TV) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { ctx in
            let left = parent?.secondsLeft.map { max(0, $0 - Int(ctx.date.timeIntervalSince(store.statusAt))) }
            HStack(spacing: 8) {
                Image(systemName: "person.fill.checkmark").foregroundStyle(.white)
                VStack(alignment: .leading, spacing: 0) {
                    Text("Parent mode on").font(.system(size: 12, weight: .bold))
                    Text((left.map { "\(timeLeftText($0)) left · " } ?? "until you end it · ") + (parent?.scheduled == true ? "scheduled · " : "") + "no rules or tracking")
                        .font(.system(size: 10)).opacity(0.9)
                }
                Spacer()
                Button("End") { store.endParentMode() }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(Capsule().fill(.white.opacity(0.25)))
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.purple.gradient))
        }
    }

    private var parentCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "person.fill.checkmark").font(.system(size: 18))
                        .foregroundStyle(.purple).frame(width: 22)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Parent mode").font(.system(size: 13, weight: .semibold))
                        Text("No rules, no restrictions and no tracking on \(tv?.name ?? "this TV")")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                }
                if parent?.active == true {
                    HStack(spacing: 8) {
                        Button("Add 30 min") { store.startParentMode(minutes: (parent?.secondsLeft ?? 0) / 60 + 30) }
                            .disabled(parent?.secondsLeft == nil)
                        Button("End parent mode") { store.endParentMode() }.tint(.purple)
                    }
                    .controlSize(.small)
                } else {
                    Text("Switch on for:").font(.system(size: 11)).foregroundStyle(.secondary)
                    HStack(spacing: 6) {
                        ForEach([(30, "30 min"), (60, "1 h"), (120, "2 h"), (240, "4 h")], id: \.0) { m, label in
                            parentChip(label) { store.startParentMode(minutes: m) }
                        }
                        parentChip("Until I stop") { store.startParentMode(minutes: nil) }
                    }
                }
                Divider()
                scheduleRow
            }
        }
    }

    /// Parent mode that switches itself on and off at fixed times every day.
    private var scheduleRow: some View {
        let rule = rules?.parentSchedule
        return VStack(alignment: .leading, spacing: 6) {
            Toggle(isOn: Binding(get: { rule?.enabled ?? false },
                                 set: { store.setRule("parent_schedule", ["enabled": $0]) })) {
                Text("Every day at a fixed time").font(.system(size: 12, weight: .medium))
            }
            .toggleStyle(.switch).controlSize(.small)
            HStack(spacing: 8) {
                Text("From").font(.system(size: 12)).foregroundStyle(.secondary)
                DatePicker("", selection: timeBinding("start", rule?.start, rule: "parent_schedule"), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                Text("to").font(.system(size: 12)).foregroundStyle(.secondary)
                DatePicker("", selection: timeBinding("end", rule?.end, rule: "parent_schedule"), displayedComponents: .hourAndMinute)
                    .labelsHidden()
            }
            .opacity(rule?.enabled == true ? 1 : 0.5)
            Text("Pressing End inside the window turns it off until tomorrow.")
                .font(.system(size: 10)).foregroundStyle(.secondary)
        }
    }

    private func parentChip(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label).font(.system(size: 11, weight: .semibold)).frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(Capsule().fill(Color.purple.opacity(0.18)))
                .foregroundStyle(Color.purple)
        }
        .buttonStyle(.plain)
    }

    private func ruleHeader(_ symbol: String, _ title: String, _ subtitle: String, isOn: Binding<Bool>) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).font(.system(size: 18)).foregroundStyle(Color.accentColor).frame(width: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 13, weight: .semibold))
                Text(subtitle).font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            Toggle("", isOn: isOn).toggleStyle(.switch).labelsHidden().disabled(store.status == nil)
        }
    }

    private func duration(_ seconds: Int) -> String {
        let m = seconds / 60
        return m >= 60 ? "\(m / 60)h \(m % 60)m" : "\(m)m"
    }

    /// "45 min", "2 h", "1 h 30 min"
    private func limitText(_ minutes: Int) -> String {
        let h = minutes / 60, m = minutes % 60
        if h == 0 { return "\(m) min" }
        return m == 0 ? "\(h) h" : "\(h) h \(m) min"
    }

    private func limitChip(_ minutes: Int) -> String {
        switch minutes {
        case 30: return "30m"
        case 90: return "1½h"
        default: return "\(minutes / 60)h"
        }
    }

    private var screenTimeCard: some View {
        let rule = rules?.screenTime
        let minutes = rule?.minutes ?? 120
        let shownMinutes = Int(limitDrag ?? Double(minutes))
        return Card {
            VStack(alignment: .leading, spacing: 10) {
                ruleHeader("hourglass", "Daily screen time", "Turns the TV off when the limit is used up",
                           isOn: Binding(get: { rule?.enabled ?? false },
                                         set: { store.setRule("screen_time", ["enabled": $0]) }))
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(limitText(shownMinutes))
                        .font(.system(size: 24, weight: .bold, design: .rounded)).monospacedDigit()
                    Text("per day on this TV").font(.system(size: 12)).foregroundStyle(.secondary)
                }
                HStack(spacing: 6) {
                    ForEach([30, 60, 90, 120, 180, 240], id: \.self) { m in
                        Button { store.setRule("screen_time", ["minutes": m]) } label: {
                            Text(limitChip(m)).font(.system(size: 12, weight: .semibold)).frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                                .background(Capsule().fill(minutes == m ? Color.accentColor : Color.primary.opacity(0.08)))
                                .foregroundStyle(minutes == m ? Color.white : Color.primary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                VStack(spacing: 2) {
                    Slider(value: Binding(get: { Double(shownMinutes) }, set: { limitDrag = $0 }), in: 15...480, step: 15) { editing in
                        if !editing, let v = limitDrag {
                            store.setRule("screen_time", ["minutes": Int(v)])
                            Task {                            // hold the dragged value until the saved one arrives
                                try? await Task.sleep(nanoseconds: 1_500_000_000)
                                limitDrag = nil
                            }
                        }
                    }
                    HStack {
                        Text("15 min"); Spacer(); Text("4 h"); Spacer(); Text("8 h")
                    }
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                ForEach((store.status?.tvs ?? []).filter { $0.id == store.selectedTV }) { t in
                    let used = store.status?.usage[t.id] ?? 0
                    let limit = shownMinutes * 60
                    let left = max(0, limit - used)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(t.name): \(dur(used)) used today · \(used >= limit ? "limit reached" : dur(left) + " left")")
                            .font(.system(size: 11)).foregroundStyle(.secondary)
                        ProgressView(value: min(Double(used), Double(limit)), total: Double(max(limit, 1)))
                            .tint(used >= limit ? .red : .accentColor)
                    }
                }
            }
        }
    }

    private func timeBinding(_ key: String, _ value: String?, rule: String = "bedtime") -> Binding<Date> {
        let fmt = DateFormatter(); fmt.dateFormat = "HH:mm"
        return Binding(get: { fmt.date(from: value ?? "00:00") ?? Date() },
                       set: { store.setRule(rule, [key: fmt.string(from: $0)]) })
    }

    private var bedtimeCard: some View {
        let rule = rules?.bedtime
        return Card {
            VStack(alignment: .leading, spacing: 8) {
                ruleHeader("moon.zzz.fill", "Bedtime", "Keeps the TVs off between these times",
                           isOn: Binding(get: { rule?.enabled ?? false },
                                         set: { store.setRule("bedtime", ["enabled": $0]) }))
                HStack(spacing: 8) {
                    Text("From").font(.system(size: 12)).foregroundStyle(.secondary)
                    DatePicker("", selection: timeBinding("start", rule?.start), displayedComponents: .hourAndMinute)
                        .labelsHidden()
                    Text("to").font(.system(size: 12)).foregroundStyle(.secondary)
                    DatePicker("", selection: timeBinding("end", rule?.end), displayedComponents: .hourAndMinute)
                        .labelsHidden()
                }
            }
        }
    }

    private var allowChannelsCard: some View {
        channelListCard("checkmark.shield.fill", "Allowed YouTube channels", "Anything from other channels goes to Home",
                        ruleId: "allow_channels", rule: rules?.allowChannels, text: $newChannel,
                        emptyNote: "The rule stays paused until you add a channel. Names match part of the channel name.")
    }

    private var blockChannelsCard: some View {
        channelListCard("nosign", "Restricted YouTube channels", "Anything from these channels goes to Home",
                        ruleId: "block_channels", rule: rules?.blockChannels, text: $newBlocked,
                        emptyNote: "Add channels to block. Names match part of the channel name.")
    }

    private func channelListCard(_ symbol: String, _ title: String, _ subtitle: String, ruleId: String,
                                 rule: AllowRule?, text: Binding<String>, emptyNote: String) -> some View {
        let channels = rule?.channels ?? []
        return Card {
            VStack(alignment: .leading, spacing: 8) {
                ruleHeader(symbol, title, subtitle,
                           isOn: Binding(get: { rule?.enabled ?? false },
                                         set: { store.setRule(ruleId, ["enabled": $0]) }))
                ForEach(channels, id: \.self) { c in
                    HStack {
                        Text(c).font(.system(size: 12)).lineLimit(1)
                        Spacer()
                        Button {
                            store.setRule(ruleId, ["channels": channels.filter { $0 != c }])
                        } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary) }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Capsule().fill(Color.primary.opacity(0.07)))
                }
                HStack(spacing: 6) {
                    Image(systemName: "plus").foregroundStyle(.secondary)
                    TextField("Add a channel name, press Return", text: text)
                        .textFieldStyle(.plain).font(.system(size: 12))
                        .onSubmit {
                            let name = text.wrappedValue.trimmingCharacters(in: .whitespaces)
                            guard !name.isEmpty else { return }
                            store.setRule(ruleId, ["channels": channels + [name]])
                            text.wrappedValue = ""
                        }
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(Capsule().fill(Color.primary.opacity(0.08)))
                if channels.isEmpty {
                    Text(emptyNote).font(.system(size: 11)).foregroundStyle(.secondary)
                }
            }
        }
    }

    private var adultCard: some View {
        Card {
            ruleHeader("eye.slash.fill", "Adult content filter", "Sends Home when a title or channel looks adult, in any app",
                       isOn: Binding(get: { rules?.adultFilter.enabled ?? false },
                                     set: { store.setRule("adult_filter", ["enabled": $0]) }))
        }
    }

    private var volumeCapCard: some View {
        let rule = rules?.volumeCap
        return Card {
            VStack(alignment: .leading, spacing: 8) {
                ruleHeader("speaker.wave.2.fill", "Volume cap", "Lowers the volume if it goes above the limit",
                           isOn: Binding(get: { rule?.enabled ?? false },
                                         set: { store.setRule("volume_cap", ["enabled": $0]) }))
                Stepper(value: Binding(get: { rule?.max ?? 40 }, set: { store.setRule("volume_cap", ["max": $0]) }),
                        in: 5...100, step: 5) {
                    Text("Maximum volume: \(rule?.max ?? 40)  (now \(tv?.volume?.level ?? 0))").font(.system(size: 12))
                }
            }
        }
    }

    private var shortsCard: some View {
        Card {
            ruleHeader("iphone.slash", "Block YouTube Shorts",
                       tv?.adb == true ? "Watches the TV screen and sends Home when a Short appears"
                                       : "Needs network debugging on this TV to catch Shorts in its YouTube app",
                       isOn: Binding(get: { rules?.blockShorts.enabled ?? false },
                                     set: { store.setRule("block_shorts", ["enabled": $0]) }))
        }
    }

    // MARK: History

    private func dur(_ seconds: Int) -> String {
        if seconds < 60 { return "\(seconds)s" }
        let m = seconds / 60
        return m >= 60 ? "\(m / 60)h \(String(format: "%02d", m % 60))m" : "\(m)m"
    }

    private func clock(_ iso: String?) -> String { iso.map { String($0.dropFirst(11).prefix(5)) } ?? "" }

    private func dayLabel(_ ts: String) -> String {
        let fmt = DateFormatter(); fmt.dateFormat = "yyyy-MM-dd"
        let day = String(ts.prefix(10))
        if day == fmt.string(from: Date()) { return "Today" }
        if day == fmt.string(from: Date().addingTimeInterval(-86_400)) { return "Yesterday" }
        return day
    }

    private func symbol(forApp app: String) -> String {
        let a = app.lowercased()
        if a.contains("youtube") { return "play.rectangle.fill" }
        if a.contains("hotstar") { return "star.fill" }
        if a.contains("netflix") { return "n.square.fill" }
        if a.contains("prime") { return "play.fill" }
        if a.contains("sony") { return "tv.fill" }
        if a.contains("zee") { return "5.square.fill" }
        return "play.tv"
    }

    private var sessionsView: some View {
        let entries = (store.status?.history ?? []).filter { $0.tvId == store.selectedTV || ($0.tvId == nil && $0.tv == tv?.name) }
        let summary = store.status?.today[store.selectedTV]
        let days: [(String, [HistoryEntry])] = entries.reduce(into: []) { acc, e in
            let d = dayLabel(e.ts)
            if let i = acc.firstIndex(where: { $0.0 == d }) { acc[i].1.append(e) } else { acc.append((d, [e])) }
        }
        let playTime = (summary?.apps ?? [:]).values.reduce(0, +)
        let sessionTime = store.status?.usage[store.selectedTV] ?? 0
        return VStack(spacing: 10) {
            HStack(spacing: 10) {
                statCard("Play time today", dur(playTime), "play.circle.fill", .green)
                statCard("Session time today", dur(sessionTime), "tv.fill", .accentColor)
            }
            Card {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Today on \(tv?.name ?? "this TV")").font(.system(size: 13, weight: .semibold))
                            Text("\(summary?.plays ?? 0) played · play time counts only while a video is playing")
                                .font(.system(size: 11)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Toggle("", isOn: Binding(get: { rules?.history.enabled ?? false },
                                                 set: { store.setRule("history", ["enabled": $0]) }))
                            .toggleStyle(.switch).labelsHidden().help("Record watch history for this TV")
                    }
                    let apps = (summary?.apps ?? [:]).sorted { $0.value > $1.value }.prefix(4)
                    let top = Double(apps.first?.value ?? 1)
                    ForEach(Array(apps), id: \.key) { app, secs in
                        HStack(spacing: 8) {
                            Image(systemName: symbol(forApp: app)).font(.system(size: 11)).frame(width: 14)
                            Text(app).font(.system(size: 11)).frame(width: 70, alignment: .leading).lineLimit(1)
                            ProgressView(value: Double(secs), total: max(top, 1))
                            Text(dur(secs)).font(.system(size: 11)).foregroundStyle(.secondary)
                                .frame(width: 50, alignment: .trailing)
                        }
                    }
                    let chans = (summary?.channels ?? [:]).sorted { $0.value > $1.value }.prefix(3)
                    if !chans.isEmpty {
                        Text("Most watched: " + chans.map { "\($0.key) (\(dur($0.value)))" }.joined(separator: ", "))
                            .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(2)
                    }
                    if parent?.active == true {
                        Text("Parent mode is on: nothing is being recorded.").font(.system(size: 11)).foregroundStyle(.purple)
                    } else if rules?.history.enabled != true {
                        Text("Recording is off for this TV.").font(.system(size: 11)).foregroundStyle(.orange)
                    }
                }
            }
            if days.isEmpty {
                Text("Nothing recorded yet. Sessions appear here once something plays.")
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 120)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(days, id: \.0) { day, list in
                            Text(day).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                                .padding(.top, 4)
                            ForEach(list) { historyRow($0) }
                        }
                        Button("Clear history for this TV") { store.clearHistory() }
                            .buttonStyle(.plain).font(.system(size: 11)).foregroundStyle(.red).padding(.top, 6)
                    }
                }
                .frame(height: 290)
            }
        }
    }

    private var historyView: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Picker("", selection: $store.historyMode) {
                    Text("Sessions").tag(0)
                    Text("Weekly report").tag(1)
                }
                .pickerStyle(.segmented).labelsHidden()
                Menu {
                    Button("Export \(tv?.name ?? "this TV") as a spreadsheet (CSV)") { store.exportHistory(allTVs: false) }
                    Button("Export all TVs") { store.exportHistory(allTVs: true) }
                } label: {
                    Image(systemName: "square.and.arrow.up")
                }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                .help("Save history as a spreadsheet")
            }
            if store.historyMode == 0 { sessionsView } else { reportView }
        }
        .onChange(of: store.historyMode) { mode in
            if mode == 1 { Task { await store.loadReport() } }
        }
    }

    private struct ChartPoint: Identifiable {
        let id = UUID()
        let day: String
        let app: String
        let minutes: Double
    }

    private func chartPoints(_ report: Report) -> [ChartPoint] {
        var points: [ChartPoint] = []
        for d in report.days {
            if d.apps.isEmpty { points.append(ChartPoint(day: d.label, app: "None", minutes: 0)) }
            for (app, secs) in d.apps.sorted(by: { $0.key < $1.key }) {
                points.append(ChartPoint(day: d.label, app: app, minutes: Double(secs) / 60))
            }
        }
        return points
    }

    private func rankList(_ title: String, _ items: [Ranked]) -> some View {
        let top = Double(items.first?.secs ?? 1)
        return VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.system(size: 12, weight: .semibold))
            if items.isEmpty {
                Text("Nothing yet").font(.system(size: 11)).foregroundStyle(.secondary)
            }
            ForEach(items) { item in
                HStack(spacing: 8) {
                    Text(item.name).font(.system(size: 11)).frame(width: 96, alignment: .leading).lineLimit(1)
                    ProgressView(value: Double(item.secs), total: max(top, 1))
                    Text(dur(item.secs)).font(.system(size: 11)).foregroundStyle(.secondary)
                        .frame(width: 52, alignment: .trailing)
                }
            }
        }
    }

    private var reportView: some View {
        ScrollView {
            if let report = store.report {
                VStack(spacing: 10) {
                    HStack(spacing: 10) {
                        statCard("Play time, 7 days", dur(report.totalPlay), "play.circle.fill", .green)
                        statCard("Daily average", dur(report.totalPlay / 7), "chart.bar.fill", .accentColor)
                    }
                    Card {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Play time per day (minutes)").font(.system(size: 12, weight: .semibold))
                            Chart(chartPoints(report)) { p in
                                BarMark(x: .value("Day", p.day), y: .value("Minutes", p.minutes))
                                    .foregroundStyle(by: .value("App", p.app))
                            }
                            .frame(height: 150)
                            ForEach(report.days.reversed()) { d in
                                HStack {
                                    Text(d.label).font(.system(size: 11, weight: .medium)).frame(width: 34, alignment: .leading)
                                    Text("play \(dur(d.play))").font(.system(size: 11))
                                    Spacer()
                                    Text("TV on \(dur(d.session))").font(.system(size: 11)).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    Card { rankList("Top apps", report.topApps) }
                    Card { rankList("Top channels", report.topChannels) }
                }
            } else {
                ProgressView().frame(maxWidth: .infinity, minHeight: 120)
            }
        }
        .frame(height: 420)
    }

    private func statCard(_ title: String, _ value: String, _ symbol: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol).font(.system(size: 16)).foregroundStyle(color)
            Text(value)
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .minimumScaleFactor(0.6).lineLimit(1)
            Text(title).font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(color.opacity(0.12)))
    }

    private func watchedLine(_ e: HistoryEntry) -> String {
        var parts: [String] = []
        var watched = "Watched " + dur(e.watched ?? 0)
        if let length = e.length { watched += " of " + dur(length) }
        parts.append(watched)
        if let language = e.language { parts.append(language.uppercased()) }
        if let channel = e.channel { parts.append(channel) }
        return parts.joined(separator: " · ")
    }

    private func historyRow(_ e: HistoryEntry) -> some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Color.primary.opacity(0.08))
                if let t = e.thumb, let url = URL(string: t) {
                    AsyncImage(url: url) { phase in
                        if case .success(let image) = phase { image.resizable().aspectRatio(contentMode: .fill) }
                    }
                } else {
                    Image(systemName: symbol(forApp: e.app)).foregroundStyle(.secondary)
                }
            }
            .frame(width: 72, height: 41).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(e.title ?? e.app).font(.system(size: 12, weight: .medium)).lineLimit(2)
                Text("\(e.app) · \(clock(e.ts))–\(e.live == true ? "now" : clock(e.end))")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                HStack(spacing: 4) {
                    if e.live == true {
                        Circle().fill(.red).frame(width: 5, height: 5)
                        Text("LIVE").font(.system(size: 9, weight: .bold)).foregroundStyle(.red)
                    }
                    Text(watchedLine(e))
                        .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if let url = e.webURL {
                Button { NSWorkspace.shared.open(url) } label: {
                    Image(systemName: e.opensExactVideo ? "safari" : "magnifyingglass")
                }
                .buttonStyle(.plain).foregroundStyle(Color.accentColor)
                .help(e.opensExactVideo ? "Open this video in your browser" : "Search for this title in your browser")
            }
        }
    }

    // MARK: Footer

    private var footer: some View {
        HStack {
            Text(store.toast ?? (store.status == nil ? "Helper offline" : "Connected"))
                .font(.system(size: 10)).foregroundStyle(store.toast == nil ? .secondary : Color.accentColor)
            Spacer()
            Menu {
                Toggle("Alerts when a rule acts", isOn: Binding(get: { store.alertsOn }, set: { store.setAlerts($0) }))
                Toggle("Start at login", isOn: Binding(get: { store.loginEnabled }, set: { store.setLogin($0) }))
                Button("Send a test alert") { store.sendTestAlert() }
                Button("Add a TV… (opens in browser)") { NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8765/")!) }
            } label: {
                Image(systemName: "gearshape")
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            Button("Quit") { store.stopHelper(); NSApplication.shared.terminate(nil) }
                .buttonStyle(.plain).font(.system(size: 11)).foregroundStyle(.secondary)
        }
    }
}
