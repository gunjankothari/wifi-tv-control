import Foundation

struct Volume: Decodable {
    let level: Int
    let max: Int
    let muted: Bool
}

struct TV: Decodable, Identifiable {
    let id: String
    let name: String
    let ip: String
    let online: Bool
    let on: Bool?
    let app: String?
    let volume: Volume?
    let title: String?
    let channel: String?
    let thumb: String?
    let appKey: String?
    let duration: Double?
    let position: Double?
    let playing: Bool?
    let power: String?
    let since: String?
    let playerState: String?
    let canSeek: Bool?
    let adb: Bool?

    enum CodingKeys: String, CodingKey {
        case id, name, ip, online, on, app, volume, title, channel, thumb, duration, position, playing, power, since
        case playerState = "player_state", canSeek = "can_seek", adb
        case appKey = "app_key"
    }

    /// The open app is one the app can search in (YouTube in-app, others via the TV app's own search).
    var searchApp: String? {
        guard online, on != false else { return nil }
        switch appKey {
        case "youtube": return "YouTube"
        case "primevideo": return "Prime Video"
        case "netflix": return "Netflix"
        case "hotstar": return "Hotstar"
        case "sonyliv": return "SonyLIV"
        case "zee5": return "ZEE5"
        default: return nil
        }
    }

    /// What kind of "off" the TV is in, or "On".
    var powerLabel: String {
        switch power {
        case "on": return "On"
        case "standby": return "Standby (screen off)"
        case "deep_sleep": return "Deep sleep (on Wi-Fi, not answering)"
        case "off": return "Powered off or off Wi-Fi"
        default: return online ? "On" : "Not connected"
        }
    }

    /// "since 19:20" for the current power state.
    var sinceLabel: String? { since.map { "since " + String($0.dropFirst(11).prefix(5)) } }

    var summary: String {
        if !online { return powerLabel + (sinceLabel.map { " · " + $0 } ?? "") }
        if on == false { return powerLabel + (sinceLabel.map { " · " + $0 } ?? "") }
        var parts = ["On"]
        if let app { parts.append(app) }
        if let volume { parts.append(volume.muted ? "Muted" : "Vol \(volume.level)") }
        return parts.joined(separator: " · ")
    }
}

/// An app on the TV's home screen, from the TV's own list.
/// Phone remote over Wi-Fi (GET/POST /phone, only reachable from this Mac).
struct PhoneAccess: Decodable {
    let enabled: Bool
    let running: Bool
    let url: String?
    let pin: String
    let phones: Int
    let ip: String?
    let error: String?
}

struct InstalledApp: Decodable, Identifiable {
    let package: String
    let name: String
    let icon: String?
    var id: String { package }
}

struct SearchResult: Decodable, Identifiable {
    let id: String
    let title: String
    let channel: String
    let duration: String?
    let thumb: String
}

struct Blocked: Decodable, Identifiable {
    let n: Int?
    let time: String
    let tv: String
    let word: String
    let title: String
    var id: String { "\(n ?? 0)" + time + tv + title }
}

struct FilterState: Decodable {
    let enabled: Bool
    let blocked: [Blocked]
}

struct CameraState: Decodable {
    let on: Bool
    let tv: String?
}

struct ToggleRule: Decodable { let enabled: Bool }
struct ScreenTimeRule: Decodable {
    let enabled: Bool
    let minutes: Int
    let weekendMinutes: Int?                 // nil: weekends use the weekday limit
    let warnMinutes: Int?
    enum CodingKeys: String, CodingKey { case enabled, minutes, weekendMinutes = "weekend_minutes", warnMinutes = "warn_minutes" }
}
struct BedtimeRule: Decodable { let enabled: Bool; let start: String; let end: String }
struct AllowRule: Decodable { let enabled: Bool; let channels: [String] }

struct VolumeCapRule: Decodable { let enabled: Bool; let max: Int }
struct AppLimitsRule: Decodable { let enabled: Bool; let limits: [String: Int] }
struct BlockAppsRule: Decodable { let enabled: Bool; let packages: [String] }

