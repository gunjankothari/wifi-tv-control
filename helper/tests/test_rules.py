import datetime, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rules import Rules
import tvd

TVS = ["sony", "oneplus"]
def at(h, m=0): return datetime.datetime(2026, 11, 3, h, m)
class Remote:
    def __init__(self): self.keys = []
    def send_key_command(self, k): self.keys.append(k)

def make(tv_state, tv_id="sony"):
    r = Rules(tempfile.mkdtemp(), TVS)
    tv = tvd.TV({"id": tv_id, "name": tv_id.title(), "ip": "x"})
    tv.remote = Remote(); tv.state.update({"on": True, "app": "YouTube", **tv_state})
    return r, tv

# bedtime, including a window that crosses midnight
r = Rules(tempfile.mkdtemp(), TVS); r.update("sony", "bedtime", {"enabled": True, "start": "21:00", "end": "07:00"})
assert r.in_bedtime("sony", at(21)) and r.in_bedtime("sony", at(23, 59)) and r.in_bedtime("sony", at(3))
assert not r.in_bedtime("sony", at(7)) and not r.in_bedtime("sony", at(12)) and not r.in_bedtime("sony", at(20, 59))
r.update("sony", "bedtime", {"start": "13:00", "end": "14:30"})
assert r.in_bedtime("sony", at(13, 30)) and not r.in_bedtime("sony", at(14, 30))

# rules are separate for each TV
assert r.cfg["oneplus"]["bedtime"] == {"enabled": False, "start": "21:00", "end": "07:00"}
r.update("sony", "screen_time", {"enabled": True, "minutes": 30})
r.add_usage("sony", 30 * 60, at(10)); r.add_usage("oneplus", 30 * 60, at(10))
assert r.over_limit("sony", at(10)) and not r.over_limit("oneplus", at(10))   # oneplus rule is off
r.update("oneplus", "screen_time", {"enabled": True, "minutes": 60})
assert not r.over_limit("oneplus", at(10))                                    # its own, longer limit
assert not r.over_limit("sony", at(10) + datetime.timedelta(days=1))

# validation
for tv, rule, bad in (("sony", "bedtime", {"start": "25:00"}), ("sony", "bedtime", {"start": "9pm"}),
                      ("tv9", "bedtime", {}), ("sony", "nope", {})):
    try: r.update(tv, rule, bad); raise SystemExit("accepted bad input")
    except ValueError: pass
r.update("sony", "screen_time", {"minutes": 5}); assert r.cfg["sony"]["screen_time"]["minutes"] == 15
r.update("sony", "allow_channels", {"enabled": True, "channels": [" Peppa Pig ", "peppa pig", "", "Bluey"]})
assert r.cfg["sony"]["allow_channels"]["channels"] == ["Peppa Pig", "Bluey"]
assert r.channel_allowed("sony", "Peppa Pig - Official Channel") and not r.channel_allowed("sony", "DiLSe Gamer")
assert r.channel_allowed("oneplus", "DiLSe Gamer")                            # other TV unaffected
r.update("sony", "allow_channels", {"channels": []}); assert r.channel_allowed("sony", "anyone")

# persistence, and migration of the earlier single rule set
r2 = Rules(r.dir, TVS); assert r2.cfg == r.cfg
d = tempfile.mkdtemp()
json.dump({"title_filter": {"enabled": False}, "bedtime": {"enabled": True, "start": "22:00", "end": "06:00"}},
          open(os.path.join(d, "rules.json"), "w"))
old = Rules(d, TVS)
assert all(not old.cfg[t]["title_filter"]["enabled"] and old.cfg[t]["bedtime"]["start"] == "22:00" for t in TVS)

# engine
r, tv = make({"title": "Cute puppies", "channel": "DiLSe Gamer"}); blocked = []
r.update("sony", "title_filter", {"enabled": False}); r.update("sony", "allow_channels", {"enabled": True, "channels": ["Bluey"]})
tv.apply_rules(r, blocked); assert tv.remote.keys == ["BACK"] and "channel not allowed" in blocked[0]["word"]
tv.apply_rules(r, blocked); assert tv.remote.keys == ["BACK"], "must not repeat for the same video"

# a rule set on the Sony does not act on the OnePlus
r, oneplus = make({"title": "Cute puppies", "channel": "DiLSe Gamer"}, "oneplus")
r.update("sony", "allow_channels", {"enabled": True, "channels": ["Bluey"]}); r.update("oneplus", "title_filter", {"enabled": False})
oneplus.apply_rules(r, []); assert oneplus.remote.keys == []

r, tv = make({"title": "Minecraft gameplay", "channel": "Kids"}); blocked = []
tv.apply_rules(r, blocked); assert tv.remote.keys == ["BACK"]
r.update("sony", "title_filter", {"enabled": False}); tv.blocked_title = None; tv.cooldown = 0; tv.remote.keys.clear()
tv.apply_rules(r, blocked); assert tv.remote.keys == []

r, tv = make({"title": "Cartoon", "channel": "Bluey"}); blocked = []
r.update("sony", "bedtime", {"enabled": True}); r.in_bedtime = lambda tv_id, now=None: tv_id == "sony"
tv.apply_rules(r, blocked); assert tv.remote.keys == ["POWER"]
tv.state["on"] = False; tv.cooldown = 0; tv.apply_rules(r, blocked); assert tv.remote.keys == ["POWER"]

