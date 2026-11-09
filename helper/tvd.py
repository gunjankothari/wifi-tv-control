"""Local helper for the TVRemote menu bar app.

Keeps connections to the TVs and serves a small JSON API on 127.0.0.1:8765.
Also runs the YouTube title filter, which presses BACK when a flagged title plays (leaving the viewer in YouTube).
"""
import secrets, subprocess, sys
import asyncio, datetime, html, itertools, json, os, re, shlex, shutil, socket, tempfile, time, urllib.parse, warnings
warnings.filterwarnings("ignore")
import aiohttp
import pychromecast
from aiohttp import web
from androidtvremote2 import AndroidTVRemote
from rules import Rules
from screen import AdbScreen, shorts_layout

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(getattr(sys, "_MEIPASS", HERE), "web")
FROZEN = bool(getattr(sys, "frozen", False))
MAC_OS = sys.platform == "darwin"


def default_data_dir():
    """Next to the source when run from the repository, otherwise the per-user app data folder."""
    if not FROZEN:
        return os.path.join(HERE, "data")
    if MAC_OS:
        return os.path.expanduser("~/Library/Application Support/TVRemote")
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "TVRemote")


DATA = os.environ.get("TVD_DATA", default_data_dir())
os.makedirs(DATA, exist_ok=True)


def migrate_dev_data():
    """First run of an installed app on the Mac this project was developed on: reuse the paired TVs and settings."""
    legacy = os.path.expanduser("~/Documents/code/TVRemote/helper/data")
    if not FROZEN or any(f.endswith(".pem") for f in os.listdir(DATA)) or not os.path.isdir(legacy):
        return
    for name in os.listdir(legacy):
        if name.endswith((".pem", ".json", ".jsonl")) or name.startswith("adbkey"):
            shutil.copy2(os.path.join(legacy, name), os.path.join(DATA, name))


migrate_dev_data()
PORT = int(os.environ.get("TVD_PORT", "8765"))
TV_FILE = os.path.join(DATA, "tvs.json")
# The two TVs this project started with; used once, when an existing setup has paired certificates but no tvs.json yet.
LEGACY_TVS = [
    {"id": "sony", "name": "Sony BRAVIA", "ip": "192.168.29.47"},
    {"id": "oneplus", "name": "OnePlus TV", "ip": "192.168.29.77"},
]


def load_tvs():
    try:
        return json.load(open(TV_FILE))
    except Exception:
        pass
    found = [t for t in LEGACY_TVS if os.path.exists(os.path.join(DATA, t["id"] + "-cert.pem"))]
    if found:
        save_tvs(found)
    return found


def save_tvs(tvs):
    json.dump(tvs, open(TV_FILE, "w"), indent=1)


TVS = load_tvs()
APPS = {
    "primevideo": "https://app.primevideo.com",
    "youtube": "https://www.youtube.com",
    "netflix": "https://www.netflix.com/title",
    "hotstar": "https://www.hotstar.com",
    "sonyliv": "https://www.sonyliv.com",
    "zee5": "https://www.zee5.com",
}
APP_NAMES = {
    "com.google.android.youtube.tv": "YouTube",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.google.android.tvlauncher": "Home",
    "com.netflix.ninja": "Netflix",
}

# Search pages that open inside each TV app (YouTube search is handled in the app itself).
SEARCH = {
    "primevideo": ("Prime Video", "https://www.primevideo.com/search?phrase={q}"),
    "netflix": ("Netflix", "https://www.netflix.com/search?q={q}"),
    "hotstar": ("Hotstar", "https://www.hotstar.com/in/search?q={q}"),
    "sonyliv": ("SonyLIV", "https://www.sonyliv.com/search?q={q}"),
    "zee5": ("ZEE5", "https://www.zee5.com/search?q={q}"),
}


NICE_NAMES = {"youtube": "YouTube", "primevideo": "Prime Video", "netflix": "Netflix", "hotstar": "Hotstar",
              "sonyliv": "SonyLIV", "zee5": "ZEE5", "home": "Home"}


def app_name_for(pkg):
    if not pkg:
        return None
    if pkg in APP_NAMES:
        return APP_NAMES[pkg]
    last = pkg.split(".")[-1]
    return NICE_NAMES.get(app_key(pkg)) or {"backdrop": "Screensaver", "dreamx": "Screensaver"}.get(last) or last


def app_key(pkg):
    p = (pkg or "").lower()
    if not p:
        return None
    for key, needles in (("youtube", ("youtube",)), ("primevideo", ("amazonvideo", "primevideo")),
                         ("netflix", ("netflix",)), ("hotstar", ("hotstar",)),
                         ("sonyliv", ("sonyliv",)), ("zee5", ("zee5", "graymatrix")),
                         ("home", ("tvlauncher", "launcher", "leanbacklauncher"))):
        if any(n in p for n in needles):
            return key
    return "other"


APP_INFO_FILE = os.path.join(DATA, "appinfo.json")
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
# Apps that come with the TV and have no Play Store page.
SYSTEM_APP_NAMES = {"com.android.tv.settings": "Settings", "com.google.android.tv": "Live Channels",
                    "com.android.vending": "Google Play Store", "com.google.android.youtube.tvmusic": "YouTube Music",
                    "com.google.android.youtube.tvkids": "YouTube Kids", "com.sony.dtv.tvx": "TV",
                    "com.google.android.videos": "Google TV", "com.android.documentsui": "Files"}
# Launcher entries that open nothing useful on their own.
HIDDEN_APPS = {"com.google.android.tvlauncher", "com.google.android.apps.tv.launcherx",
               "com.google.android.leanbacklauncher"}


def load_app_info():
    try:
        return json.load(open(APP_INFO_FILE))
    except Exception:
        return {}


APP_INFO = load_app_info()


def guess_app_name(pkg):
    """A readable name from a package id, for apps the Play Store doesn't know: com.sony.dtv.photoviewer → Photoviewer."""
    parts = [p for p in pkg.split(".") if p not in ("com", "tv", "android", "app", "atv", "dtv", "leanback", "androidtv")]
    return (parts[-1] if parts else pkg.split(".")[-1]).replace("_", " ").capitalize()


async def app_info(sess, pkg):
    """Name and icon for a package: the Play Store page's title and image, looked up once and kept."""
    if pkg in APP_INFO:
        return APP_INFO[pkg]
    info = {"name": SYSTEM_APP_NAMES.get(pkg) or APP_NAMES.get(pkg), "icon": None}
    try:
        url = "https://play.google.com/store/apps/details?id=%s&hl=en" % pkg
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                page = await r.text()
                title = re.search(r'<meta property="og:title" content="([^"]+)"', page)
                image = re.search(r'<meta property="og:image" content="([^"]+)"', page)
                if title and not info["name"]:
                    info["name"] = html.unescape(re.sub(r"\s+-\s+Apps on Google Play$", "", title.group(1)))
                if image:
                    info["icon"] = html.unescape(image.group(1)).split("=")[0] + "=s96"   # a 96px icon
            elif r.status != 404:
                return {"name": info["name"] or guess_app_name(pkg), "icon": None}   # try again next time
    except Exception:
        return {"name": info["name"] or guess_app_name(pkg), "icon": None}
    info["name"] = info["name"] or guess_app_name(pkg)
    APP_INFO[pkg] = info
    return info