struct RuleSet: Decodable {
    let titleFilter: ToggleRule
    let screenTime: ScreenTimeRule
    let bedtime: BedtimeRule
    let allowChannels: AllowRule
    let blockShorts: ToggleRule
    let adultFilter: ToggleRule
    let volumeCap: VolumeCapRule
    let blockChannels: AllowRule
    let history: ToggleRule
    let parentSchedule: BedtimeRule
    let appLimits: AppLimitsRule?
    let blockApps: BlockAppsRule?

    enum CodingKeys: String, CodingKey {
        case titleFilter = "title_filter", screenTime = "screen_time", bedtime
        case allowChannels = "allow_channels", blockShorts = "block_shorts", adultFilter = "adult_filter", volumeCap = "volume_cap", blockChannels = "block_channels", history, parentSchedule = "parent_schedule"
        case appLimits = "app_limits", blockApps = "block_apps"
    }
}

struct HistoryEntry: Decodable, Identifiable {
    let ts: String
    let end: String?
    let tvId: String?
    let tv: String
    let app: String
    let title: String?
    let channel: String?
    let watched: Int?
    let length: Int?
    let language: String?
    let thumb: String?
    let live: Bool?
    let blocked: Bool?
    let reason: String?
    let canAllow: Bool?
    let allowed: Bool?
    var id: String { ts + tv + (title ?? app) + (reason ?? "") }

    /// The video itself for YouTube (its id is in the thumbnail address), otherwise a web search for the title.
    var webURL: URL? {
        if let t = thumb, let r = t.range(of: "/vi/"), t.contains("ytimg.com") {
            let id = t[r.upperBound...].prefix { $0 != "/" }
            if !id.isEmpty { return URL(string: "https://www.youtube.com/watch?v=\(id)") }
        }
        guard let title, !title.isEmpty else { return nil }
        var comps = URLComponents(string: "https://www.google.com/search")!
        comps.queryItems = [URLQueryItem(name: "q", value: "\(title) \(app)")]
        return comps.url
    }
    var opensExactVideo: Bool { thumb?.contains("ytimg.com/vi/") == true }

    enum CodingKeys: String, CodingKey {
        case ts, end, tv, app, title, channel, watched, length, language, thumb, live, blocked, reason, allowed
        case tvId = "tv_id", canAllow = "can_allow"
    }
}

struct DaySummary: Decodable {
    let apps: [String: Int]
    let channels: [String: Int]
    let plays: Int
}

struct ReportDay: Decodable, Identifiable {
    let date: String
    let label: String
    let play: Int
    let session: Int
    let apps: [String: Int]
    let channels: [String: Int]
    var id: String { date }
}

struct Ranked: Decodable, Identifiable {
    let name: String
    let secs: Int
    var id: String { name }
}

struct Report: Decodable {
    let days: [ReportDay]
    let topApps: [Ranked]
    let topChannels: [Ranked]
    let totalPlay: Int
    let totalSession: Int

    enum CodingKeys: String, CodingKey {
        case days
        case topApps = "top_apps", topChannels = "top_channels", totalPlay = "total_play", totalSession = "total_session"
    }
}

struct MediaState: Decodable {
    let on: Bool
    let tv: String?
    let kind: String?
    let name: String?
    let count: Int
}

struct ParentState: Decodable {
    let active: Bool
    let scheduled: Bool?
    let secondsLeft: Int?

    enum CodingKeys: String, CodingKey {
        case active, scheduled
        case secondsLeft = "seconds_left"
    }
}

struct Status: Decodable {
    let tvs: [TV]
    let filter: FilterState
    let camera: CameraState
    let media: MediaState
    let rules: [String: RuleSet]
    let usage: [String: Int]
    let appUsage: [String: [String: Int]]?
    let limit: [String: Int]?                // today's limit in minutes per TV, bonus included
    let bonus: [String: Int]?                // extra minutes granted for today per TV
    let history: [HistoryEntry]
    let today: [String: DaySummary]
    let parent: [String: ParentState]

    enum CodingKeys: String, CodingKey {
        case tvs, filter, camera, media, rules, usage, appUsage = "app_usage", limit, bonus, history, today, parent
    }
}