r, tv = make({"title": "Cartoon", "channel": "Bluey"}); blocked = []
r.update("sony", "screen_time", {"enabled": True, "minutes": 15}); r.add_usage("sony", 15 * 60)
tv.apply_rules(r, blocked); assert tv.remote.keys == ["POWER"] and blocked[0]["word"] == "daily limit"

# watch sessions
r, tv = make({"title": "Cartoon", "channel": "Bluey", "playing": True, "duration": 600, "language": "eng",
              "thumb": "http://img/x.jpg", "app_key": "youtube"})
r.update("sony", "title_filter", {"enabled": False})
r.update("sony", "history", {"enabled": False}); tv.apply_rules(r, []); assert tv.session is None   # recording off
r.update("sony", "history", {"enabled": True})
for _ in range(10): tv.last_tick -= 3; tv.apply_rules(r, [])                                     # 10 ticks of ~3s
assert tv.session and 25 <= tv.session["watched"] <= 31 and tv.live_entry()["live"] is True
tv.state["playing"] = False; before = tv.session["watched"]; tv.last_tick -= 3; tv.apply_rules(r, [])
assert tv.session["watched"] == before                                                           # paused = not counted
tv.state.update(app="Home", app_key="home", title=None, channel=None); tv.apply_rules(r, [])      # left the video
assert tv.session is None and len(r.history) == 1
e = r.history[0]
assert e["title"] == "Cartoon" and e["tv_id"] == "sony" and e["length"] == 600 and e["language"] == "eng"
assert e["thumb"] and e["end"] and 25 <= e["watched"] <= 31 and "key" not in e
summary = r.today_summary([])["sony"]; assert summary["apps"]["YouTube"] == e["watched"] and summary["channels"]["Bluey"]
# short blips are not recorded; apps without playback info count while open
r, tv = make({"title": None, "channel": None, "app": "Netflix", "app_key": "netflix", "playing": None, "duration": None})
tv.state["app"] = "Netflix"; r.update("sony", "history", {"enabled": True})
tv.apply_rules(r, []); tv.state["app"] = "Prime Video"; tv.apply_rules(r, []); assert r.history == []
for _ in range(4): tv.last_tick -= 3; tv.apply_rules(r, [])
tv.state["on"] = False; tv.apply_rules(r, []); assert len(r.history) == 1 and r.history[0]["app"] == "Prime Video"
# history can be cleared for one TV
r.record({"tv_id": "oneplus", "tv": "Oneplus", "app": "Netflix", "title": None, "channel": None, "watched": 60})
r.clear_history("sony"); assert [x["tv_id"] for x in r.history] == ["oneplus"]
assert [x["tv_id"] for x in Rules(r.dir, TVS).history] == ["oneplus"]

# restricted channels rule
r, tv = make({"title": "Some video", "channel": "DiLSe Gamer"}); r.update("sony", "title_filter", {"enabled": False})
tv.apply_rules(r, []); assert tv.remote.keys == []
r.update("sony", "block_channels", {"enabled": True, "channels": ["dilse"]}); blocked = []
tv.apply_rules(r, blocked); assert tv.remote.keys == ["BACK"] and blocked[0]["word"] == "channel blocked"
r.update("oneplus", "block_channels", {"enabled": True, "channels": []}); assert not r.channel_blocked("oneplus", "DiLSe Gamer")
assert not r.channel_blocked("sony", "Bluey")

# Shorts rule and detection
sample = {"a": [{"shortsLockupViewModel": {"accessibilityText": "Funny cat jump #cat, 6 million views - play Short"}},
                {"videoRenderer": {"title": {"runs": [{"text": "Long documentary"}]}}}]}
assert tvd.short_match(sample, "Funny cat jump #cat") is True
assert tvd.short_match(sample, "Long documentary") is False
assert tvd.short_match(sample, "Something else") is None
r, tv = make({"title": "Funny cat jump", "channel": "Cats", "is_short": True}); blocked = []
r.update("sony", "title_filter", {"enabled": False})
tv.apply_rules(r, blocked); assert tv.remote.keys == []                              # rule is off by default
r.update("sony", "block_shorts", {"enabled": True}); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["BACK"] and blocked[0]["word"] == "YouTube Shorts"
r, tv = make({"title": "Long documentary", "channel": "Docs", "is_short": False})
r.update("sony", "block_shorts", {"enabled": True}); tv.apply_rules(r, []); assert tv.remote.keys == []
r, tv = make({"title": "Pending", "channel": "x", "is_short": None})                # lookup not finished yet
r.update("sony", "block_shorts", {"enabled": True}); tv.apply_rules(r, []); assert tv.remote.keys == []
assert tvd.key_for("a") == "A" and tvd.key_for("7") == "7" and tvd.key_for(" ") == "SPACE" and tvd.key_for("!") is None
# power states
import asyncio
assert asyncio.run(tvd.probe_power("127.0.0.1", 1)) == "deep_sleep"                  # reachable host, closed port
assert asyncio.run(tvd.probe_power("10.255.255.1", 6466)) == "off"                     # nothing answers
tv = tvd.TV({"id": "sony", "name": "Sony", "ip": "x"})
tv.set_power("on"); since = tv.power_since; tv.set_power("on"); assert tv.power_since == since
tv.set_power("standby"); assert tv.power == "standby"; tv.set_power(None); assert tv.power == "standby"
# adult content filter (any app that reports a title)
for ok, text in ((True, "Hot Girls Dance Compilation"), (True, "NSFW compilation"), (True, "Sexy Bikini haul"),
                 (False, "Peppa Pig at the beach"), (False, "Essex County cricket"), (False, "Sussex holiday")):
    assert bool(tvd.ADULT_PAT.search(text)) == ok, text
