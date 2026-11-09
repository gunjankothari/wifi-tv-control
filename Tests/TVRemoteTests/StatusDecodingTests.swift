import XCTest
@testable import TVRemote

/// Feeds a saved helper `/status` reply (Fixtures/status.json) through the app's decoders.
/// If a JSON key is renamed in the helper, these tests fail instead of the app silently showing nothing.
final class StatusDecodingTests: XCTestCase {
    private func fixture() throws -> Data {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "status", withExtension: "json", subdirectory: "Fixtures"))
        return try Data(contentsOf: url)
    }

    private func status() throws -> Status { try JSONDecoder().decode(Status.self, from: fixture()) }

    func testTVsDecodeWithSnakeCaseKeys() throws {
        let tvs = try status().tvs
        XCTAssertEqual(tvs.map(\.id), ["sony", "oneplus"])
        let sony = tvs[0]
        XCTAssertEqual(sony.appKey, "youtube")
        XCTAssertEqual(sony.playerState, "PLAYING")
        XCTAssertEqual(sony.canSeek, true)
        XCTAssertEqual(sony.adb, true)
        XCTAssertEqual(sony.volume?.level, 23)
        XCTAssertEqual(sony.position, 42.5)
        XCTAssertEqual(sony.searchApp, "YouTube")
        XCTAssertEqual(sony.sinceLabel, "since 19:20")
        XCTAssertEqual(sony.summary, "On · YouTube · Vol 23")

        let oneplus = tvs[1]
        XCTAssertFalse(oneplus.online)
        XCTAssertNil(oneplus.on)
        XCTAssertNil(oneplus.volume)
        XCTAssertNil(oneplus.searchApp)
        XCTAssertEqual(oneplus.summary, "Powered off or off Wi-Fi · since 08:05")
    }

    func testRulesUsageAndParentState() throws {
        let s = try status()
        let sony = try XCTUnwrap(s.rules["sony"])
        XCTAssertEqual(sony.screenTime.minutes, 45)
        XCTAssertEqual(sony.bedtime.start, "21:00")
        XCTAssertEqual(sony.allowChannels.channels, ["Peppa Pig", "Bluey"])
        XCTAssertEqual(sony.volumeCap.max, 40)
        XCTAssertTrue(sony.blockShorts.enabled)
        XCTAssertEqual(sony.parentSchedule.end, "19:00")
        XCTAssertEqual(s.rules["oneplus"]?.screenTime.enabled, false)

        XCTAssertEqual(s.usage["sony"], 1830)
        XCTAssertEqual(s.today["sony"]?.apps["YouTube"], 1500)
        XCTAssertEqual(s.today["sony"]?.plays, 2)
        XCTAssertEqual(s.parent["sony"]?.secondsLeft, 1200)
        XCTAssertEqual(s.parent["oneplus"]?.active, false)
        XCTAssertNil(s.parent["oneplus"]?.secondsLeft)
    }

    func testHistoryBlockedMediaAndCamera() throws {
        let s = try status()
        XCTAssertEqual(s.history.count, 3)
        let live = s.history[0]
        XCTAssertEqual(live.tvId, "sony")
        XCTAssertEqual(live.live, true)
        XCTAssertTrue(live.opensExactVideo)
        XCTAssertEqual(live.webURL?.absoluteString, "https://www.youtube.com/watch?v=AAAAAAAAAAA")

        let blocked = s.history[1]
        XCTAssertEqual(blocked.blocked, true)
        XCTAssertEqual(blocked.canAllow, true)
        XCTAssertEqual(blocked.allowed, false)
        XCTAssertEqual(blocked.reason, "channel is not on the allowed list")
        XCTAssertFalse(blocked.opensExactVideo)
        XCTAssertEqual(blocked.webURL?.host, "www.google.com")

        XCTAssertNil(s.history[2].title)
        XCTAssertNil(s.history[2].webURL)

        XCTAssertTrue(s.filter.enabled)
        XCTAssertEqual(s.filter.blocked.first?.word, "channel not allowed")
        XCTAssertEqual(s.media.name, "2 photos")
        XCTAssertEqual(s.media.count, 2)
        XCTAssertFalse(s.camera.on)
        XCTAssertNil(s.camera.tv)
    }

    func testRenamedTopLevelKeyIsRejected() throws {
        // A helper that stops sending "tvs" (or renames it) must not decode into an empty status.
        let text = try XCTUnwrap(String(data: fixture(), encoding: .utf8))
        let renamed = Data(text.replacingOccurrences(of: "\"tvs\":", with: "\"televisions\":").utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(Status.self, from: renamed))
    }

    func testReportDecodes() throws {
        let json = """
        {"days": [{"date": "2026-11-06", "label": "Fri", "play": 1500, "session": 1830,
                   "apps": {"YouTube": 1500}, "channels": {"Bluey": 1500}, "app_usage": {}}],
         "top_apps": [{"name": "YouTube", "secs": 1500}], "top_channels": [{"name": "Bluey", "secs": 1500}],
         "total_play": 1500, "total_session": 1830}
        """
        let report = try JSONDecoder().decode(Report.self, from: Data(json.utf8))
        XCTAssertEqual(report.days.first?.id, "2026-11-06")
        XCTAssertEqual(report.topApps.first?.name, "YouTube")
        XCTAssertEqual(report.totalSession, 1830)
    }
}