async def installed_apps(tv):
    """The apps on the TV's home screen (those with a TV launcher entry), or None when ADB isn't reachable."""
    out = await tv.screen.shell("cmd package query-activities --brief -a android.intent.action.MAIN "
                                "-c android.intent.category.LEANBACK_LAUNCHER")
    if out is None:
        return None
    pkgs = re.findall(r"^\s*([A-Za-z][\w.]*)/[\w.$]+\s*$", out, re.M)
    if not pkgs:                                   # older Android without query-activities: the apps people installed
        out = await tv.screen.shell("pm list packages -3")
        if out is None:
            return None
        pkgs = re.findall(r"^package:(\S+)", out, re.M)
    pkgs = sorted({p for p in pkgs if p not in HIDDEN_APPS})
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"}) as sess:
        infos = await asyncio.gather(*(app_info(sess, p) for p in pkgs))
    try:
        json.dump(APP_INFO, open(APP_INFO_FILE, "w"), indent=1)
    except Exception:
        pass
    apps = [{"package": p, "name": i["name"], "icon": i["icon"]} for p, i in zip(pkgs, infos)]
    return sorted(apps, key=lambda a: a["name"].lower())


ADULT_WORDS = """porn porno pornhub xxx nsfw nude nudes naked sex sexy sexual erotic erotica onlyfans hentai
fetish stripper striptease escort milf boobs lingerie cleavage twerk seductive topless underwear 18+ adults-only
hookup orgasm""".split()
ADULT_PHRASES = ["adult only", "adults only", "hot girls", "dirty talk", "r-rated", "sex scene", "hot scene",
                 "bedroom scene", "bikini haul", "only fans"]
ADULT_PAT = re.compile(r"(?<!\w)(" + "|".join(re.escape(x) for x in ADULT_PHRASES + ADULT_WORDS) + r")(?!\w)", re.I)

PHRASES = ["among us", "free fire", "let's play", "lets play", "dead body", "five nights",
           "poppy playtime", "call of duty", "horror game"]
WORDS = """gun guns shooting shooter shot murder murdered kill killed killing dead death die dying blood
bloody gore horror scary creepy nightmare zombie ghost haunted demon possessed police arrested crime
criminal kidnap kidnapped torture suicide drugs drug alcohol vodka beer wine weed sex sexy nude naked
nsfw 18+ roast prank fnaf backrooms scp creepypasta granny gta warzone pubg bgmi fortnite gameplay
walkthrough speedrun gaming gamer minecraft roblox""".split()
PAT = re.compile(r"(?<!\w)(" + "|".join(re.escape(x) for x in PHRASES + WORDS) + r")(?!\w)", re.I)

FILTER_FILE = os.path.join(DATA, "filter.json")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


THUMBS = {}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


async def find_thumb(key, title, channel):
    """Looks up the playing video on YouTube by title and channel and stores its thumbnail URL."""
    url = ""
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(headers={"User-Agent": UA, "Accept-Language": "en"},
                                         cookies={"CONSENT": "YES+1"}, timeout=timeout) as s:
            async with s.get("https://www.youtube.com/results",
                             params={"search_query": f"{title} {channel}".strip()}) as resp:
                m = re.search(r'"videoId":"([\w-]{11})"', await resp.text())
        if m:
            url = f"https://i.ytimg.com/vi/{m.group(1)}/mqdefault.jpg"
    except Exception as e:
        log("thumbnail lookup failed:", repr(e))
    THUMBS[key] = url


def _videos(node):
    """Yields every videoRenderer dict found in YouTube's embedded results JSON."""
    if isinstance(node, dict):
        if "videoRenderer" in node:
            yield node["videoRenderer"]
        for v in node.values():
            yield from _videos(v)
    elif isinstance(node, list):
        for v in node:
            yield from _videos(v)


async def yt_search(query, limit=8):
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(headers={"User-Agent": UA, "Accept-Language": "en"},
                                     cookies={"CONSENT": "YES+1"}, timeout=timeout) as s:
        async with s.get("https://www.youtube.com/results",
                         params={"search_query": query, "sp": "EgIQAQ=="}) as resp:
            html = await resp.text()
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    out = []
    for v in _videos(json.loads(m.group(1))):
        vid = v.get("videoId")
        if not vid or any(r["id"] == vid for r in out):
            continue
        out.append({
            "id": vid,
            "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
            "channel": "".join(r.get("text", "") for r in v.get("ownerText", {}).get("runs", [])),
            "duration": v.get("lengthText", {}).get("simpleText"),
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
        if len(out) >= limit:
            break
    return out


FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
CAM_PORT = 8767
CAM = {"proc": None, "runner": None, "dir": None, "tv": None}


async def camera_device():
    """Index of the built-in camera (falls back to the first video device)."""
    p = await asyncio.create_subprocess_exec(
        FFMPEG, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", "",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    video, audio = [], []
    section = video
    for line in err.decode(errors="ignore").splitlines():
        if "AVFoundation audio devices" in line:
            section = audio
            continue
        m = re.search(r"\] \[(\d+)\] (.+)$", line)
        if m:
            section.append((m.group(1), m.group(2)))
    if not video:
        raise RuntimeError("no camera found")

    def pick(devices, hints):
        for idx, name in devices:
            if any(h in name for h in hints):
                return idx
        return devices[0][0] if devices else None

    return pick(video, ("FaceTime", "Built-in")), pick(audio, ("MacBook", "Built-in", "Microphone"))


async def camera_stop():
    proc, runner, d, tv = CAM["proc"], CAM["runner"], CAM["dir"], CAM["tv"]
    CAM.update(proc=None, runner=None, dir=None, tv=None)
    if tv is not None and tv.cast is not None:
        try:
            await asyncio.get_running_loop().run_in_executor(None, tv.cast.quit_app)
        except Exception as e:
            log("camera: could not close cast app:", repr(e))
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except asyncio.TimeoutError:
            proc.kill()
    if runner:
        await runner.cleanup()
    if d:
        shutil.rmtree(d, ignore_errors=True)
    log("camera stopped")


async def camera_start(tv):
    """Streams the Mac camera as live HLS and tells the TV's media receiver to play it.

    The stream is served on the LAN only while the camera is on.
    """
    if CAM["proc"]:
        await camera_stop()
    await media_stop()
    if tv.cast is None:
        raise RuntimeError("TV cast connection not ready")
    vidx, aidx = await camera_device()
    d = tempfile.mkdtemp(prefix="tvcam-")
    audio_args = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"] if aidx is not None else []
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-f", "avfoundation", "-framerate", "30", "-video_size", "1280x720",
        "-i", f"{vidx}:{aidx if aidx is not None else 'none'}",
        "-vf", "format=yuv420p", "-c:v", "h264_videotoolbox", "-b:v", "2500k", "-g", "30", *audio_args,
        "-f", "hls", "-hls_time", "1", "-hls_list_size", "4",
        "-hls_flags", "delete_segments+independent_segments", f"{d}/stream.m3u8",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    CAM.update(proc=proc, dir=d, tv=tv)
    try:
        for _ in range(60):
            if proc.returncode is not None:
                err = (await proc.stderr.read()).decode(errors="ignore").strip()
                raise RuntimeError(f"ffmpeg exited: {err[-300:] or proc.returncode}")
            if os.path.exists(f"{d}/stream.m3u8") and any(f.endswith(".ts") for f in os.listdir(d)):
                break
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("camera produced no video (is camera access allowed?)")

        @web.middleware
        async def no_cache(request, handler):
            resp = await handler(request)
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp

        site_app = web.Application(middlewares=[no_cache])
        site_app.router.add_static("/cam/", d)
        runner = web.AppRunner(site_app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", CAM_PORT).start()
        CAM["runner"] = runner

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((tv.ip, 9))
        host = s.getsockname()[0]
        s.close()
        url = f"http://{host}:{CAM_PORT}/cam/stream.m3u8"

        def cast_it():
            mc = tv.cast.media_controller
            mc.play_media(url, "application/x-mpegURL", stream_type="LIVE")
            mc.block_until_active(timeout=15)

        await asyncio.get_running_loop().run_in_executor(None, cast_it)
        log("camera streaming to", tv.id, url)
    except Exception:
        await camera_stop()
        raise


SHORTS = {}
SCREEN_INTERVAL = 3          # seconds between screen checks while YouTube is in front
ADB_KEY = os.path.join(DATA, "adbkey")
SHORT_WAIT = {}
BLOCK_COUNTER = itertools.count(1)
MIN_SESSION_SECONDS = 5


def short_match(data, title):
    """True/False when YouTube's results page shows `title` only as a Short / only as a long video, else None."""
    t = title.strip().lower()
    found_short = found_long = False
    stack = [data]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            vm = n.get("shortsLockupViewModel")
            if isinstance(vm, dict) and str(vm.get("accessibilityText", "")).lower().startswith(t):
                found_short = True
            vr = n.get("videoRenderer")
            if isinstance(vr, dict):
                name = "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", []))
                if name.strip().lower() == t:
                    found_long = True
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    if found_short != found_long:
        return found_short
    return None


SHORT_MAX_SECONDS = 185        # Shorts can run up to 3 minutes; anything clearly longer is not one


def decide_short(verdict, duration):
    """Combines the search-results verdict (True/False/None) with the video length.

    A video clearly longer than a Short can never be one, which stops a long episode being blocked just
    because a clip with the same title shows up in the Shorts shelf.
    """
    if duration and duration > SHORT_MAX_SECONDS:
        return False
    if not duration:
        return False            # a title alone is not enough: Shorts often reuse the title of a long video
    if verdict is None:
        return duration <= 60
    return bool(verdict)


def candidate_ids(data, title):
    """Video ids in a results page whose title matches `title` (long videos and Shorts alike)."""
    t = title.strip().lower()
    ids = []
    stack = [data]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            vm = n.get("shortsLockupViewModel")
            if isinstance(vm, dict) and str(vm.get("accessibilityText", "")).lower().startswith(t):
                eid = str(vm.get("entityId", ""))
                vid = eid.rsplit("-", 1)[-1] if eid.startswith("shorts-shelf-item-") else None
                if vid and vid not in ids:
                    ids.append(vid)
            vr = n.get("videoRenderer")
            if isinstance(vr, dict):
                name = "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", []))
                if name.strip().lower() == t and vr.get("videoId") and vr["videoId"] not in ids:
                    ids.append(vr["videoId"])
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return ids[:4]