r, tv = make({"title": "Late Night Erotic Stories", "channel": "Drama", "app": "Hotstar"}); blocked = []
r.update("sony", "title_filter", {"enabled": False}); r.update("sony", "adult_filter", {"enabled": False})
tv.apply_rules(r, blocked); assert tv.remote.keys == []                              # rule off = nothing
r.update("sony", "adult_filter", {"enabled": True}); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["HOME"] and blocked[0]["word"] == "adult content" and "n" in blocked[0]
tv.apply_rules(r, blocked); assert tv.remote.keys == ["HOME"]                        # once per title
r, tv = make({"title": "Hot Girls Dance Compilation", "channel": "x"}); r.update("sony", "title_filter", {"enabled": False})
tv.apply_rules(r, []); assert tv.remote.keys == ["BACK"]                              # in YouTube: back, not Home
r, tv = make({"title": "Cartoon Fun", "channel": "Kids", "app": "Hotstar"}); tv.apply_rules(r, []); assert tv.remote.keys == []
assert Rules(tempfile.mkdtemp(), TVS).cfg["sony"]["adult_filter"]["enabled"] is True   # on by default
# weekly report and export
import csv as _csv, io as _io
r = Rules(tempfile.mkdtemp(), TVS)
today = datetime.date.today(); yday = today - datetime.timedelta(days=1)
r.record({"ts": f"{yday}T20:00:00", "end": f"{yday}T20:30:00", "tv_id": "sony", "tv": "Sony", "app": "YouTube",
          "title": "Cartoon", "channel": "Bluey", "watched": 1500, "length": 1800, "language": "eng"})
r.record({"ts": f"{today}T09:00:00", "end": f"{today}T09:10:00", "tv_id": "sony", "tv": "Sony", "app": "Hotstar",
          "title": "Show", "channel": None, "watched": 600, "length": 1700, "language": "hin"})
r.record({"ts": f"{today}T10:00:00", "end": f"{today}T10:05:00", "tv_id": "oneplus", "tv": "One", "app": "Netflix",
          "title": "Film", "channel": None, "watched": 300, "length": None, "language": None})
r.usage = {str(today): {"sony": 900}, str(yday): {"sony": 2000}}
rep = r.report("sony")
assert len(rep["days"]) == 7 and rep["days"][-1]["date"] == str(today) and rep["days"][-2]["date"] == str(yday)
assert rep["days"][-1]["play"] == 600 and rep["days"][-2]["play"] == 1500 and rep["days"][-2]["session"] == 2000
assert rep["total_play"] == 2100 and rep["top_apps"][0] == {"name": "YouTube", "secs": 1500} and rep["top_channels"] == [{"name": "Bluey", "secs": 1500}]
assert r.report("oneplus")["total_play"] == 300                                       # other TV is separate
rows = list(_csv.reader(_io.StringIO(r.csv_text("sony"))))
assert rows[0][0] == "Date" and len(rows) == 3 and rows[1][4] == "YouTube" and rows[1][7] == "25.0" and rows[2][4] == "Hotstar"
assert len(list(_csv.reader(_io.StringIO(r.csv_text())))) == 4                        # all TVs
live = [{"ts": f"{today}T11:00:00", "tv_id": "sony", "tv": "Sony", "app": "Netflix", "watched": 120, "end": None, "live": True}]
assert "playing now" in r.csv_text("sony", live) and r.report("sony", live)["total_play"] == 2220
# volume cap
r, tv = make({"title": "Cartoon", "channel": "Bluey", "volume": {"level": 45, "max": 100, "muted": False}})
r.update("sony", "title_filter", {"enabled": False}); tv.apply_rules(r, [])
assert tv.remote.keys == []                                                           # off by default
r.update("sony", "volume_cap", {"enabled": True, "max": 40}); tv.apply_rules(r, [])
assert tv.remote.keys == ["VOLUME_DOWN"] * 5
tv.apply_rules(r, []); assert len(tv.remote.keys) == 5                                # waits before pressing again
tv.vol_cooldown = 0; tv.state["volume"] = {"level": 40, "max": 100, "muted": False}; tv.apply_rules(r, [])
assert len(tv.remote.keys) == 5                                                       # at the cap = no action
tv.vol_cooldown = 0; tv.state["volume"] = {"level": 90, "max": 100, "muted": False}; tv.apply_rules(r, [])
assert len(tv.remote.keys) == 20                                                      # at most 15 presses at once
tv.vol_cooldown = 0; tv.state["volume"] = {"level": 90, "max": 100, "muted": True}; tv.apply_rules(r, [])
assert len(tv.remote.keys) == 20                                                      # muted = no action
r.update("sony", "volume_cap", {"max": 2}); assert r.cfg["sony"]["volume_cap"]["max"] == 5
r.update("sony", "volume_cap", {"max": 500}); assert r.cfg["sony"]["volume_cap"]["max"] == 100
assert r.cfg["oneplus"]["volume_cap"] == {"enabled": False, "max": 40}                # per TV
# wake on lan
pkt = tvd.magic_packet("aa:bb:cc:dd:ee:ff")
assert len(pkt) == 102 and pkt[:6] == b"\xff" * 6 and pkt[6:12] == bytes.fromhex("aabbccddeeff") and pkt[-6:] == pkt[6:12]
# playback controls
class MC:
    def __init__(self, status): self.status = status; self.calls = []
    def play(self): self.calls.append("play")
    def pause(self): self.calls.append("pause")
    def seek(self, t): self.calls.append(("seek", round(t, 1)))
