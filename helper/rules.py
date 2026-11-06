"""Per-TV rule settings, daily TV usage and watch history for the TVRemote helper."""
import copy, csv, datetime, io, json, os, re, time

DEFAULTS = {
    "title_filter": {"enabled": True},
    "screen_time": {"enabled": False, "minutes": 120, "weekend_minutes": None},   # weekend None = same as weekdays
    "bedtime": {"enabled": False, "start": "21:00", "end": "07:00"},
    "allow_channels": {"enabled": False, "channels": []},
    "block_shorts": {"enabled": False},
    "adult_filter": {"enabled": True},
    "volume_cap": {"enabled": False, "max": 40},
    "block_channels": {"enabled": False, "channels": []},
    "history": {"enabled": True},
    "parent_schedule": {"enabled": False, "start": "18:00", "end": "19:00"},
    "allowed_videos": {"items": []},          # videos a parent chose to allow even though a rule blocks them
}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def minutes_of(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class Rules:
    def __init__(self, data_dir, tv_ids):
        self.dir = data_dir
        self.tv_ids = list(tv_ids)
        self.cfg = {t: copy.deepcopy(DEFAULTS) for t in self.tv_ids}
        self.usage = {}
        self.history = []
        self.parent_skip = {}             # tv id -> epoch seconds: a scheduled window that was ended early stays off until then
        self.parent = {}                  # tv id -> {"until": epoch seconds or None for no end}
        self._last_usage_save = 0.0
        self._load()

    def add_tv(self, tv_id):
        if tv_id not in self.cfg:
            self.tv_ids.append(tv_id)
            self.cfg[tv_id] = copy.deepcopy(DEFAULTS)
            self._save_cfg()

    # --- persistence -------------------------------------------------------
    def _path(self, name):
        return os.path.join(self.dir, name)

    def _merge(self, tv_id, saved):
        for rid, defaults in DEFAULTS.items():
            for k in defaults:
                if k in saved.get(rid, {}):
                    self.cfg[tv_id][rid][k] = saved[rid][k]

    def _load(self):
        try:
            saved = json.load(open(self._path("rules.json")))
            if "title_filter" in saved:           # earlier version: one rule set for every TV
                for t in self.tv_ids:
                    self._merge(t, saved)
            else:
                for t in self.tv_ids:
                    self._merge(t, saved.get(t, {}))
        except Exception:
            # carry over the old on/off switch for the title filter, if there is one
            try:
                on = bool(json.load(open(self._path("filter.json")))["enabled"])
                for t in self.tv_ids:
                    self.cfg[t]["title_filter"]["enabled"] = on
            except Exception:
                pass
        try:
            self.parent = {t: p for t, p in json.load(open(self._path("parent.json"))).items() if t in self.tv_ids}
        except Exception:
            self.parent = {}
        try:
            self.usage = json.load(open(self._path("usage.json")))
        except Exception:
            self.usage = {}
        try:
            with open(self._path("history.jsonl")) as f:
                self.history = [json.loads(line) for line in f if line.strip()][-5000:]
        except Exception:
            self.history = []

    def _save_cfg(self):
        json.dump(self.cfg, open(self._path("rules.json"), "w"), indent=1)

    # --- settings ----------------------------------------------------------
    def update(self, tv_id, rule_id, patch):
        if tv_id not in self.cfg:
            raise ValueError("unknown TV")
        if rule_id not in DEFAULTS:
            raise ValueError("unknown rule")
        cur = self.cfg[tv_id][rule_id]
        for k, v in patch.items():
            if k not in cur:
                continue
            if k == "enabled":
                cur[k] = bool(v)
            elif k == "minutes":
                cur[k] = max(15, min(720, int(v)))
            elif k == "weekend_minutes":                 # None: weekends use the weekday limit
                cur[k] = None if v is None else max(15, min(720, int(v)))
            elif k == "max":
                cur[k] = max(5, min(100, int(v)))
            elif k in ("start", "end"):
                if not isinstance(v, str) or not HHMM.match(v):
                    raise ValueError("time must be HH:MM")
                cur[k] = v
            elif k == "channels":
                seen, out = set(), []
                for c in v:
                    c = str(c).strip()
                    if c and c.lower() not in seen:
                        seen.add(c.lower())
                        out.append(c)
                cur[k] = out[:50]
        self._save_cfg()

    # --- parent mode -------------------------------------------------------
    def _save_parent(self):
        json.dump(self.parent, open(self._path("parent.json"), "w"))

    def set_parent(self, tv_id, minutes=None, now=None):
        """Starts parent mode on a TV: no rules, no restrictions, no tracking. `minutes` None = until ended."""
        if tv_id not in self.cfg:
            raise ValueError("unknown TV")
        if minutes is not None:
            minutes = max(5, min(1440, int(minutes)))
        self.parent[tv_id] = {"until": (now or time.time()) + minutes * 60 if minutes else None}
        self._save_parent()

    def _drop_parent(self, tv_id):
        if self.parent.pop(tv_id, None) is not None:
            self._save_parent()

    def end_parent(self, tv_id, now=None):
        """Ends parent mode, including a scheduled window that is running right now."""
        self._drop_parent(tv_id)
        end = self._window_end(tv_id, now)
        if end:
            self.parent_skip[tv_id] = end

    def _window_end(self, tv_id, now=None):
        """Epoch seconds when today's scheduled parent window ends, or None when not inside one."""
        s = self.cfg[tv_id]["parent_schedule"]
        start, end = minutes_of(s["start"]), minutes_of(s["end"])
        if not s["enabled"] or start == end:
            return None
        now = now or time.time()
        dt = datetime.datetime.fromtimestamp(now)
        t = dt.hour * 60 + dt.minute
        inside = start <= t < end if start < end else (t >= start or t < end)
        if not inside:
            return None
        day = dt.date() + datetime.timedelta(days=1 if start > end and t >= start else 0)
        return datetime.datetime.combine(day, datetime.time(end // 60, end % 60)).timestamp()

    def _scheduled_end(self, tv_id, now):
        end = self._window_end(tv_id, now)
        return end if end and now >= self.parent_skip.get(tv_id, 0) else None

    def parent_active(self, tv_id, now=None):
        now = now or time.time()
        p = self.parent.get(tv_id)
        if p:
            if p["until"] is None or now < p["until"]:
                return True
            self._drop_parent(tv_id)
        return self._scheduled_end(tv_id, now) is not None

    def parent_snapshot(self, now=None):
        now = now or time.time()
        out = {}
        for t in self.tv_ids:
            active = self.parent_active(t, now)
            if t in self.parent:
                until, scheduled = self.parent[t]["until"], False
            else:
                until, scheduled = (self._scheduled_end(t, now) if active else None), active
            out[t] = {"active": active, "scheduled": scheduled and active,
                      "seconds_left": max(0, int(until - now)) if until else None}
        return out

    # --- bedtime -----------------------------------------------------------
    def in_bedtime(self, tv_id, now=None):
        b = self.cfg[tv_id]["bedtime"]
        now = now or datetime.datetime.now()
        t = now.hour * 60 + now.minute
        start, end = minutes_of(b["start"]), minutes_of(b["end"])
        if start == end:
            return False
        return start <= t < end if start < end else (t >= start or t < end)

    # --- daily usage -------------------------------------------------------
    @staticmethod
    def _today(now=None):
        return (now or datetime.datetime.now()).strftime("%Y-%m-%d")

    def _save_usage(self):
        self._last_usage_save = time.time()
        for old in sorted(self.usage)[:-14]:
            del self.usage[old]
        json.dump(self.usage, open(self._path("usage.json"), "w"))

    def add_usage(self, tv_id, seconds, now=None):
        day = self.usage.setdefault(self._today(now), {})
        day[tv_id] = day.get(tv_id, 0) + seconds
        if time.time() - self._last_usage_save > 30:
            self._save_usage()

    def used(self, tv_id, now=None):
        return int(self.usage.get(self._today(now), {}).get(tv_id, 0))

    # --- today's limit: weekday or weekend value, plus any bonus granted for today --
    def add_bonus(self, tv_id, minutes, now=None):
        """Grants extra screen time for today only; tomorrow the normal limit applies again. Returns today's total bonus."""
        if tv_id not in self.cfg:
            raise ValueError("unknown TV")
        minutes = int(minutes)
        if not 1 <= minutes <= 240:
            raise ValueError("bonus must be between 1 and 240 minutes")
        day = self.usage.setdefault(self._today(now), {})
        bonus = day.setdefault("bonus", {})            # usage.json: day -> "bonus" -> tv -> minutes
        bonus[tv_id] = bonus.get(tv_id, 0) + minutes
        self._save_usage()
        return bonus[tv_id]

    def bonus(self, tv_id, now=None):
        """Extra minutes granted for today."""
        return int(self.usage.get(self._today(now), {}).get("bonus", {}).get(tv_id, 0))

    def base_limit(self, tv_id, now=None):
        """The configured limit for today: the weekend value on Saturday and Sunday when one is set."""
        st = self.cfg[tv_id]["screen_time"]
        weekend = (now or datetime.datetime.now()).weekday() >= 5
        return st["weekend_minutes"] if weekend and st["weekend_minutes"] is not None else st["minutes"]

    def limit_minutes(self, tv_id, now=None):
        return self.base_limit(tv_id, now) + self.bonus(tv_id, now)

    def over_limit(self, tv_id, now=None):
        st = self.cfg[tv_id]["screen_time"]
        return st["enabled"] and self.used(tv_id, now) >= self.limit_minutes(tv_id, now) * 60

    # --- YouTube channel allow list ---------------------------------------
    def channel_allowed(self, tv_id, channel):
        a = self.cfg[tv_id]["allow_channels"]
        if not a["enabled"] or not a["channels"] or not channel:
            return True
        return any(c.lower() in channel.lower() for c in a["channels"])

    # --- YouTube restricted channels ----------------------------------------
    def channel_blocked(self, tv_id, channel):
        b = self.cfg[tv_id]["block_channels"]
        if not b["enabled"] or not b["channels"] or not channel:
            return False
        return any(c.lower() in channel.lower() for c in b["channels"])

    # --- videos a parent allowed ---------------------------------------------
    @staticmethod
    def _same_video(item, title, channel):
        return (item["title"].lower() == (title or "").lower()
                and (item.get("channel") or "").lower() == (channel or "").lower())

    def video_allowed(self, tv_id, title, channel):
        if not title:
            return False
        return any(self._same_video(i, title, channel) for i in self.cfg[tv_id]["allowed_videos"]["items"])

    def set_video_allowed(self, tv_id, title, channel, allowed=True):
        if tv_id not in self.cfg:
            raise ValueError("unknown TV")
        if not title:
            raise ValueError("no title")
        items = [i for i in self.cfg[tv_id]["allowed_videos"]["items"] if not self._same_video(i, title, channel)]
        if allowed:
            items.append({"title": title, "channel": channel or None})
        self.cfg[tv_id]["allowed_videos"]["items"] = items[-200:]
        self._save_cfg()

    # --- history -----------------------------------------------------------
    def record(self, entry):
        entry = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **entry}
        self.history.append(entry)
        del self.history[:-5000]
        with open(self._path("history.jsonl"), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def clear_history(self, tv_id=None):
        self.history = [e for e in self.history if tv_id and e.get("tv_id") != tv_id]
        if self.history:
            with open(self._path("history.jsonl"), "w") as f:
                f.writelines(json.dumps(e) + "\n" for e in self.history)
        else:
            try:
                os.remove(self._path("history.jsonl"))
            except FileNotFoundError:
                pass

    # --- summaries ---------------------------------------------------------
    def today_summary(self, live):
        """Watch time today per TV, split by app and by channel (finished sessions plus live ones)."""
        day = self._today()
        out = {t: {"apps": {}, "channels": {}, "plays": 0} for t in self.tv_ids}
        for e in self.history + live:
            if not str(e.get("ts", "")).startswith(day) or e.get("tv_id") not in out:
                continue
            secs = int(e.get("watched") or 0)
            if secs <= 0:
                continue
            d = out[e["tv_id"]]
            d["apps"][e["app"]] = d["apps"].get(e["app"], 0) + secs
            if e.get("channel"):
                d["channels"][e["channel"]] = d["channels"].get(e["channel"], 0) + secs
            d["plays"] += 1
        return out

    # --- weekly report and export ------------------------------------------
    def report(self, tv_id, live=(), days=7):
        """Play time and session time per day for the last `days` days, plus top apps and channels."""
        today = datetime.date.today()
        entries = [e for e in self.history + list(live) if e.get("tv_id") == tv_id]
        out, apps_total, chans_total = [], {}, {}
        for i in range(days - 1, -1, -1):
            d = today - datetime.timedelta(days=i)
            key = d.isoformat()
            apps, chans = {}, {}
            for e in entries:
                secs = int(e.get("watched") or 0)
                if secs <= 0 or not str(e.get("ts", "")).startswith(key):
                    continue
                apps[e["app"]] = apps.get(e["app"], 0) + secs
                apps_total[e["app"]] = apps_total.get(e["app"], 0) + secs
                if e.get("channel"):
                    chans[e["channel"]] = chans.get(e["channel"], 0) + secs
                    chans_total[e["channel"]] = chans_total.get(e["channel"], 0) + secs
            out.append({"date": key, "label": d.strftime("%a"), "play": sum(apps.values()),
                        "session": int(self.usage.get(key, {}).get(tv_id, 0)), "apps": apps, "channels": chans})
        top = lambda m: [{"name": k, "secs": v} for k, v in sorted(m.items(), key=lambda kv: -kv[1])[:5]]
        return {"days": out, "top_apps": top(apps_total), "top_channels": top(chans_total),
                "total_play": sum(x["play"] for x in out), "total_session": sum(x["session"] for x in out)}

    def csv_text(self, tv_id=None, live=()):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Start", "End", "TV", "App", "Title", "Channel", "Watched (min)", "Watched (sec)",
                    "Video length (min)", "Audio language", "Blocked because"])
        for e in sorted(self.history + list(live), key=lambda x: x.get("ts", "")):
            if tv_id and e.get("tv_id") != tv_id:
                continue
            ts, end = str(e.get("ts", "")), e.get("end")
            watched = int(e.get("watched") or 0)
            length = e.get("length")
            w.writerow([ts[:10], ts[11:16], end[11:16] if end else ("playing now" if e.get("live") else ""), e.get("tv", ""), e.get("app", ""),
                        e.get("title") or "", e.get("channel") or "", round(watched / 60, 1), watched,
                        round(length / 60, 1) if length else "", e.get("language") or "", e.get("reason") or ""])
        return buf.getvalue()

    # --- API view ----------------------------------------------------------
    def snapshot(self, live=()):
        live = list(live)
        return {"rules": self.cfg,
                "usage": {t: self.used(t) for t in self.tv_ids},
                "limit": {t: self.limit_minutes(t) for t in self.tv_ids},     # today's limit in minutes, bonus included
                "bonus": {t: self.bonus(t) for t in self.tv_ids},
                "today": self.today_summary(live),
                "parent": self.parent_snapshot(),
                "history": live + [self._annotate(e) for e in reversed(self.history[-200:])]}

    def _annotate(self, e):
        """A blocked entry also says whether the parent has since allowed that video."""
        if e.get("blocked") and e.get("tv_id") in self.cfg:
            return {**e, "allowed": self.video_allowed(e["tv_id"], e.get("title"), e.get("channel"))}
        return e