async def confirm_by_id(sess, ids):
    """Asks YouTube directly: /shorts/<id> answers 200 for a Short and redirects (303) for a normal video.

    Returns True/False when every matching video agrees, else None (no match, or a long video and a Short
    share the title)."""
    results = set()
    for vid in ids:
        try:
            async with sess.head(f"https://www.youtube.com/shorts/{vid}", allow_redirects=False) as r:
                if r.status == 200:
                    results.add(True)
                elif r.status in (301, 302, 303, 307, 308):
                    results.add(False)
        except Exception:
            pass
    return results.pop() if len(results) == 1 else None


async def check_short(key, title, channel, duration):
    """Decides whether the playing YouTube video is a Short and caches the answer."""
    if re.search(r"#shorts?\b", title, re.I) and not (duration and duration > SHORT_MAX_SECONDS):
        SHORTS[key] = True
        return
    verdict = None
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(headers={"User-Agent": UA, "Accept-Language": "en"},
                                         cookies={"CONSENT": "YES+1"}, timeout=timeout) as sess:
            async with sess.get("https://www.youtube.com/results",
                                params={"search_query": f"{title} {channel or ''}".strip()}) as resp:
                html = await resp.text()
            m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
            if m:
                data = json.loads(m.group(1))
                verdict = await confirm_by_id(sess, candidate_ids(data, title))
                if verdict is None:
                    verdict = short_match(data, title)
    except Exception as e:
        log("shorts lookup failed:", repr(e))
    verdict = decide_short(verdict, duration)
    SHORTS[key] = verdict
    if verdict:
        log("detected a YouTube Short:", title)


def key_for(ch):
    if ch.isascii() and ch.isalnum():
        return ch.upper()
    return {" ": "SPACE", "-": "MINUS", "'": "APOSTROPHE", ".": "PERIOD", ",": "COMMA"}.get(ch)


async def type_keys(tv, text, open_search, submit):
    """Types `text` on the TV as key presses (the app's search box must be focused), optionally after
    pressing the SEARCH key, and presses Enter at the end."""
    try:
        if open_search:
            tv.remote.send_key_command("SEARCH")
            await asyncio.sleep(2)
        for ch in text:
            k = key_for(ch)
            if k:
                tv.remote.send_key_command(k)
                await asyncio.sleep(0.15)
        if submit:
            await asyncio.sleep(0.4)
            tv.remote.send_key_command("ENTER")
        log(tv.id, "typed", repr(text))
    except Exception as e:
        log(tv.id, "typing failed:", repr(e))