class St:
    def __init__(self, state, duration=1000.0, pos=100.0, cmds=15, stream="BUFFERED"):
        self.player_state, self.duration, self.adjusted_current_time = state, duration, pos
        self.supported_media_commands, self.stream_type = cmds, stream
def tvwith(status):
    tv = tvd.TV({"id": "sony", "name": "Sony", "ip": "x"}); tv.remote = Remote()
    class Cast: pass
    tv.cast = Cast(); tv.cast.media_controller = MC(status); return tv
tv = tvwith(St("PLAYING")); tvd.do_playback(tv, "toggle"); assert tv.cast.media_controller.calls == ["pause"]
tv = tvwith(St("PAUSED")); tvd.do_playback(tv, "toggle"); assert tv.cast.media_controller.calls == ["play"]
tv = tvwith(St("PLAYING")); tvd.do_playback(tv, "play"); assert tv.cast.media_controller.calls == []      # already playing
tv = tvwith(St("PLAYING")); tvd.do_playback(tv, "pause"); assert tv.cast.media_controller.calls == ["pause"]
tv = tvwith(St("PAUSED", pos=100)); tvd.do_playback(tv, "skip", delta=30); assert tv.cast.media_controller.calls == [("seek", 130.0)]
tv = tvwith(St("PAUSED", pos=5)); tvd.do_playback(tv, "skip", delta=-30); assert tv.cast.media_controller.calls == [("seek", 0.0)]
tv = tvwith(St("PAUSED", pos=990)); tvd.do_playback(tv, "skip", delta=60); assert tv.cast.media_controller.calls == [("seek", 999.0)]
tv = tvwith(St("PLAYING")); tvd.do_playback(tv, "seek", position=400); assert tv.cast.media_controller.calls == [("seek", 400.0)]
for bad in (St("PLAYING", cmds=1), St("PLAYING", stream="LIVE")):                                           # seeking not allowed
    tv = tvwith(bad)
    try: tvd.do_playback(tv, "seek", position=10); raise SystemExit("seeked a video that cannot seek")
    except ValueError: pass
tv = tvwith(St("IDLE", duration=None)); tvd.do_playback(tv, "toggle")                                         # no session: use the remote's key
assert tv.remote.keys == ["MEDIA_PLAY_PAUSE"]
tv = tvwith(St("IDLE", duration=None)); tvd.do_playback(tv, "skip", delta=10); assert tv.remote.keys == ["MEDIA_FAST_FORWARD"]
try: tvd.do_playback(tv, "explode"); raise SystemExit("accepted a bad action")
except ValueError: pass
# a long video is never a Short, and a missing length falls back to the lookup alone
assert tvd.decide_short(True, 1736) is False and tvd.decide_short(True, 600) is False
assert tvd.decide_short(True, 45) is True and tvd.decide_short(True, None) is False   # no length = never block on title alone
assert tvd.decide_short(False, 30) is False and tvd.decide_short(None, 30) is True
assert tvd.decide_short(None, 120) is False and tvd.decide_short(None, None) is False
# with screen detection available the title verdict is ignored
r, tv = make({"title": "Funny cat jump", "channel": "Cats", "is_short": True}); r.update("sony", "title_filter", {"enabled": False})
r.update("sony", "block_shorts", {"enabled": True}); tv.adb_ok = True; tv.apply_rules(r, []); assert tv.remote.keys == []
tv.adb_ok = False; tv.apply_rules(r, []); assert tv.remote.keys == ["BACK"]
# candidate ids come from the results page, then YouTube confirms
sample2 = {"a": [{"shortsLockupViewModel": {"entityId": "shorts-shelf-item-AAAAAAAAAAA",
                                            "accessibilityText": "Funny cat jump #cat, 6 million views - play Short"}},
                 {"videoRenderer": {"videoId": "BBBBBBBBBBB", "title": {"runs": [{"text": "Long documentary"}]}}}]}
assert tvd.candidate_ids(sample2, "Funny cat jump #cat") == ["AAAAAAAAAAA"]
assert tvd.candidate_ids(sample2, "long documentary") == ["BBBBBBBBBBB"] and tvd.candidate_ids(sample2, "nope") == []
class FakeResp:
    def __init__(self, status): self.status = status
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
class FakeSess:
    def __init__(self, answers): self.answers = answers
    def head(self, url, **kw): return FakeResp(self.answers[url.rsplit("/", 1)[-1]])
