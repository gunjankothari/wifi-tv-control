"""Phone access over Wi-Fi: an opt-in second listener on the computer's LAN address, protected by a PIN.

Requests from this computer (127.0.0.1) never need the PIN, so the Mac and Windows apps keep working.
Requests from the LAN are only served while phone access is on, only from private addresses, and only
with a token that the phone gets by entering the PIN. Tokens and the PIN are never written to the log.
"""
import ipaddress, json, os, secrets, socket, time

from aiohttp import web

COOKIE = "tvr_token"
HEADER = "X-TVRemote-Token"
# Reachable from the LAN without a token: the page itself (it shows the PIN screen), its install files and the login.
OPEN_PATHS = {"/", "/login", "/manifest.json", "/icon.svg"}
# Never reachable from the LAN, even with a token: the phone settings (they show the PIN) and casting files from
# this computer (it takes any file path, and no page uses it). Everything the app's pages offer, rules, parent
# mode, allow, history export/clear included, works from a signed-in phone too.
LOCAL_ONLY = {"/phone", "/phone/pin", "/media", "/media/stop"}
MAX_FAILS_PER_IP = 5
MAX_FAILS_TOTAL = 20
FAIL_WINDOW = 300            # seconds
MAX_TOKENS = 20              # oldest phone is signed out when a new one signs in past this


def new_pin():
    return f"{secrets.randbelow(10 ** 6):06d}"


def lan_ip():
    """The address this computer uses on the local network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.connect(("10.255.255.255", 1))
            ip = u.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def is_loopback(remote):
    try:
        return ipaddress.ip_address(remote or "").is_loopback
    except ValueError:
        return False


def is_private(remote):
    try:
        a = ipaddress.ip_address(remote or "")
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_private or a.is_link_local


class Phone:
    def __init__(self, data_dir, clock=time.monotonic):
        self.file = os.path.join(data_dir, "phone.json")
        self.clock = clock
        self.fails = {}              # ip -> [times of failed PIN attempts]
        self.site = None             # the LAN listener while it runs
        self.bound = None            # address it is bound to
        try:
            cfg = json.load(open(self.file))
        except Exception:
            cfg = {}
        self.enabled = bool(cfg.get("enabled", False))
        self.pin = str(cfg.get("pin") or new_pin())
        self.tokens = [str(t) for t in cfg.get("tokens", [])]
        self.save()

    def save(self):
        tmp = self.file + ".tmp"
        try:
            os.remove(tmp)                          # a leftover could have looser permissions; O_EXCL needs it gone
        except FileNotFoundError:
            pass
        # Created 0600 from the start, so the PIN is never readable by other users, not even briefly.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"enabled": self.enabled, "pin": self.pin, "tokens": self.tokens}, f)
        os.replace(tmp, self.file)

    def new_pin(self):
        """A new PIN signs out every phone."""
        self.pin, self.tokens = new_pin(), []
        self.save()

    def token_ok(self, token):
        if not token:
            return False
        ok = False
        for t in self.tokens:                       # compare against all, so timing doesn't reveal which matched
            ok |= secrets.compare_digest(t.encode(), str(token).encode())
        return ok

    def _recent(self, times):
        now = self.clock()
        return [t for t in times if now - t < FAIL_WINDOW]

    def locked(self, ip):
        self.fails = {k: v for k, v in ((k, self._recent(v)) for k, v in self.fails.items()) if v}
        total = sum(len(v) for v in self.fails.values())
        return len(self.fails.get(ip, [])) >= MAX_FAILS_PER_IP or total >= MAX_FAILS_TOTAL

    def login(self, ip, pin):
        """Returns a new token, or None for a wrong PIN. Raises PermissionError while too many attempts failed."""
        if self.locked(ip):
            raise PermissionError
        if not secrets.compare_digest(str(pin).strip().encode(), self.pin.encode()):
            self.fails.setdefault(ip, []).append(self.clock())
            return None
        self.fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        self.tokens = [*self.tokens, token][-MAX_TOKENS:]
        self.save()
        return token

    def url(self):
        return f"http://{self.bound}:{self.port}/" if self.site and self.bound else None

    def info(self):
        return {"enabled": self.enabled, "running": self.site is not None, "url": self.url(),
                "pin": self.pin, "phones": len(self.tokens), "ip": lan_ip()}

    # --- the LAN listener -------------------------------------------------------------------------------------------

    async def start(self, runner, port):
        self.port = port
        await self.stop()
        if not self.enabled:
            return
        ip = lan_ip()
        if not ip:
            return
        site = web.TCPSite(runner, ip, port)
        await site.start()
        self.site, self.bound = site, ip

    async def stop(self):
        if self.site:
            await self.site.stop()
        self.site = self.bound = None

    # --- request checks ---------------------------------------------------------------------------------------------

    def middleware(self):
        phone = self

        @web.middleware
        async def check(request, handler):
            remote = request.remote
            if is_loopback(remote):
                return await handler(request)
            if not phone.enabled or not is_private(remote):
                raise web.HTTPForbidden(text="Phone access is off")
            if request.path in LOCAL_ONLY:
                raise web.HTTPForbidden(text="Only available on the computer")
            if request.path in OPEN_PATHS:
                return await handler(request)
            token = request.cookies.get(COOKIE) or request.headers.get(HEADER)
            if not phone.token_ok(token):
                raise web.HTTPUnauthorized(text="Enter the PIN")
            return await handler(request)

        return check

    def routes(self, on_change):
        """Routes for the PIN login (phone) and the settings (computer only). on_change(): rebind after a toggle."""
        phone = self

        async def login(request):
            try:
                body = await request.json()
            except Exception:
                body = {}
            try:
                token = phone.login(request.remote, body.get("pin", ""))
            except PermissionError:
                raise web.HTTPTooManyRequests(text="Too many wrong PINs. Wait a few minutes and try again.")
            if not token:
                raise web.HTTPUnauthorized(text="Wrong PIN")
            resp = web.json_response({"ok": True})
            resp.set_cookie(COOKIE, token, max_age=365 * 24 * 3600, httponly=True, samesite="Strict")
            return resp

        async def get_settings(_):
            return web.json_response(phone.info())

        async def set_settings(request):
            body = await request.json()
            before = phone.enabled
            phone.enabled = bool(body.get("enabled"))
            phone.save()
            try:
                await on_change()
            except OSError as e:
                phone.enabled = before              # nothing is listening, so don't keep (or save) the new setting
                phone.save()
                return web.json_response({**phone.info(), "error": f"Couldn't open the Wi-Fi port: {e}"})
            return web.json_response(phone.info())

        async def change_pin(_):
            phone.new_pin()
            return web.json_response(phone.info())

        return [web.post("/login", login), web.get("/phone", get_settings),
                web.post("/phone", set_settings), web.post("/phone/pin", change_pin)]