async def probe_power(ip, port=6466):
    """Tells apart a TV that is asleep but on the network (it refuses the connection) from one that is
    completely off or off Wi-Fi (no answer). Returns None if the port is actually reachable."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), 2)
        writer.close()
        return None
    except ConnectionRefusedError:
        return "deep_sleep"
    except (asyncio.TimeoutError, OSError):
        return "off"


VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".3gp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
MEDIA_PORT = 8768
SLIDE_SECONDS = 8
VIDEO_ENCODER = "h264_videotoolbox"          # Mac hardware encoder; playing files is a Mac-only feature
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
MEDIA = {"runner": None, "tv": None, "kind": None, "name": None, "count": 0, "task": None, "proc": None,
         "dir": None, "files": {}}


def media_kind(path):
    ext = os.path.splitext(path)[1].lower()
    return "video" if ext in VIDEO_EXTS else "image" if ext in IMAGE_EXTS else None


async def can_play_directly(path):
    """H.264 video (with AAC/MP3 or no audio) in an MP4/MOV container plays on a TV as it is."""
    if os.path.splitext(path)[1].lower() not in (".mp4", ".m4v", ".mov"):
        return False
    p = await asyncio.create_subprocess_exec(
        FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await p.communicate()
    try:
        streams = json.loads(out).get("streams", [])
    except ValueError:
        return False
    video = [s["codec_name"] for s in streams if s.get("codec_type") == "video"]
    audio = [s["codec_name"] for s in streams if s.get("codec_type") == "audio"]
    return bool(video) and video[0] == "h264" and all(a in ("aac", "mp3") for a in audio)


def lan_ip_for(target_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((target_ip, 9))
    ip = s.getsockname()[0]
    s.close()
    return ip


async def media_stop():
    task, proc, runner, d, tv = MEDIA["task"], MEDIA["proc"], MEDIA["runner"], MEDIA["dir"], MEDIA["tv"]
    MEDIA.update(task=None, proc=None, runner=None, dir=None, tv=None, kind=None, name=None, count=0, files={})
    if task:
        task.cancel()
    if tv is not None and tv.cast is not None:
        try:
            await asyncio.get_running_loop().run_in_executor(None, tv.cast.quit_app)
        except Exception as e:
            log("media: could not close cast app:", repr(e))
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except asyncio.TimeoutError:
            proc.kill()
    if runner:
        await runner.cleanup()
    if d:
        shutil.rmtree(d, ignore_errors=True)
    log("media stopped")


async def media_start(tv, paths):
    """Plays a video, or a slideshow of photos, from this Mac on the TV.

    Files are served on the LAN only while they play, and only the ones you picked.
    """
    if CAM["proc"]:
        await camera_stop()
    await media_stop()
    if tv.cast is None:
        raise RuntimeError("TV cast connection not ready")
    paths = [p for p in paths if os.path.isfile(p) and media_kind(p)]
    if not paths:
        raise RuntimeError("no playable video or photo selected")
    kind = media_kind(paths[0])
    d = tempfile.mkdtemp(prefix="tvmedia-")
    MEDIA.update(tv=tv, dir=d, kind=kind)
    try:
        loop = asyncio.get_running_loop()
        items = []                                   # (url path, mime type)
        if kind == "video":
            path = paths[0]
            MEDIA.update(name=os.path.basename(path), count=1)
            if await can_play_directly(path):
                token = secrets.token_urlsafe(12)
                MEDIA["files"][token] = path
                items.append((f"/m/{token}", "video/mp4"))
            else:
                proc = await asyncio.create_subprocess_exec(
                    FFMPEG, "-hide_banner", "-loglevel", "error", "-i", path,
                    "-vf", "scale='min(1920,iw)':-2,format=yuv420p", "-c:v", VIDEO_ENCODER, "-b:v", "5M",
                    "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-f", "hls", "-hls_time", "4",
                    "-hls_list_size", "0", "-hls_playlist_type", "event", "-hls_flags", "independent_segments",
                    f"{d}/index.m3u8", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                MEDIA["proc"] = proc
                for _ in range(120):
                    if proc.returncode not in (None, 0):
                        err = (await proc.stderr.read()).decode(errors="ignore").strip()
                        raise RuntimeError(f"could not convert the video: {err[-200:]}")
                    if os.path.exists(f"{d}/index.m3u8") and len([f for f in os.listdir(d) if f.endswith(".ts")]) >= 2:
                        break
                    await asyncio.sleep(0.25)
                else:
                    raise RuntimeError("converting the video took too long")
                items.append(("/h/index.m3u8", "application/x-mpegURL"))
        else:
            images = [p for p in paths if media_kind(p) == "image"]
            MEDIA.update(name=os.path.basename(images[0]) if len(images) == 1 else f"{len(images)} photos",
                         count=len(images))
            for p in images:
                if p.lower().endswith(".heic"):      # TVs cannot show HEIC; convert with macOS's own tool
                    out = os.path.join(d, secrets.token_hex(4) + ".jpg")
                    c = await asyncio.create_subprocess_exec("sips", "-s", "format", "jpeg", p, "--out", out,
                                                             stdout=asyncio.subprocess.DEVNULL,
                                                             stderr=asyncio.subprocess.DEVNULL)
                    await c.wait()
                    if not os.path.exists(out):
                        continue
                    p = out
                token = secrets.token_urlsafe(12)
                MEDIA["files"][token] = p
                mime = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}.get(
                    os.path.splitext(p)[1].lower(), "image/jpeg")
                items.append((f"/m/{token}", mime))
            if not items:
                raise RuntimeError("could not read the photos")

        @web.middleware
        async def cors(request, handler):
            resp = await handler(request)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Cache-Control"] = "no-store"
            return resp

        async def serve_file(request):
            path = MEDIA["files"].get(request.match_info["token"])
            if path is None:
                raise web.HTTPNotFound()
            return web.FileResponse(path)

        site_app = web.Application(middlewares=[cors])
        site_app.router.add_get("/m/{token}", serve_file)
        site_app.router.add_static("/h/", d)
        runner = web.AppRunner(site_app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", MEDIA_PORT).start()
        MEDIA["runner"] = runner
        base = f"http://{lan_ip_for(tv.ip)}:{MEDIA_PORT}"

        def cast_item(item):
            mc = tv.cast.media_controller
            mc.play_media(base + item[0], item[1], title=MEDIA["name"] or "",
                          stream_type="BUFFERED")
            mc.block_until_active(timeout=15)

        await loop.run_in_executor(None, cast_item, items[0])
        if len(items) > 1:
            async def slideshow():
                i = 0
                while True:
                    await asyncio.sleep(SLIDE_SECONDS)
                    i = (i + 1) % len(items)
                    await loop.run_in_executor(None, cast_item, items[i])
            MEDIA["task"] = asyncio.create_task(slideshow())
        log("media playing on", tv.id, kind, MEDIA["name"])
    except Exception:
        await media_stop()
        raise


def set_volume(tv, level, cap=None):
    """Sets the TV's volume to `level` (0-100), never above the volume cap.

    Uses the exact volume control the TV offers over Cast; if that isn't connected, presses volume up or down
    the right number of times instead. Returns (level actually set, method).
    """
    level = max(0, min(100, int(level)))
    if cap is not None:
        level = min(level, cap)
    if tv.cast is not None and getattr(tv.cast, "status", None) is not None:
        tv.cast.set_volume(level / 100)
        return level, "cast"
    vol = tv.state["volume"]
    if not vol:
        raise ValueError("the TV's volume isn't known yet")
    diff = level - vol["level"]
    for _ in range(min(abs(diff), 40)):
        tv.remote.send_key_command("VOLUME_UP" if diff > 0 else "VOLUME_DOWN")
    return level, "keys"


def media_session(tv):
    """The TV's current media status when an app is playing something it reports, else None."""
    try:
        mc = tv.cast.media_controller if tv.cast is not None else None
        st = mc.status if mc is not None else None
    except Exception:
        return None, None
    if st is not None and st.player_state in ("PLAYING", "PAUSED", "BUFFERING") and st.duration:
        return mc, st
    return None, None


def do_playback(tv, action, position=None, delta=None):
    """Play, pause, toggle, seek or skip the video that is playing on the TV.

    Uses the app's own playback connection when it has one; otherwise falls back to the TV remote's media keys.
    """
    mc, st = media_session(tv)
    if action in ("toggle", "play", "pause"):
        playing = st is not None and st.player_state == "PLAYING"
        want_play = (not playing) if action == "toggle" else action == "play"
        if mc is not None:
            if want_play and not playing:
                mc.play()
            elif not want_play and playing:
                mc.pause()
        else:
            tv.remote.send_key_command("MEDIA_PLAY_PAUSE" if action == "toggle" else
                                       ("MEDIA_PLAY" if want_play else "MEDIA_PAUSE"))
        return "ok"
    if action in ("seek", "skip"):
        if mc is None or not (st.supported_media_commands & 2) or st.stream_type == "LIVE":
            if action == "skip" and mc is None and delta:
                tv.remote.send_key_command("MEDIA_FAST_FORWARD" if delta > 0 else "MEDIA_REWIND")
                return "ok"
            raise ValueError("this video can't be skipped")
        target = float(position) if action == "seek" else st.adjusted_current_time + float(delta)
        mc.seek(max(0.0, min(target, st.duration - 1)))
        return "ok"
    raise ValueError("unknown action")


MAC_FILE = os.path.join(DATA, "macs.json")


def load_macs():
    try:
        return json.load(open(MAC_FILE))
    except Exception:
        return {}


def lookup_mac(ip):
    """Reads the TV's hardware address from the Mac's neighbour table (works while the TV is on the network)."""
    try:
        cmd = ["arp", "-a", ip] if sys.platform == "win32" else ["arp", "-n", ip]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
        m = re.search(r"((?:[0-9a-f]{1,2}[:-]){5}[0-9a-f]{1,2})", out.split(ip, 1)[-1], re.I)
        if m:
            return ":".join(p.zfill(2) for p in re.split(r"[:-]", m.group(1).lower()))
    except Exception:
        pass
    return None


