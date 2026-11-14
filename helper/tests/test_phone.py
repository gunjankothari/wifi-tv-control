"""Phone access checks: PIN login, tokens, rate limit and which callers may reach which routes. No TV or network needed."""
import asyncio, os, socket, stat, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import phone as ph

LAN, PUBLIC, LOOP = "192.168.1.50", "8.8.8.8", "127.0.0.1"

# --- the Phone class on its own ---------------------------------------------------------------------------------------
d = tempfile.mkdtemp()
now = [1000.0]
p = ph.Phone(d, clock=lambda: now[0])
assert p.enabled is False and len(p.pin) == 6 and p.pin.isdigit() and p.tokens == []      # off by default
assert stat.S_IMODE(os.stat(os.path.join(d, "phone.json")).st_mode) == 0o600
assert p.login(LAN, "nope") is None
t = p.login(LAN, p.pin)
assert t and p.token_ok(t) and not p.token_ok(t + "x") and not p.token_ok("") and not p.token_ok(None)
assert ph.Phone(d).tokens == [t]                                                        # survives a restart
p.new_pin()
assert not p.token_ok(t) and p.tokens == []                                             # a new PIN signs out every phone
for _ in range(ph.MAX_FAILS_PER_IP):
    assert p.login(LAN, "000000x") is None
try: p.login(LAN, p.pin); raise SystemExit("not rate limited")
except PermissionError: pass
assert p.login("192.168.1.51", p.pin)                                                   # other phones still get in
now[0] += ph.FAIL_WINDOW + 1
assert p.login(LAN, p.pin)                                                              # the lock wears off
for i in range(ph.MAX_FAILS_TOTAL):
    p.login(f"10.0.0.{i}", "bad")
try: p.login("10.0.1.1", p.pin); raise SystemExit("no overall limit")
except PermissionError: pass
for _ in range(ph.MAX_TOKENS + 5):
    now[0] += ph.FAIL_WINDOW + 1
    p.login(LAN, p.pin)
assert len(p.tokens) == ph.MAX_TOKENS
assert ph.is_private("10.1.2.3") and ph.is_private("fe80::1") and ph.is_private("::ffff:192.168.0.2")
assert not ph.is_private(PUBLIC) and not ph.is_private("::ffff:8.8.8.8") and not ph.is_private("junk")


# --- the checks on real HTTP requests ---------------------------------------------------------------------------------
@web.middleware
async def fake_remote(request, handler):          # test only: pretend the request came from another address
    return await handler(request.clone(remote=request.headers.get("X-Test-Remote", request.remote)))


async def main():
    phone = ph.Phone(tempfile.mkdtemp())
    changed = []
    async def on_change(): changed.append(phone.enabled)
    async def ok(_): return web.json_response({"ok": True})
    app = web.Application(middlewares=[fake_remote, phone.middleware()])
    app.add_routes(phone.routes(on_change))
    app.add_routes([web.get("/", ok), web.get("/status", ok), web.post("/key", ok), web.get("/manifest.json", ok)])
    async with TestClient(TestServer(app)) as c:
        async def st(method, path, remote=LOOP, **kw):
            headers = {"X-Test-Remote": remote, **kw.pop("headers", {})}
            async with c.request(method, path, headers=headers, **kw) as r:
                return r.status

        # access off: the computer works, nobody else gets anything
        assert await st("GET", "/status") == 200
        assert await st("GET", "/status", LAN) == 403
        assert await st("GET", "/", LAN) == 403
        assert await st("POST", "/login", LAN, json={"pin": phone.pin}) == 403
        assert await st("POST", "/phone", json={"enabled": True}) == 200 and changed == [True]

        # access on
        assert await st("GET", "/status") == 200                                       # loopback needs no PIN
        assert await st("GET", "/status", PUBLIC) == 403                               # never from outside the LAN
        assert await st("GET", "/status", LAN) == 401                                  # LAN without a token
        assert await st("POST", "/key", LAN, json={"key": "POWER"}) == 401
        assert await st("GET", "/", LAN) == 200 and await st("GET", "/manifest.json", LAN) == 200
        assert await st("GET", "/phone", LAN) == 403                                   # PIN and settings: computer only
        assert await st("POST", "/phone", LAN, json={"enabled": False}) == 403
        assert await st("POST", "/phone/pin", LAN) == 403
        assert phone.enabled and await st("GET", "/phone") == 200

        # wrong PIN, then right PIN
        assert await st("POST", "/login", LAN, json={"pin": "999999x"}) == 401
        assert await st("POST", "/login", LAN, data="not json") == 401
        c.session.cookie_jar.clear()
        async with c.post("/login", json={"pin": phone.pin}, headers={"X-Test-Remote": LAN}) as r:
            assert r.status == 200
            cookie = r.cookies[ph.COOKIE]
            assert cookie["httponly"] and cookie["samesite"] == "Strict"
            token = cookie.value
        assert phone.token_ok(token)
        assert await st("GET", "/status", LAN) == 200                                  # the cookie works
        c.session.cookie_jar.clear()
        assert await st("GET", "/status", LAN) == 401
        assert await st("GET", "/status", LAN, headers={ph.HEADER: token}) == 200      # so does the header
        assert await st("GET", "/status", LAN, headers={ph.HEADER: token[:-1]}) == 401
        assert await st("GET", "/status", PUBLIC, headers={ph.HEADER: token}) == 403   # a token doesn't open it to the internet

        # a new PIN signs the phone out
        assert await st("POST", "/phone/pin") == 200
        assert await st("GET", "/status", LAN, headers={ph.HEADER: token}) == 401

        # too many wrong PINs: 429, even with the right one
        for _ in range(ph.MAX_FAILS_PER_IP):
            assert await st("POST", "/login", "192.168.1.77", json={"pin": "bad"}) == 401
        assert await st("POST", "/login", "192.168.1.77", json={"pin": phone.pin}) == 429

        # switching off locks the phone out again
        assert await st("POST", "/phone", json={"enabled": False}) == 200 and changed == [True, False]
        assert await st("GET", "/status", LAN, headers={ph.HEADER: phone.login(LAN, phone.pin)}) == 403

    # the extra listener opens on the Wi-Fi address only while access is on (skipped without a network)
    ip = ph.lan_ip()
    if ip:
        with socket.socket() as s:
            s.bind((ip, 0)); port = s.getsockname()[1]
        runner = web.AppRunner(app); await runner.setup()
        await phone.start(runner, port)
        assert phone.site is None and phone.url() is None
        phone.enabled = True
        await phone.start(runner, port)
        assert phone.url() == f"http://{ip}:{port}/"
        await phone.start(runner, port)                                                 # rebinding twice is fine
        phone.enabled = False
        await phone.start(runner, port)
        assert phone.url() is None
        await runner.cleanup()
    print("all phone tests passed")

asyncio.run(main())
