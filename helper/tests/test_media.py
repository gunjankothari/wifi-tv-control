"""Needs ffmpeg. Plays real files through the media code against a fake TV, so no TV is touched."""
import asyncio, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aiohttp, tvd

d = tempfile.mkdtemp()
def ff(*args): subprocess.run([tvd.FFMPEG, "-v", "error", "-y", *args], check=True)
ff("-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=6", "-f", "lavfi", "-i", "sine=duration=6",
   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", f"{d}/direct.mp4")
ff("-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", f"{d}/convert.mkv")
for n, c in (("a", "red"), ("b", "blue")):
    ff("-f", "lavfi", "-i", f"color=c={c}:size=320x180", "-frames:v", "1", f"{d}/{n}.jpg")
open(f"{d}/notes.txt", "w").write("not media")

class MC:
    def __init__(self): self.played = []
    def play_media(self, url, mime, **kw): self.played.append((url, mime, kw))
    def block_until_active(self, timeout=0): pass
class Cast:
    def __init__(self): self.media_controller = MC(); self.quit = 0
    def quit_app(self): self.quit += 1

async def fetch(url, headers=None):
    async with aiohttp.ClientSession() as s, s.get(url, headers=headers) as r:
        return r.status, r.headers, await r.read()

async def main():
    assert tvd.media_kind("x.MP4") == "video" and tvd.media_kind("x.png") == "image" and tvd.media_kind("x.txt") is None
    assert await tvd.can_play_directly(f"{d}/direct.mp4") is True
    assert await tvd.can_play_directly(f"{d}/convert.mkv") is False

    tv = tvd.TV({"id": "t", "name": "T", "ip": "127.0.0.1"}); tv.cast = Cast()
    # 1. H.264 MP4 plays as it is, with seeking (Range requests) and CORS
    await tvd.media_start(tv, [f"{d}/direct.mp4"])
    url, mime, kw = tv.cast.media_controller.played[-1]
    assert mime == "video/mp4" and kw["stream_type"] == "BUFFERED" and tvd.MEDIA["tv"] is tv
    st, h, body = await fetch(url, {"Range": "bytes=0-99"})
    assert st == 206 and len(body) == 100 and h["Access-Control-Allow-Origin"] == "*"
    st, _, _ = await fetch(url.rsplit("/", 1)[0] + "/not-a-token"); assert st == 404   # only picked files are served
    await tvd.media_stop(); assert tvd.MEDIA["tv"] is None and tv.cast.quit == 1
    try: await fetch(url); raise SystemExit("server still up after stop")
    except aiohttp.ClientConnectionError: pass

    # 2. an MKV is converted to HLS on the fly
    await tvd.media_start(tv, [f"{d}/convert.mkv"])
    url, mime, _ = tv.cast.media_controller.played[-1]
    assert mime == "application/x-mpegURL" and url.endswith("/h/index.m3u8")
    st, _, body = await fetch(url); assert st == 200 and b"#EXTM3U" in body and b".ts" in body
    seg = url.rsplit("/", 1)[0] + "/" + [l for l in body.decode().splitlines() if l.endswith(".ts")][0]
    st, _, seg_body = await fetch(seg); assert st == 200 and seg_body[:1] == b"G"        # MPEG-TS sync byte
    await tvd.media_stop()

    # 3. photos become a slideshow; non-media files are ignored
    tvd.SLIDE_SECONDS = 1
    await tvd.media_start(tv, [f"{d}/a.jpg", f"{d}/b.jpg", f"{d}/notes.txt"])
    assert tvd.MEDIA["count"] == 2 and tvd.MEDIA["name"] == "2 photos" and tvd.MEDIA["kind"] == "image"
    await asyncio.sleep(2.6)
    urls = [p[0] for p in tv.cast.media_controller.played[-3:]]
    assert len(set(urls)) == 2 and all(p[1] == "image/jpeg" for p in tv.cast.media_controller.played[-3:])
    st, _, img = await fetch(urls[0]); assert st == 200 and img[:2] == b"\xff\xd8"          # a real JPEG
    await tvd.media_stop()

    # 4. bad input is rejected cleanly and leaves nothing running
    try: await tvd.media_start(tv, [f"{d}/notes.txt"]); raise SystemExit("accepted a text file")
    except RuntimeError as e: assert "no playable" in str(e)
    assert tvd.MEDIA["tv"] is None and tvd.MEDIA["runner"] is None
    # camera and media never run together
    tvd.CAM["proc"] = None
    print("all media tests passed")
asyncio.run(main())