def magic_packet(mac):
    raw = bytes.fromhex(mac.replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_wol(mac, ip):
    """Wake-on-LAN: broadcasts the magic packet to the network and to the TV's own subnet."""
    packet = magic_packet(mac)
    targets = {"255.255.255.255", ip.rsplit(".", 1)[0] + ".255"}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for t in targets:
            for port in (9, 7):
                s.sendto(packet, (t, port))


REASONS = {"adult content": "adult content filter", "channel not allowed": "channel is not on the allowed list",
           "channel blocked": "channel is restricted", "YouTube Shorts": "YouTube Shorts are blocked",
           "bedtime": "bedtime", "daily limit": "daily screen time used up",
           "app limit": "daily limit for this app used up", "app blocked": "app is blocked"}


class TV:
    def __init__(self, cfg):
        self.id, self.name, self.ip = cfg["id"], cfg["name"], cfg["ip"]
        self.remote = None
        self.cast = None
        self.online = False
        self.state = {"on": None, "app": None, "volume": None, "title": None, "channel": None, "thumb": None,
                      "app_key": None, "package": None, "duration": None, "position": None, "playing": None,
                      "is_short": None, "language": None, "player_state": None, "can_seek": None}
        self.blocked_title = None
        self.rules = None
        self.cooldown = 0.0
        self.last_tick = time.time()
        self.session = None
        self.power = None
        self.power_since = None
        self.vol_cooldown = 0.0
        self.screen = AdbScreen(ip=cfg["ip"], key_path=ADB_KEY)
        self.adb_ok = False
        self.screen_task = None
        self.short_streak = 0
        self.adb_probe_at = 0.0
        self.mac = load_macs().get(self.id)
        self.warned = set()          # (day, cut-off, minutes ahead): each heads-up is given once a day

    def set_power(self, power):
        if power and power != self.power:
            self.power = power
            self.power_since = datetime.datetime.now().isoformat(timespec="seconds")

    def snapshot(self):
        s = self.state
        return {"id": self.id, "name": self.name, "ip": self.ip, "online": self.online,
                "on": s["on"], "app": s["app"], "volume": s["volume"], "title": s["title"],
                "channel": s["channel"], "thumb": s["thumb"] or None, "app_key": s["app_key"],
                "duration": s["duration"], "position": s["position"], "playing": s["playing"],
                "player_state": s["player_state"], "can_seek": s["can_seek"],
                "power": self.power, "since": self.power_since, "adb": self.adb_ok}

    async def run(self, rules, blocked):
        self.rules = rules
        loop = asyncio.get_running_loop()
        while True:
            try:
                r = AndroidTVRemote("TVRemote", f"{DATA}/{self.id}-cert.pem", f"{DATA}/{self.id}-key.pem", self.ip)
                await r.async_connect()
                r.keep_reconnecting()
                self.remote = r
                if self.cast is None:
                    c = await loop.run_in_executor(
                        None, lambda: pychromecast.get_chromecast_from_host((self.ip, 8009, None, None, self.id)))
                    await loop.run_in_executor(None, lambda: c.wait(timeout=15))
                    self.cast = c
                log(self.id, "connected")
                if self.screen_task is None:
                    self.screen_task = asyncio.create_task(self.screen_loop(rules, blocked))
                mac = await loop.run_in_executor(None, lookup_mac, self.ip)
                if mac and mac != self.mac:
                    self.mac = mac
                    macs = load_macs()
                    macs[self.id] = mac
                    json.dump(macs, open(MAC_FILE, "w"))
                probe_at = 0.0
                while True:
                    if time.time() >= probe_at:
                        # The remote library keeps its last "on" state when the TV drops off the network, so check
                        # that the TV still answers instead of trusting that state.
                        probe_at = time.time() + 6
                        gone = await probe_power(self.ip)
                        if gone:
                            raise ConnectionError(f"TV stopped answering ({gone})")
                    self.online = True
                    self.refresh()
                    self.apply_rules(rules, blocked)
                    await asyncio.sleep(2)
            except Exception as e:
                self.online = False
                if self.remote is not None:
                    try:
                        self.remote.disconnect()
                    except Exception:
                        pass
                    self.remote = None
                self.close_session(rules)
                self.state.update(on=None, app=None, app_key=None, package=None, volume=None, title=None, channel=None,
                                  thumb=None, duration=None, position=None, playing=None, is_short=None, language=None,
                                  player_state=None, can_seek=None)
                self.set_power(await probe_power(self.ip))
                log(self.id, "error:", repr(e), "- power:", self.power, "- retry in 15s")
                await asyncio.sleep(15)

    def refresh(self):
        r = self.remote
        pkg = r.current_app
        title = channel = thumb = duration = position = playing = is_short = language = None
        player_state = can_seek = None
        try:
            app_name = self.cast.app_display_name if self.cast is not None else None
            if app_name:
                st = self.cast.media_controller.status
                title, channel = st.title or None, st.artist or None
                if st.duration:
                    duration, position = st.duration, st.adjusted_current_time
                    playing = st.player_state == "PLAYING"
                    player_state = st.player_state
                    can_seek = bool(st.supported_media_commands & 2) and st.stream_type != "LIVE"
                if st.images:
                    thumb = st.images[0].url
                language = ((st.media_custom_data or {}).get("audio_language_info") or {}).get("iso3code")
                if title and app_name == "YouTube" and not thumb:
                    key = f"{title}|{channel}"
                    if key not in THUMBS:
                        THUMBS[key] = None
                        asyncio.get_running_loop().create_task(find_thumb(key, title, channel or ""))
                    thumb = THUMBS[key]
                    if key not in SHORTS:
                        # wait (a few polls) for the video length, so a long video is never mistaken for a Short
                        SHORT_WAIT[key] = SHORT_WAIT.get(key, 0) + 1
                        if duration or SHORT_WAIT[key] >= 4:
                            SHORTS[key] = None
                            asyncio.get_running_loop().create_task(check_short(key, title, channel, duration))
                    is_short = SHORTS.get(key)
        except Exception:
            pass
        self.set_power("on" if r.is_on else "standby")
        self.state.update(on=r.is_on, app=app_name_for(pkg),
                          app_key=app_key(pkg), package=pkg or None, volume=r.volume_info, title=title, channel=channel, thumb=thumb,
                          duration=duration, position=position, playing=playing, is_short=is_short, language=language,
                          player_state=player_state, can_seek=can_seek)

    async def adb_reachable(self):
        """Is network debugging switched on for this TV (and is the Mac's key set up)?"""
        if not os.path.exists(ADB_KEY):
            return False
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(self.ip, 5555), 1.5)
            writer.close()
            return True
        except Exception:
            return False

    async def screen_loop(self, rules, blocked):
        """Catches Shorts by looking at the TV screen: the TV does not report what YouTube is playing, but a
        Short has a distinctive portrait layout. Needs network debugging (ADB) on the TV."""
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(SCREEN_INTERVAL)
            try:
                s = self.state
                watching = (rules.cfg[self.id]["block_shorts"]["enabled"] and self.online and s["on"]
                            and s["app_key"] == "youtube" and not rules.parent_active(self.id)
                            and not rules.video_allowed(self.id, s["title"], s["channel"]))
                if not watching:
                    self.short_streak = 0
                    if time.time() >= self.adb_probe_at:                  # keep the "screen detection" status fresh
                        self.adb_probe_at = time.time() + 30
                        self.adb_ok = await self.adb_reachable()
                    continue
                png = await self.screen.screenshot()
                self.adb_ok = png is not None
                if png is None:
                    continue
                looks = await loop.run_in_executor(None, shorts_layout, png)
                self.short_streak = self.short_streak + 1 if looks else 0
                if self.short_streak >= 2 and time.time() >= self.cooldown:   # two looks in a row, not a transition
                    self.short_streak = 0
                    self.enforce("BACK", "YouTube Shorts", "seen on the TV screen", blocked)   # back into YouTube
            except Exception as e:
                log(self.id, "screen check failed:", repr(e))

    def session_key(self):
        s = self.state
        if not s["on"] or not s["app"] or s["app_key"] == "home" or s["app"] == "Screensaver":
            return None
        if s["app"] == "YouTube" and not s["title"]:
            return None          # browsing YouTube, nothing playing yet
        return (s["app"], s["title"], s["channel"])

    def live_entry(self):
        sess = self.session
        if not sess:
            return None
        return {**{k: v for k, v in sess.items() if k != "key"}, "end": None, "live": True,
                "watched": int(sess["watched"])}

    def close_session(self, rules):
        sess, self.session = self.session, None
        if sess and sess["watched"] >= MIN_SESSION_SECONDS:
            rules.record({**{k: v for k, v in sess.items() if k != "key"},
                          "end": datetime.datetime.now().isoformat(timespec="seconds"),
                          "watched": int(sess["watched"])})

    def track_session(self, rules, cfg, dt):
        s = self.state
        key = self.session_key() if cfg["history"]["enabled"] else None
        if self.session and self.session["key"] != key:
            self.close_session(rules)
        if key is None:
            return
        if self.session is None:
            self.session = {"key": key, "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "tv_id": self.id, "tv": self.name, "app": s["app"], "title": s["title"],
                            "channel": s["channel"], "watched": 0.0, "length": None, "language": None,
                            "thumb": None}
        sess = self.session
        # With playback info only count while playing; apps that report none count while open.
        if s["playing"] is True or (s["playing"] is None and s["duration"] is None):
            sess["watched"] += min(dt, 10)
        sess["length"] = int(s["duration"]) if s["duration"] else sess["length"]
        sess["language"] = s["language"] or sess["language"]
        sess["thumb"] = s["thumb"] or sess["thumb"]

    def enforce(self, key, reason, detail, blocked, cooldown=10, video=True):
        self.cooldown = time.time() + cooldown
        self.remote.send_key_command(key)
        self.record_block(reason, video)
        blocked.insert(0, {"n": next(BLOCK_COUNTER), "time": time.strftime("%H:%M:%S"), "tv": self.name,
                           "word": reason, "title": detail})
        del blocked[20:]
        log(self.id, f"RULE {reason}: {detail} -> {key}")

    def warn_ahead(self, rules, cfg, blocked, now=None):
        """A heads-up `warn_minutes` before the daily limit or bedtime cuts the TV off, and again at 1 minute.
        Each is given once a day; a TV switched on with 30 s left gets only the 1-minute one."""
        now = now or datetime.datetime.now()
        today = now.strftime("%Y-%m-%d")
        self.warned = {w for w in self.warned if w[0] >= today}
        for cutoff, secs in rules.cutoffs_near(self.id, now).items():
            # A bedtime just after midnight counts as the day it starts on, or midnight would repeat its warning.
            day = (now + datetime.timedelta(seconds=secs)).strftime("%Y-%m-%d") if cutoff == "bedtime" else today
            crossed = {m for m in (cfg["screen_time"]["warn_minutes"], 1) if secs <= m * 60}
            due = [m for m in crossed if (day, cutoff, m) not in self.warned]
            self.warned.update((day, cutoff, m) for m in crossed)
            if due:
                self.warn(cutoff, secs, blocked)

    def warn(self, cutoff, secs, blocked):
        """Shows the heads-up on the TV and sends it to the Mac (through the same feed as blocks)."""
        minutes = -(-secs // 60)
        text = f"{'Bedtime' if cutoff == 'bedtime' else 'Screen time is up'} in {minutes} minute{'s' if minutes > 1 else ''}"
        blocked.insert(0, {"n": next(BLOCK_COUNTER), "time": time.strftime("%H:%M:%S"), "tv": self.name,
                           "word": "warning", "title": text})
        del blocked[20:]
        log(self.id, f"WARN {cutoff}: {text}")
        try:
            asyncio.get_running_loop().create_task(self.show_on_tv(text))
        except RuntimeError:
            pass                     # no event loop (tests)

    async def show_on_tv(self, text):
        """Sends the heads-up to the TV over ADB as a notification, or a short screen off/on blink if the TV refuses
        it. Without ADB it is only shown on the Mac. A posted notification has default importance, so it is not
        a pop-up: whether a viewer sees it depends on the TV's software."""
        q = shlex.quote
        out = await self.screen.shell(f"cmd notification post -S bigtext -t {q('TV Remote')} tvremote {q(text)}")
        if out is None:
            log(self.id, "heads-up: no ADB on this TV, shown on the Mac only")
        elif "posting:" not in out:                     # the command prints this when it accepts the notification
            log(self.id, "heads-up: TV refused the notification, blinking the screen instead")
            await self.screen.shell("input keyevent KEYCODE_SLEEP; sleep 1; input keyevent KEYCODE_WAKEUP")

    def record_block(self, reason, video):
        """Puts the block in the history, with the video and the rule, so a parent can review it and allow it."""
        rules, s = self.rules, self.state
        if not rules or not rules.cfg[self.id]["history"]["enabled"]:
            return
        now = datetime.datetime.now().isoformat(timespec="seconds")
        reason = REASONS.get(reason, f"flagged word “{reason}” in the title")
        rules.record({"ts": now, "end": now, "tv_id": self.id, "tv": self.name, "app": s["app"] or "TV",
                      "title": s["title"] if video else None, "channel": s["channel"] if video else None,
                      "thumb": s["thumb"] if video else None, "watched": 0, "blocked": True, "reason": reason,
                      "can_allow": bool(video and s["title"])})

    def apply_rules(self, rules, blocked):
        s = self.state
        self.rules = rules
        now = time.time()
        dt, self.last_tick = now - self.last_tick, now
        if rules.parent_active(self.id):
            # Parent mode: nothing is enforced and nothing is recorded (no usage, no history, no blocks).
            self.session = None
            self.short_streak = 0
            self.blocked_title = None
            self.cooldown = 0.0
            return
        if s["on"] and s["app"] != "Screensaver" and dt < 10:      # the screensaver is not watching
            rules.add_usage(self.id, dt, package=s["package"] if s["app_key"] != "home" else None)

        cfg = rules.cfg[self.id]
        self.track_session(rules, cfg, dt)

        vc, vol = cfg["volume_cap"], s["volume"]
        if vc["enabled"] and s["on"] and vol and not vol.get("muted") and now >= self.vol_cooldown:
            over = vol["level"] - vc["max"]
            if over > 0:
                self.vol_cooldown = now + 3
                for _ in range(min(over, 15)):
                    self.remote.send_key_command("VOLUME_DOWN")
                log(self.id, f"volume {vol['level']} is over the cap of {vc['max']} -> lowering")

        if not s["on"] or now < self.cooldown:
            return
        # Bedtime and the daily limit switch the TV off; they repeat if it is turned back on.
        if cfg["bedtime"]["enabled"] and rules.in_bedtime(self.id):
            return self.enforce("POWER", "bedtime", "TV off during bedtime", blocked, cooldown=20, video=False)
        if rules.over_limit(self.id):
            minutes = cfg["screen_time"]["minutes"]
            return self.enforce("POWER", "daily limit", f"{minutes} min used today", blocked, cooldown=20, video=False)
        self.warn_ahead(rules, cfg, blocked)
        # A blocked app, or one past its own daily limit, is sent back to the TV's Home screen.
        pkg = s["package"]
        if rules.app_blocked(self.id, pkg):
            return self.enforce("HOME", "app blocked", f"{s['app']} is blocked", blocked, video=False)
        if rules.app_over_limit(self.id, pkg):
            minutes = rules.app_limit(self.id, pkg)
            return self.enforce("HOME", "app limit", f"{s['app']}: {minutes} min used today", blocked, video=False)

        title, channel = s["title"], s["channel"]
        # In YouTube a blocked video goes BACK to the YouTube screen it was picked from, not to the TV's Home.
        leave = "BACK" if s["app"] == "YouTube" else "HOME"
        if not title:
            self.blocked_title = None
            return
        if rules.video_allowed(self.id, title, channel):          # a parent allowed this one
            return
        # Adult content is checked for every app that reports what is playing, not only YouTube.
        if title != self.blocked_title and cfg["adult_filter"]["enabled"]:
            m = ADULT_PAT.search(f"{title} {channel or ''}")
            if m:
                self.blocked_title = title
                return self.enforce(leave, "adult content", f"{m.group(1)}: {title}", blocked)
        if s["app"] != "YouTube" or title == self.blocked_title:
            return
        if not rules.channel_allowed(self.id, channel):
            self.blocked_title = title
            return self.enforce(leave, "channel not allowed", f"{channel}: {title}", blocked)
        if rules.channel_blocked(self.id, channel):
            self.blocked_title = title
            return self.enforce(leave, "channel blocked", f"{channel}: {title}", blocked)
        # The screen check (needs network debugging) is more reliable than guessing from the title, so the
        # title-based verdict is only used on TVs where the screen check isn't available.
        if cfg["block_shorts"]["enabled"] and s["is_short"] and not self.adb_ok:
            self.blocked_title = title
            return self.enforce(leave, "YouTube Shorts", title, blocked)
        if cfg["title_filter"]["enabled"]:
            m = PAT.search(title)
            if m:
                self.blocked_title = title
                self.enforce(leave, m.group(1), title, blocked)


def build_app():
    tvs = {cfg["id"]: TV(cfg) for cfg in TVS}
    rules = Rules(DATA, list(tvs))
    blocked = []

    async def status(_):
        return web.json_response({"tvs": [t.snapshot() for t in tvs.values()],
                                  "filter": {"enabled": any(c["title_filter"]["enabled"] for c in rules.cfg.values()),
                                             "blocked": blocked},
                                  **rules.snapshot([e for e in (t.live_entry() for t in tvs.values()) if e]),
                                  "media": {"on": MEDIA["tv"] is not None,
                                            "tv": MEDIA["tv"].id if MEDIA["tv"] else None,
                                            "kind": MEDIA["kind"], "name": MEDIA["name"], "count": MEDIA["count"]},
                                  "platform": sys.platform, "features": {"camera": MAC_OS, "media": MAC_OS},
                                  "camera": {"on": CAM["proc"] is not None,
                                             "tv": CAM["tv"].id if CAM["tv"] else None}})

    def tv_of(body):
        tv = tvs.get(body.get("tv"))
        if tv is None or tv.remote is None or not tv.online:
            raise web.HTTPServiceUnavailable(text="TV not connected")
        return tv

    async def key(request):
        body = await request.json()
        tv_of(body).remote.send_key_command(str(body["key"]).upper())
        return web.json_response({"ok": True})

    async def launch(request):
        body = await request.json()
        pkg = body.get("package")
        if pkg is not None:                       # an app from the TV's own list
            if not isinstance(pkg, str) or not PACKAGE_RE.match(pkg):
                raise web.HTTPBadRequest(text="bad package name")
            tv = tv_of(body)
            out = await tv.screen.shell("monkey -p %s -c android.intent.category.LEANBACK_LAUNCHER 1" % pkg)
            if out is None or "No activities found" in out or "monkey aborted" in out:
                tv.remote.send_launch_app_command("market://launch?id=" + pkg)
            return web.json_response({"ok": True})
        link = APPS.get(body.get("app"))
        if link is None:
            raise web.HTTPBadRequest(text="unknown app")
        tv_of(body).remote.send_launch_app_command(link)
        return web.json_response({"ok": True})

    async def apps_list(request):
        tv = tv_of({"tv": request.query.get("tv")})
        apps = await installed_apps(tv)
        if apps is None:
            return web.json_response({"error": "Turn on network debugging on the TV to see its apps "
                                               "(Settings › Device Preferences › Developer options)"}, status=409)
        return web.json_response({"apps": apps})

    async def search(request):
        q = request.query.get("q", "").strip()
        if not q:
            return web.json_response([])
        try:
            return web.json_response(await yt_search(q))
        except Exception as e:
            log("search failed:", repr(e))
            raise web.HTTPBadGateway(text="search failed")

    async def app_search(request):
        body = await request.json()
        tv = tv_of(body)
        entry = SEARCH.get(tv.state["app_key"])
        q = str(body.get("q", "")).strip()
        if entry is None or not q:
            raise web.HTTPBadRequest(text="no searchable app open")
        tv.remote.send_launch_app_command(entry[1].format(q=urllib.parse.quote(q)))
        return web.json_response({"ok": True})

    async def type_text(request):
        body = await request.json()
        tv = tv_of(body)
        text = str(body.get("text", "")).strip()[:60]
        if not text:
            raise web.HTTPBadRequest(text="nothing to type")
        asyncio.create_task(type_keys(tv, text, bool(body.get("open_search")), bool(body.get("submit", True))))
        return web.json_response({"ok": True})

    async def media(request):
        body = await request.json()
        if not MAC_OS:
            raise web.HTTPNotImplemented(text="Playing files from this computer is only available on the Mac app")
        tv = tv_of(body)
        paths = [str(p) for p in body.get("paths", [])][:200]
        try:
            await media_start(tv, paths)
        except Exception as e:
            log("media failed:", repr(e))
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"ok": True})

    async def media_off(_):
        await media_stop()
        return web.json_response({"ok": True})

    async def parent(request):
        body = await request.json()
        tv_id = str(body.get("tv"))
        try:
            if body.get("on"):
                rules.set_parent(tv_id, body.get("minutes"))
                log(tv_id, "parent mode on", f"for {body.get('minutes')} min" if body.get("minutes") else "until ended")
            else:
                rules.end_parent(tv_id)
                log(tv_id, "parent mode off")
        except (ValueError, TypeError) as e:
            raise web.HTTPBadRequest(text=str(e))
        return web.json_response({"ok": True})

    async def volume(request):
        body = await request.json()
        tv = tv_of(body)
        vc = rules.cfg[tv.id]["volume_cap"]
        try:
            level, how = set_volume(tv, body.get("level"), vc["max"] if vc["enabled"] else None)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=409)
        return web.json_response({"ok": True, "level": level, "method": how})

    async def playback(request):
        body = await request.json()
        tv = tv_of(body)
        try:
            do_playback(tv, str(body.get("action")), body.get("position"), body.get("delta"))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=409)
        return web.json_response({"ok": True})

    async def wake(request):
        body = await request.json()
        tv = tvs.get(body.get("tv"))
        if tv is None:
            raise web.HTTPBadRequest(text="unknown TV")
        if tv.online and tv.state["on"]:
            return web.json_response({"ok": True, "method": "already on"})
        methods = []
        if tv.online and tv.remote is not None:                # screen off but still answering
            tv.remote.send_key_command("WAKEUP")
            methods.append("wake key")

            async def power_if_still_off():
                await asyncio.sleep(4)
                if tv.online and not tv.state["on"]:           # some TVs ignore WAKEUP; POWER toggles them on
                    tv.remote.send_key_command("POWER")
                    log(tv.id, "wake: still off, pressed POWER")
            asyncio.create_task(power_if_still_off())
        if tv.mac:                                             # asleep or off the network: Wake-on-LAN
            send_wol(tv.mac, tv.ip)
            methods.append("wake-on-lan")
        if not methods:
            return web.json_response({"error": "TV address unknown; it has to be seen on the network once"}, status=409)
        log(tv.id, "wake:", ", ".join(methods))
        return web.json_response({"ok": True, "method": ", ".join(methods)})

    async def play(request):
        body = await request.json()
        vid = str(body.get("id", ""))
        if not re.fullmatch(r"[\w-]{11}", vid):
            raise web.HTTPBadRequest(text="bad video id")
        tv_of(body).remote.send_launch_app_command(f"https://www.youtube.com/watch?v={vid}")
        return web.json_response({"ok": True})

    async def camera(request):
        body = await request.json()
        if body.get("on") and not MAC_OS:
            raise web.HTTPNotImplemented(text="Camera to TV is only available on the Mac app")
        if not body.get("on"):
            await camera_stop()
            return web.json_response({"ok": True})
        tv = tv_of(body)
        try:
            await camera_start(tv)
        except Exception as e:
            log("camera failed:", repr(e))
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"ok": True})

    async def set_rule(request):
        body = await request.json()
        try:
            rules.update(str(body.get("tv")), str(body.get("id")), body.get("config") or {})
        except (ValueError, TypeError) as e:
            raise web.HTTPBadRequest(text=str(e))
        return web.json_response({"ok": True})

    def live_sessions():
        return [e for e in (t.live_entry() for t in tvs.values()) if e]

    def tv_param(request):
        tv = request.query.get("tv")
        if tv not in tvs:
            raise web.HTTPBadRequest(text="unknown TV")
        return tv

    async def report(request):
        return web.json_response(rules.report(tv_param(request), live_sessions()))

    async def export(request):
        tv = request.query.get("tv")
        if tv and tv not in tvs:
            raise web.HTTPBadRequest(text="unknown TV")
        return web.Response(text=rules.csv_text(tv, live_sessions()), content_type="text/csv", charset="utf-8")

    async def allow_video(request):
        body = await request.json()
        try:
            rules.set_video_allowed(str(body.get("tv")), body.get("title"), body.get("channel"), bool(body.get("allow", True)))
        except (ValueError, TypeError) as e:
            raise web.HTTPBadRequest(text=str(e))
        return web.json_response({"ok": True})

    async def clear_history(request):
        body = await request.json()
        rules.clear_history(body.get("tv"))
        return web.json_response({"ok": True})

    pairing = {}

    def free_id(name):
        base = re.sub(r"[^a-z0-9]+", "", name.lower()) or "tv"
        tid, n = base, 2
        while tid in tvs:
            tid, n = f"{base}{n}", n + 1
        return tid

    async def discover(_):
        """Android/Google TVs advertising themselves on the network."""
        from zeroconf import ServiceBrowser, Zeroconf
        found = {}

        class L:
            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name, 2000)
                if info and info.parsed_addresses():
                    ip = info.parsed_addresses()[0]
                    found[ip] = {"ip": ip, "name": name.split(".")[0]}
            update_service = remove_service = lambda *a: None

        def scan():
            zc = Zeroconf()
            try:
                ServiceBrowser(zc, "_androidtvremote2._tcp.local.", L())
                time.sleep(3)
            finally:
                zc.close()

        async def sweep():
            """Fallback when the network blocks mDNS (common on Windows): look for the TV remote port on every address nearby."""
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                    u.connect(("8.8.8.8", 80))
                    mine = u.getsockname()[0]
            except OSError:
                return
            prefix = mine.rsplit(".", 1)[0]

            async def probe(ip):
                try:
                    _, w = await asyncio.wait_for(asyncio.open_connection(ip, 6466), 0.8)
                    w.close()
                    found.setdefault(ip, {"ip": ip, "name": "Android TV"})
                except Exception:
                    pass
            await asyncio.gather(*(probe(f"{prefix}.{i}") for i in range(1, 255) if f"{prefix}.{i}" != mine))

        await asyncio.get_running_loop().run_in_executor(None, scan)
        await sweep()
        paired = {t.ip for t in tvs.values()}
        return web.json_response([v for ip, v in found.items() if ip not in paired])

    async def pair_start(request):
        body = await request.json()
        ip = str(body.get("ip", "")).strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
            raise web.HTTPBadRequest(text="Enter the TV's IP address, like 192.168.1.20")
        if any(t.ip == ip for t in tvs.values()):
            raise web.HTTPBadRequest(text="That TV is already added")
        stem = os.path.join(DATA, "pending-" + ip.replace(".", "-"))
        r = AndroidTVRemote("TVRemote", stem + "-cert.pem", stem + "-key.pem", ip)
        try:
            await r.async_generate_cert_if_missing()
            info = await r.async_get_name_and_mac()
            await r.async_start_pairing()
        except Exception as e:
            raise web.HTTPBadGateway(text=f"Couldn't reach the TV: {e}")
        pairing.clear()
        pairing[ip] = {"remote": r, "stem": stem, "info": info, "name": str(body.get("name") or "").strip()}
        return web.json_response({"ok": True})

    async def pair_finish(request):
        body = await request.json()
        ip, code = str(body.get("ip", "")), str(body.get("code", "")).strip()
        p = pairing.get(ip)
        if not p:
            raise web.HTTPBadRequest(text="Start pairing first")
        r = p["remote"]
        try:
            await r.async_finish_pairing(code)
            info_name, mac = p["info"]
        except Exception as e:
            raise web.HTTPBadRequest(text=f"That code didn't work: {e}")
        name = p["name"] or info_name or "TV"
        tid = free_id(name)
        for kind in ("cert", "key"):
            os.replace(f"{p['stem']}-{kind}.pem", os.path.join(DATA, f"{tid}-{kind}.pem"))
        pairing.pop(ip, None)
        macs = load_macs(); macs[tid] = str(mac).lower().replace("-", ":")
        json.dump(macs, open(MAC_FILE, "w"))
        save_tvs([*(t for t in load_tvs() if t["id"] != tid), {"id": tid, "name": name, "ip": ip}])
        tv = TV({"id": tid, "name": name, "ip": ip})
        tvs[tid] = tv
        rules.add_tv(tid)
        app["tasks"].append(asyncio.create_task(tv.run(rules, blocked)))
        return web.json_response({"ok": True, "id": tid, "name": name})

    async def index(_):
        return web.FileResponse(os.path.join(WEB, "index.html"))

    async def start(app):
        app["tasks"] = [asyncio.create_task(t.run(rules, blocked)) for t in tvs.values()]

    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/discover", discover),
                    web.post("/pair/start", pair_start), web.post("/pair/finish", pair_finish),
                    web.get("/status", status), web.post("/key", key),
                    web.post("/launch", launch), web.get("/apps", apps_list), web.post("/rules", set_rule), web.post("/allow", allow_video),
                    web.post("/history/clear", clear_history),
                    web.get("/report", report), web.get("/export", export),
                    web.get("/search", search), web.post("/play", play), web.post("/camera", camera),
                    web.post("/appsearch", app_search), web.post("/type", type_text), web.post("/wake", wake), web.post("/playback", playback), web.post("/volume", volume), web.post("/parent", parent),
                    web.post("/media", media), web.post("/media/stop", media_off)])
    app.on_cleanup.append(lambda _: camera_stop())
    app.on_cleanup.append(lambda _: media_stop())
    app.on_startup.append(start)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=lambda *_: log("listening on 127.0.0.1:%d" % PORT))