assert asyncio.run(tvd.confirm_by_id(FakeSess({"A": 200}), ["A"])) is True
assert asyncio.run(tvd.confirm_by_id(FakeSess({"B": 303}), ["B"])) is False
assert asyncio.run(tvd.confirm_by_id(FakeSess({"A": 200, "B": 303}), ["A", "B"])) is None   # ambiguous, use length
assert asyncio.run(tvd.confirm_by_id(FakeSess({}), [])) is None
# screen-based Shorts detection
import screen as screenmod
fixture = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "youtube-short-oneplus.png"), "rb").read()
assert screenmod.shorts_layout(fixture) is True and screenmod.shorts_layout(b"not an image") is False
normal = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "youtube-normal-oneplus.png"), "rb").read()
assert screenmod.shorts_layout(normal) is False
dark = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "youtube-short-dark-oneplus.png"), "rb").read()
assert screenmod.shorts_layout(dark) is True
home = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "youtube-home-oneplus.png"), "rb").read()
assert screenmod.shorts_layout(home) is False                                           # YouTube's own home screen
import io as _io3
from PIL import Image as _Im3
_buf3 = _io3.BytesIO(); _Im3.effect_noise((480, 270), 70).convert("RGB").save(_buf3, "PNG")
assert screenmod.shorts_layout(_buf3.getvalue()) is False                                # very busy picture: edges by chance                                            # a Short whose picture is still black                                         # a real normal YouTube video
import io as _io2
from PIL import Image as _Im
_buf = _io2.BytesIO(); _Im.effect_noise((480, 270), 70).convert("RGB").save(_buf, "PNG"); busy = _buf.getvalue()
class FakeScreen:
    def __init__(self, frames): self.frames = list(frames); self.calls = 0
    async def screenshot(self):
        self.calls += 1
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
async def run_screen(frames, shorts_on=True, app_key="youtube", on=True, seconds=0.5):
    r, tv = make({"title": None, "channel": None, "app_key": app_key}); tv.online = True; tv.state["on"] = on
    r.update("sony", "block_shorts", {"enabled": shorts_on}); tv.screen = FakeScreen(frames); blocked = []
    old, tvd.SCREEN_INTERVAL = tvd.SCREEN_INTERVAL, 0.05
    try:
        await asyncio.wait_for(tv.screen_loop(r, blocked), seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        tvd.SCREEN_INTERVAL = old
    return tv, blocked
tv, blocked = asyncio.run(run_screen([fixture]))
assert tv.remote.keys == ["BACK"] and blocked[0]["word"] == "YouTube Shorts" and tv.adb_ok is True
tv, _ = asyncio.run(run_screen([busy], seconds=1.5)); assert tv.remote.keys == [] and tv.screen.calls >= 3   # normal video: no action
tv, _ = asyncio.run(run_screen([fixture, busy, fixture, busy, fixture, busy]))                        # one-off looks do not trigger
assert tv.remote.keys == []
tv, _ = asyncio.run(run_screen([fixture], shorts_on=False)); assert tv.remote.keys == [] and tv.screen.calls == 0
tv, _ = asyncio.run(run_screen([fixture], app_key="netflix")); assert tv.remote.keys == [] and tv.screen.calls == 0
tv, _ = asyncio.run(run_screen([fixture], on=False)); assert tv.remote.keys == [] and tv.screen.calls == 0
tv, _ = asyncio.run(run_screen([None])); assert tv.remote.keys == [] and tv.adb_ok is False         # ADB unavailable: quiet
# volume slider
class Cast2:
    def __init__(self, ok=True): self.status = object() if ok else None; self.set = []
    def set_volume(self, v): self.set.append(round(v, 2))
tv = tvd.TV({"id": "sony", "name": "Sony", "ip": "x"}); tv.remote = Remote(); tv.cast = Cast2()
tv.state["volume"] = {"level": 30, "max": 100, "muted": False}
assert tvd.set_volume(tv, 55) == (55, "cast") and tv.cast.set == [0.55]
assert tvd.set_volume(tv, 150) == (100, "cast") and tvd.set_volume(tv, -4) == (0, "cast")      # clamped
assert tvd.set_volume(tv, 80, cap=40) == (40, "cast") and tv.cast.set[-1] == 0.4                 # never above the cap
tv.cast = Cast2(ok=False); tv.remote.keys.clear()                                                # no cast: use key presses
assert tvd.set_volume(tv, 34) == (34, "keys") and tv.remote.keys == ["VOLUME_UP"] * 4
tv.remote.keys.clear(); assert tvd.set_volume(tv, 25) == (25, "keys") and tv.remote.keys == ["VOLUME_DOWN"] * 5
tv.remote.keys.clear(); tvd.set_volume(tv, 100); assert len(tv.remote.keys) == 40               # at most 40 presses
tv.state["volume"] = None
try: tvd.set_volume(tv, 10); raise SystemExit("set a volume without knowing the current one")
except ValueError: pass
# parent mode
import time as _time
r = Rules(tempfile.mkdtemp(), TVS); t0 = _time.time()
assert not r.parent_active("sony") and r.parent_snapshot()["sony"] == {"active": False, "scheduled": False, "seconds_left": None}
r.set_parent("sony", 30, now=t0)
assert r.parent_active("sony", t0 + 60) and not r.parent_active("oneplus", t0 + 60)                 # per TV
assert r.parent_snapshot(t0 + 600)["sony"] == {"active": True, "scheduled": False, "seconds_left": 1200}
assert not r.parent_active("sony", t0 + 31 * 60) and "sony" not in r.parent                         # ends by itself
r.set_parent("sony", None, now=t0); assert r.parent_active("sony", t0 + 10 ** 7)                      # no end time
assert Rules(r.dir, TVS).parent_active("sony", t0 + 10 ** 7)                                          # survives a restart
r.end_parent("sony"); assert not r.parent_active("sony", t0) and not Rules(r.dir, TVS).parent_active("sony")
r.set_parent("sony", 1, now=t0); assert r.parent["sony"]["until"] == t0 + 5 * 60                      # at least 5 minutes
r.end_parent("sony")
try: r.set_parent("tv9", 10); raise SystemExit("accepted an unknown TV")
except ValueError: pass
# scheduled parent mode: a fixed time of day, per TV
import datetime as _dt
at = lambda h, m=0, d=0: _dt.datetime(2026, 11, 4 + d, h, m).timestamp()
r = Rules(tempfile.mkdtemp(), TVS)
assert not r.parent_active("sony", at(18, 30))                                                    # off by default
r.update("sony", "parent_schedule", {"enabled": True, "start": "18:00", "end": "19:00"})
assert r.parent_active("sony", at(18, 30)) and not r.parent_active("oneplus", at(18, 30))          # per TV
assert not r.parent_active("sony", at(17, 59)) and not r.parent_active("sony", at(19, 0))
snap = r.parent_snapshot(at(18, 30))["sony"]; assert snap == {"active": True, "scheduled": True, "seconds_left": 1800}
r.end_parent("sony", at(18, 30))                                                                  # End during the window
assert not r.parent_active("sony", at(18, 45)) and r.parent_active("sony", at(18, 30, 1))          # off today, back tomorrow
r.set_parent("sony", 30, now=at(18, 45)); assert r.parent_snapshot(at(18, 50))["sony"]["scheduled"] is False
r.update("sony", "parent_schedule", {"start": "22:00", "end": "06:00"}); r.parent_skip.clear()
assert r.parent_active("sony", at(2, 0, 1)) and not r.parent_active("sony", at(12))                  # across midnight
assert r.parent_snapshot(at(23, 0))["sony"]["seconds_left"] == 7 * 3600
assert Rules(r.dir, TVS).cfg["sony"]["parent_schedule"]["start"] == "22:00"                         # saved
# the screensaver counts as neither watch time nor TV-on time
r, tv = make({"app": "Screensaver", "app_key": "other", "title": None})
for _ in range(5): tv.last_tick -= 3; tv.apply_rules(r, [])
assert r.used("sony") == 0 and tv.session is None
tv.state["app"] = "YouTube"; tv.state["title"] = "A video"; tv.state["channel"] = "Chan"
for _ in range(5): tv.last_tick -= 3; tv.apply_rules(r, [])
assert r.used("sony") >= 14                                                                          # counts again once something plays
# while parent mode is on nothing is enforced, recorded or counted
r, tv = make({"title": "Minecraft gameplay", "channel": "DiLSe Gamer", "playing": True, "duration": 600, "app_key": "youtube",
              "volume": {"level": 90, "max": 100, "muted": False}})
r.update("sony", "bedtime", {"enabled": True}); r.in_bedtime = lambda tv_id, now=None: True
r.update("sony", "screen_time", {"enabled": True, "minutes": 15}); r.add_usage("sony", 20 * 60)
r.update("sony", "volume_cap", {"enabled": True, "max": 20}); r.update("sony", "block_channels", {"enabled": True, "channels": ["dilse"]})
r.set_parent("sony", 30)
used_before = r.used("sony")
for _ in range(5): tv.last_tick -= 3; tv.apply_rules(r, [])
assert tv.remote.keys == [] and tv.session is None and r.history == [] and r.used("sony") == used_before
r.end_parent("sony"); tv.last_tick -= 3; tv.apply_rules(r, [])                                       # rules are back
assert tv.remote.keys and tv.remote.keys[0] in ("VOLUME_DOWN", "POWER")
# the open session is dropped, not saved, when parent mode starts
r, tv = make({"title": "Cartoon", "channel": "Bluey", "playing": True, "duration": 600, "app_key": "youtube"})
r.update("sony", "title_filter", {"enabled": False})
for _ in range(4): tv.last_tick -= 3; tv.apply_rules(r, [])
assert tv.session is not None
r.set_parent("sony", 30); tv.apply_rules(r, []); assert tv.session is None and r.history == []
print("all rule tests passed")

# blocks go into the history with the rule, and a parent can allow a blocked video
r, tv = make({"title": "Zombie shooting game", "channel": "Fun"}); r.update("sony", "title_filter", {"enabled": True})
import tvd as _t
blocked = []
tv.apply_rules(r, blocked)
b = [e for e in r.history if e.get("blocked")]
assert len(b) == 1 and b[0]["title"] == "Zombie shooting game" and b[0]["can_allow"] and b[0]["watched"] == 0, r.history
print("block reason:", b[0]["reason"])
snap = r.snapshot()["history"]
assert snap[0]["allowed"] is False
r.set_video_allowed("sony", "Zombie shooting game", "Fun")
assert r.snapshot()["history"][0]["allowed"] is True
tv.remote.keys.clear(); tv.blocked_title = None; tv.cooldown = 0
tv.apply_rules(r, blocked)
assert tv.remote.keys == [], "allowed video must not be blocked"
r.set_video_allowed("sony", "Zombie shooting game", "Fun", False)
tv.apply_rules(r, blocked)
assert tv.remote.keys == ["BACK"]
# bedtime blocks are recorded without a video and can't be allowed
r, tv = make({"title": None}); r.update("sony", "bedtime", {"enabled": True, "start": "00:00", "end": "23:59"})
tv.apply_rules(r, [])
assert [e["reason"] for e in r.history if e.get("blocked")] == ["bedtime"] and not r.history[-1]["can_allow"]
assert "Blocked because" in r.csv_text("sony")
print("allow tests ok")

# per-app daily limits and blocked apps
at = lambda h, m=0: datetime.datetime(2026, 11, 3, h, m)                             # a datetime again: the block above made it epoch seconds
YT, NF ="com.google.android.youtube.tv", "com.netflix.ninja"
r = Rules(tempfile.mkdtemp(), TVS)
assert r.cfg["sony"]["app_limits"] == {"enabled": False, "limits": {}} and r.cfg["sony"]["block_apps"] == {"enabled": False, "packages": []}
r.update("sony", "app_limits", {"enabled": True, "limits": {YT: 45, NF: 2, " ": 10}})
assert r.cfg["sony"]["app_limits"]["limits"] == {YT: 45, NF: 5}                      # at least 5 min, blanks ignored
r.update("sony", "app_limits", {"limits": {NF: None}}); assert r.cfg["sony"]["app_limits"]["limits"] == {YT: 45}   # None removes
try: r.update("sony", "app_limits", {"limits": [YT]}); raise SystemExit("accepted a list of limits")
except ValueError: pass
r.update("sony", "block_apps", {"enabled": True, "packages": [NF, NF, " ", YT]}); assert r.cfg["sony"]["block_apps"]["packages"] == [NF, YT]
assert r.app_blocked("sony", NF) and not r.app_blocked("oneplus", NF) and not r.app_blocked("sony", None)      # per TV
r.update("sony", "block_apps", {"packages": [NF]})
r.add_usage("sony", 44 * 60, at(10), package=YT); r.add_usage("sony", 60, at(10)); r.add_usage("oneplus", 3600, at(10), package=YT)
assert r.app_used("sony", YT, at(10)) == 44 * 60 and r.used("sony", at(10)) == 45 * 60 and r.app_usage("sony", "2026-11-03") == {YT: 44 * 60}
assert not r.app_over_limit("sony", YT, at(10))
r.add_usage("sony", 60, at(10), package=YT)
assert r.app_over_limit("sony", YT, at(10)) and not r.app_over_limit("oneplus", YT, at(10))                    # oneplus has no rule
assert not r.app_over_limit("sony", YT, at(10) + datetime.timedelta(days=1))                                     # resets daily
r.update("sony", "app_limits", {"enabled": False}); assert not r.app_over_limit("sony", YT, at(10)) and r.app_limit("sony", YT) is None
assert Rules(r.dir, TVS).cfg["sony"]["block_apps"]["packages"] == [NF]                                           # saved
# engine: a blocked app goes Home as soon as it is in front, with a history entry that says why
r, tv = make({"title": None, "channel": None, "app": "Netflix", "app_key": "netflix", "package": NF}); blocked = []
tv.apply_rules(r, blocked); assert tv.remote.keys == []                                                           # off by default
r.update("sony", "block_apps", {"enabled": True, "packages": [NF]}); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["HOME"] and blocked[0]["word"] == "app blocked" and "Netflix" in blocked[0]["title"]
assert r.history[-1]["blocked"] and r.history[-1]["reason"] == "app is blocked" and not r.history[-1]["can_allow"]
tv.apply_rules(r, blocked); assert tv.remote.keys == ["HOME"]                                                    # cooldown: no repeat
tv.cooldown = 0; tv.state.update(app="YouTube", app_key="youtube", package=YT); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["HOME"]                                                                                 # another app is fine
# engine: usage is counted per app and the limit sends the app Home, but only that app
r, tv = make({"title": None, "channel": None, "app": "YouTube", "app_key": "youtube", "package": YT}); blocked = []
r.update("sony", "app_limits", {"enabled": True, "limits": {YT: 5}})
for _ in range(5): tv.last_tick -= 3; tv.apply_rules(r, [])
assert 14 <= r.app_used("sony", YT) <= 16 and r.used("sony") >= 14 and tv.remote.keys == []
r.add_usage("sony", 5 * 60, package=YT); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["HOME"] and blocked[0]["word"] == "app limit" and "5 min" in blocked[0]["title"]
assert r.history[-1]["reason"] == "daily limit for this app used up"
tv.cooldown = 0; tv.state.update(app="Netflix", app_key="netflix", package=NF); tv.apply_rules(r, blocked)
assert tv.remote.keys == ["HOME"]                                                                                 # Netflix has no limit
tv.state.update(app="Home", app_key="home", package="com.google.android.tvlauncher"); tv.last_tick -= 3; tv.apply_rules(r, [])
assert "com.google.android.tvlauncher" not in r.app_usage("sony")                                                 # the launcher is not an app
assert r.snapshot()["app_usage"]["sony"][YT] >= 5 * 60 and r.report("sony")["days"][-1]["app_usage"][YT] >= 5 * 60
# parent mode: no per-app enforcement or counting
r.set_parent("sony", 30); tv.cooldown = 0; tv.remote.keys.clear(); tv.state.update(app="YouTube", app_key="youtube", package=YT)
used = r.app_used("sony", YT); tv.last_tick -= 3; tv.apply_rules(r, []); assert tv.remote.keys == [] and r.app_used("sony", YT) == used
print("app limit tests ok")

# heads-up before the daily limit and before bedtime
r = Rules(tempfile.mkdtemp(), TVS)
assert r.cfg["sony"]["screen_time"]["warn_minutes"] == 5
r.update("sony", "screen_time", {"enabled": True, "minutes": 30, "warn_minutes": 0}); assert r.cfg["sony"]["screen_time"]["warn_minutes"] == 1
r.update("sony", "screen_time", {"warn_minutes": 5})
r.add_usage("sony", 24 * 60, at(10)); assert r.cutoffs_near("sony", at(10)) == {}
r.add_usage("sony", 60, at(10)); assert r.cutoffs_near("sony", at(10)) == {"daily limit": 300}
r.add_usage("sony", 5 * 60, at(10)); assert r.cutoffs_near("sony", at(10)) == {}                                  # already cut off
r.update("sony", "bedtime", {"enabled": True, "start": "21:00", "end": "07:00"})
assert r.cutoffs_near("sony", at(20, 54)) == {} and r.cutoffs_near("sony", at(20, 56)) == {"bedtime": 240}
assert r.cutoffs_near("sony", at(21, 30)) == {} and r.cutoffs_near("sony", at(6, 59)) == {}                       # inside bedtime
r.update("sony", "bedtime", {"start": "00:02"}); assert r.cutoffs_near("sony", at(23, 59)) == {"bedtime": 180}    # across midnight
assert r.cutoffs_near("oneplus", at(20, 56)) == {}                                                                  # rules are per TV
# engine: once per threshold per day, no key is sent, and the Mac gets it through the blocked feed
r, tv = make({"title": None, "channel": None}); blocked = []
r.update("sony", "screen_time", {"enabled": True, "minutes": 30}); r.add_usage("sony", 25 * 60)
tv.apply_rules(r, blocked)
assert tv.remote.keys == [] and [b["word"] for b in blocked] == ["warning"] and blocked[0]["title"] == "Screen time is up in 5 minutes"
tv.apply_rules(r, blocked); assert len(blocked) == 1                                                                # not repeated
r.add_usage("sony", 3 * 60); tv.apply_rules(r, blocked); assert len(blocked) == 1                                   # 2 min left: nothing new
r.add_usage("sony", 90); tv.apply_rules(r, blocked); assert len(blocked) == 2 and blocked[0]["title"] == "Screen time is up in 1 minute"
tv.apply_rules(r, blocked); assert len(blocked) == 2
r.add_usage("sony", 30); tv.apply_rules(r, blocked); assert tv.remote.keys == ["POWER"] and blocked[0]["word"] == "daily limit"
assert not [e for e in r.history if e.get("reason") == "warning"]                                                   # warnings are not history
r, tv = make({"title": None, "channel": None}); blocked = []
r.update("sony", "screen_time", {"enabled": True, "minutes": 30}); r.add_usage("sony", 29 * 60 + 30)
tv.apply_rules(r, blocked); tv.apply_rules(r, blocked)
assert len(blocked) == 1 and "1 minute" in blocked[0]["title"]                                                      # switched on late: one heads-up only
r.set_parent("sony", 30); tv.warned.clear(); tv.apply_rules(r, blocked); assert len(blocked) == 1                   # parent mode: no warnings
# a bedtime just after midnight: crossing midnight does not repeat the warning, and it still comes the next night
r, tv = make({"title": None, "channel": None}); blocked = []
r.update("sony", "bedtime", {"enabled": True, "start": "00:02", "end": "07:00"}); cfg = r.cfg["sony"]
dt = lambda d, h, m, s=0: datetime.datetime(2026, 11, d, h, m, s)
tv.warn_ahead(r, cfg, blocked, dt(3, 23, 58)); assert blocked[0]["title"] == "Bedtime in 4 minutes" and len(blocked) == 1
tv.warn_ahead(r, cfg, blocked, dt(4, 0, 0, 30)); assert len(blocked) == 1
tv.warn_ahead(r, cfg, blocked, dt(4, 0, 1, 10)); assert blocked[0]["title"] == "Bedtime in 1 minute" and len(blocked) == 2
tv.warn_ahead(r, cfg, blocked, dt(4, 23, 58)); assert len(blocked) == 3
# on the TV: a notification; the blink only when the TV refuses it; nothing without ADB
class Screen:
    def __init__(self, reply): self.reply, self.cmds = reply, []
    async def shell(self, cmd): self.cmds.append(cmd); return self.reply
for reply, n, blink in (("posting:\n  Notification(...)", 1, False), ("Unknown command: post", 2, True),
                        ("Exception occurred while executing", 2, True), (None, 1, False)):
    tv.screen = Screen(reply); asyncio.run(tv.show_on_tv("Bedtime in 5 minutes"))
    assert len(tv.screen.cmds) == n and tv.screen.cmds[0].startswith("cmd notification post") and "'Bedtime in 5 minutes'" in tv.screen.cmds[0]
    assert ("KEYCODE_SLEEP" in tv.screen.cmds[-1]) == blink
print("warning tests ok")
