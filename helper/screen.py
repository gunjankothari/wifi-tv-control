"""Screen-based YouTube Shorts detection over ADB (network debugging).

The TV's own data does not say what YouTube is playing, but a Short has a distinctive look: a tall 9:16 frame
with flat dark margins and a side panel, instead of a picture filling the screen. `shorts_layout` recognises that
from a screenshot, and `AdbScreen` takes the screenshot.
"""
import asyncio, base64, io, os, time
from PIL import Image, ImageStat

THUMB = (192, 108)


def _column_std(im):
    w, h = im.size
    y0, y1 = int(h * 0.05), int(h * 0.95)
    return [ImageStat.Stat(im.crop((x, y0, x + 1, y1))).stddev[0] for x in range(w)]


def frame_run(stds, busy=30.0):
    """(start, end) of the longest run of columns busy enough to be video content."""
    best, cur_start = (0, 0), None
    for x, s in enumerate(list(stds) + [0.0]):
        if s > busy and cur_start is None:
            cur_start = x
        elif s <= busy and cur_start is not None:
            if x - cur_start > best[1] - best[0]:
                best = (cur_start, x)
            cur_start = None
    return best


EDGE_SIZE = (480, 270)


def frame_edges(im):
    """x positions (centres) of the vertical edges that run through nearly the whole screen height."""
    w, h = im.size
    data = im.tobytes()
    y0, y1 = int(h * 0.08), int(h * 0.92)
    rows = y1 - y0
    strong = [x for x in range(2, w - 2)
              if sum(1 for y in range(y0, y1) if abs(data[y * w + x + 2] - data[y * w + x - 2]) > 18) >= rows * 0.85]
    clusters = []
    for x in strong:
        if clusters and x - clusters[-1][-1] <= 3:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [(c[0] + c[-1]) / 2 for c in clusters]


def has_portrait_frame(png):
    """The Shorts player's rounded 9:16 frame: two full-height edges about 32% of the width apart. It shows
    even while the video inside is still black."""
    try:
        im = Image.open(io.BytesIO(png)).convert("L").resize(EDGE_SIZE)
    except Exception:
        return False
    edges = frame_edges(im)
    w = im.size[0]
    if len(edges) > 4:          # a Short frame gives two edges; a busy picture gives many by chance
        return False
    return any(0.28 <= (b - a) / w <= 0.37 for i, a in enumerate(edges) for b in edges[i + 1:])


def shorts_layout(png):
    """True when the screenshot shows a portrait Short: a 9:16 frame (about 32% of the width at full height)
    surrounded by flat margins, rather than a picture that fills the screen."""
    if has_portrait_frame(png):
        return True
    try:
        im = Image.open(io.BytesIO(png)).convert("L").resize(THUMB)
    except Exception:
        return False
    stds = _column_std(im)
    start, end = frame_run(stds)
    width = (end - start) / im.size[0]
    if not 0.24 <= width <= 0.40:
        return False
    outside = sorted(s for x, s in enumerate(stds) if not start - 2 <= x <= end + 2)
    if not outside:
        return False
    flat_outside = outside[len(outside) // 2] < 20          # median column outside the frame is flat
    return flat_outside and sum(stds[start:end]) / (end - start) > 35


class AdbScreen:
    """Takes screenshots of a TV over ADB, reconnecting when needed and backing off when ADB is off."""

    def __init__(self, ip, key_path):
        self.ip, self.key_path = ip, key_path
        self.dev = None
        self.retry_at = 0.0
        self.reported = False

    async def _connect(self):
        from adb_shell.adb_device_async import AdbDeviceTcpAsync
        from adb_shell.auth.sign_pythonrsa import PythonRSASigner
        signer = PythonRSASigner(open(self.key_path + ".pub").read(), open(self.key_path).read())
        dev = AdbDeviceTcpAsync(self.ip, 5555, default_transport_timeout_s=15.0)
        await asyncio.wait_for(dev.connect(rsa_keys=[signer], auth_timeout_s=10), 20)
        self.dev = dev

    async def close_app(self, package):
        """Force-stops an app so it starts fresh next time (otherwise YouTube reopens on the last Short)."""
        if time.time() < self.retry_at or not os.path.exists(self.key_path):
            return False
        try:
            if self.dev is None:
                await self._connect()
            await asyncio.wait_for(self.dev.shell(f"am force-stop {package}"), 15)
            return True
        except Exception:
            self.dev = None
            self.retry_at = time.time() + 60
            return False

    async def screenshot(self):
        """PNG bytes of the TV screen, or None when ADB isn't available right now."""
        if time.time() < self.retry_at or not os.path.exists(self.key_path):
            return None
        try:
            if self.dev is None:
                await self._connect()
            out = await asyncio.wait_for(self.dev.shell("screencap -p | base64", read_timeout_s=30), 40)
            return base64.b64decode("".join(out.split()))
        except Exception:
            self.dev = None
            self.retry_at = time.time() + 60          # ADB is off, the TV is asleep, or the key was refused
            return None
