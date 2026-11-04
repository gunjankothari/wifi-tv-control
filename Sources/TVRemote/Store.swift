import Foundation
import SwiftUI
import UserNotifications
import ServiceManagement
import AppKit
import UniformTypeIdentifiers

@MainActor
final class Store: ObservableObject {
    @Published var status: Status?
    @Published var error: String?
    @Published var selectedTV = "sony"
    @Published var tab = 0
    @Published var statusAt = Date()
    @Published var loginEnabled = false
    @Published var historyMode = 0
    @Published var report: Report?
    @Published var alertsOn = UserDefaults.standard.object(forKey: "alertsOn") as? Bool ?? true
    private var lastBlockedN: Int?
    @Published var previewMuted = true
    @Published var toast: String?
    @Published var query = ""
    @Published var results: [SearchResult] = []
    @Published var searching = false
    @Published var searchError: String?

    private let base = URL(string: "http://127.0.0.1:8765")!
    private var helper: Process?
    private var timer: Timer?

    init() {
        refreshLogin()
        Task { await startHelperIfNeeded() }
        if alertsOn { requestNotificationPermission() }
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            guard let store = self else { return }
            Task { @MainActor in await store.refresh() }
        }
    }

    private var projectDir: URL {
        if let p = ProcessInfo.processInfo.environment["TVREMOTE_HOME"] { return URL(fileURLWithPath: p) }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/code/TVRemote")
    }

    private func startHelperIfNeeded() async {
        await refresh()
        guard status == nil else { return }
        let p = Process()
        let log: URL
        if let bundled = Bundle.main.resourceURL?.appendingPathComponent("tvd/tvd"),
           FileManager.default.isExecutableFile(atPath: bundled.path) {
            // Installed app: the helper is bundled inside it and keeps its data in Application Support.
            p.executableURL = bundled
            let data = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/TVRemote")
            try? FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            log = data.appendingPathComponent("helper.log")
        } else {
            let dir = projectDir.appendingPathComponent("helper")
            p.executableURL = dir.appendingPathComponent(".venv/bin/python")
            p.arguments = ["-W", "ignore", dir.appendingPathComponent("tvd.py").path]
            p.currentDirectoryURL = dir
            log = dir.appendingPathComponent("data/helper.log")
        }
        FileManager.default.createFile(atPath: log.path, contents: nil)
        if let h = try? FileHandle(forWritingTo: log) { p.standardOutput = h; p.standardError = h }
        do { try p.run(); helper = p } catch { self.error = "Could not start helper: \(error.localizedDescription)" }
    }

    func stopHelper() { helper?.terminate() }

    /// True when at least one TV is connected and switched on (drives the green menu bar icon).
    var anyTVOn: Bool { status?.tvs.contains { $0.online && $0.on == true } ?? false }

    // MARK: Report and export

    func loadReport() async {
        var comps = URLComponents(url: base.appendingPathComponent("report"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "tv", value: selectedTV)]
        if let (data, _) = try? await URLSession.shared.data(from: comps.url!),
           let r = try? JSONDecoder().decode(Report.self, from: data) { report = r }
    }

    func exportHistory(allTVs: Bool) {
        var comps = URLComponents(url: base.appendingPathComponent("export"), resolvingAgainstBaseURL: false)!
        if !allTVs { comps.queryItems = [URLQueryItem(name: "tv", value: selectedTV)] }
        let name = allTVs ? "all-TVs" : (status?.tvs.first { $0.id == selectedTV }?.name ?? selectedTV)
        Task {
            guard let (data, _) = try? await URLSession.shared.data(from: comps.url!) else {
                showToast("Export failed"); return
            }
            let fmt = DateFormatter(); fmt.dateFormat = "yyyy-MM-dd"
            let panel = NSSavePanel()
            panel.allowedContentTypes = [.commaSeparatedText]
            panel.nameFieldStringValue = "TV history \(name) \(fmt.string(from: Date())).csv"
            NSApp.activate(ignoringOtherApps: true)
            guard panel.runModal() == .OK, let url = panel.url else { return }
            do { try data.write(to: url); showToast("Saved \(url.lastPathComponent)") }
            catch { showToast("Couldn't save the file") }
        }
    }

    // MARK: Start at login

    func refreshLogin() { loginEnabled = SMAppService.mainApp.status == .enabled }

    func setLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            showToast("Couldn't change start at login")
        }
        refreshLogin()
        if on && SMAppService.mainApp.status == .requiresApproval {
            showToast("Approve TVRemote in System Settings > General > Login Items")
        }
    }

    // MARK: Alerts

    func setAlerts(_ on: Bool) {
        alertsOn = on
        UserDefaults.standard.set(on, forKey: "alertsOn")
        if on { requestNotificationPermission() }
    }

    func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    private func alertText(_ b: Blocked) -> (String, String) {
        switch b.word {
        case "bedtime": return ("\(b.tv): bedtime", "The TV was switched off.")
        case "daily limit": return ("\(b.tv): daily limit reached", "The TV was switched off. \(b.title)")
        default: return ("\(b.tv): blocked (\(b.word))", b.title)
        }
    }

    func notify(title: String, body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }

    func sendTestAlert() {
        requestNotificationPermission()
        notify(title: "TV Remote", body: "Alerts are working. You will see a message like this when a rule blocks something.")
    }

    private func processAlerts(_ s: Status) {
        let entries = s.filter.blocked.filter { $0.n != nil }
        let top = entries.compactMap(\.n).max() ?? 0
        guard let last = lastBlockedN else { lastBlockedN = top; return }   // first load: nothing is new
        if top < last { lastBlockedN = 0 }                                // helper restarted, numbering began again
        let fresh = entries.filter { ($0.n ?? 0) > (lastBlockedN ?? 0) }.sorted { ($0.n ?? 0) < ($1.n ?? 0) }
        lastBlockedN = max(top, lastBlockedN ?? 0)
        guard alertsOn else { return }
        for b in fresh {
            let (t, body) = alertText(b)
            notify(title: t, body: body)
        }
    }

    func refresh() async {
        do {
            let (data, _) = try await URLSession.shared.data(from: base.appendingPathComponent("status"))
            status = try JSONDecoder().decode(Status.self, from: data)
            statusAt = Date()
            if let s = status { processAlerts(s) }
            if tab == 3 && historyMode == 1 { await loadReport() }
            error = nil
        } catch {
            status = nil
            self.error = "Helper not running"
        }
    }

    private func post(_ path: String, _ body: [String: Any]) {
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        let tvName = status?.tvs.first { $0.id == selectedTV }?.name ?? "TV"
        let wantsOn = body["on"] as? Bool ?? false
        Task {
            let result = try? await URLSession.shared.data(for: req)
            let code = (result?.1 as? HTTPURLResponse)?.statusCode ?? 0
            switch path {
            case "play":
                showToast(code == 200 ? "Sent to \(tvName)" : "Couldn't play on \(tvName) (is it on?)")
            case "media":
                if code == 200 { showToast("Playing on \(tvName)") }
                else {
                    var detail = ""
                    if let data = result?.0, let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let msg = obj["error"] as? String { detail = ": " + String(msg.prefix(80)) }
                    showToast("Couldn't play" + detail)
                }
            case "volume":
                if code != 200 { showToast("Couldn't set the volume on \(tvName)") }
            case "wake":
                showToast(code == 200 ? "Wake signal sent to \(tvName), it can take up to 30 seconds" : "Couldn't wake \(tvName) (never seen on the network?)")
            case "type":
                showToast(code == 200 ? "Typing on \(tvName)…" : "Couldn't type on \(tvName)")
            case "appsearch":
                showToast(code == 200 ? "Searching on \(tvName)…" : "Couldn't search on \(tvName)")
            case "camera":
                if code != 200 {
                    var detail = ""
                    if let data = result?.0,
                       let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let msg = obj["error"] as? String { detail = ": " + String(msg.prefix(80)) }
                    showToast("Camera failed" + detail)
                } else if wantsOn {
                    showToast("Camera live on \(tvName)")
                }
            default: break
            }
            await refresh()
        }
    }

    func setCamera(_ on: Bool) {
        if on { showToast("Starting camera…") }
        post("camera", ["tv": selectedTV, "on": on])
    }

    private func showToast(_ text: String) {
        toast = text
        Task {
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            if toast == text { toast = nil }
        }
    }

    func search() {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { results = []; searchError = nil; return }
        searching = true
        searchError = nil
        var comps = URLComponents(url: base.appendingPathComponent("search"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "q", value: q)]
        Task {
            defer { searching = false }
            do {
                let (data, _) = try await URLSession.shared.data(from: comps.url!)
                results = try JSONDecoder().decode([SearchResult].self, from: data)
                if results.isEmpty { searchError = "No results" }
            } catch {
                results = []
                searchError = "Search failed"
            }
        }
    }

    func chooseMedia() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.movie, .image]
        panel.allowsMultipleSelection = true
        panel.message = "Choose one video, or several photos for a slideshow"
        NSApp.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, !panel.urls.isEmpty else { return }
        showToast("Starting… long videos in other formats take a few seconds")
        post("media", ["tv": selectedTV, "paths": panel.urls.map(\.path)])
    }

    func stopMedia() { post("media/stop", [:]) }

    func playback(_ action: String, position: Double? = nil, delta: Double? = nil) {
        var body: [String: Any] = ["tv": selectedTV, "action": action]
        if let position { body["position"] = position }
        if let delta { body["delta"] = delta }
        if let delta { showToast(delta > 0 ? "Skipped forward \(Int(delta)) s" : "Went back \(Int(-delta)) s") }
        post("playback", body)
    }

    func startParentMode(minutes: Int?) {
        var body: [String: Any] = ["tv": selectedTV, "on": true]
        if let minutes { body["minutes"] = minutes }
        let name = status?.tvs.first { $0.id == selectedTV }?.name ?? "the TV"
        showToast("Parent mode on for \(name)")
        post("parent", body)
    }

    func endParentMode() { post("parent", ["tv": selectedTV, "on": false]) }

    func setVolume(_ level: Int) { post("volume", ["tv": selectedTV, "level": level]) }

    func wake() { post("wake", ["tv": selectedTV]) }

    func typeOnTV(openSearch: Bool) {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return }
        post("type", ["tv": selectedTV, "text": q, "open_search": openSearch, "submit": true])
    }

    func searchInApp() {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return }
        post("appsearch", ["tv": selectedTV, "q": q])
    }

    func play(_ id: String) { post("play", ["tv": selectedTV, "id": id]) }

    func key(_ key: String) { post("key", ["tv": selectedTV, "key": key]) }
    func launch(_ app: String) { post("launch", ["tv": selectedTV, "app": app]) }
    func setRule(_ id: String, _ config: [String: Any]) { post("rules", ["tv": selectedTV, "id": id, "config": config]) }
    func clearHistory() { post("history/clear", ["tv": selectedTV]) }
}
