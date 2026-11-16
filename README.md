# TV Remote

Control the Android TV and Google TV sets in your home over Wi-Fi, from a Mac menu bar app or a Windows app. You can use it as a remote, open any installed app and search YouTube, from the computer or from a phone on the same Wi-Fi (PIN-protected). It also sets parental rules: a kid filter, channel allow and block lists, Shorts blocking, daily screen time, bedtime and a volume cap. It keeps a watch history that shows blocked videos.

**Feature overview:** https://gunjankothari.github.io/wifi-tv-control/ (the site lives in [`docs/`](docs/))

**Download:** [latest release](https://github.com/gunjankothari/wifi-tv-control/releases/latest) (Mac `.dmg`, Windows installer)

**Contribute:** TV Remote is open source. [Report an issue](https://github.com/gunjankothari/wifi-tv-control/issues), or fork the repo and open a [pull request](https://github.com/gunjankothari/wifi-tv-control/pulls).

## Project layout

| Path | What it is |
| --- | --- |
| `Sources/TVRemote` | Mac menu bar app (SwiftUI) |
| `helper` | Python helper that talks to the TVs, runs the rules and serves the local web UI |
| `windows` | Windows app: runs the helper and shows its UI in a native window |
| `mobile` | Expo app (iOS, Android, web) that shows the helper's phone page; see [`mobile/README.md`](mobile/README.md) |
| `build.sh` | Builds `TVRemote.app` (`./build.sh --bundle` includes the helper) |
| `.github/workflows/release.yml` | Builds and publishes the Mac and Windows installers on every push to `main` |

## Running the Mac app from source

The installed app (built with `./build.sh --bundle`) carries its own helper and keeps its data in `~/Library/Application Support/TVRemote`, so it needs no setup.

A development build (`./build.sh` or `swift run`) has no bundled helper. Instead it starts the Python helper from `helper/.venv` in your checkout. To tell it where your checkout is, set `TVREMOTE_HOME`:

```sh
cd helper && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
export TVREMOTE_HOME="$PWD"
swift run
```

Apps started from Finder or with `open` don't see shell variables. To use a `./build.sh` build that way, run `launchctl setenv TVREMOTE_HOME "$PWD"` once first.

If `TVREMOTE_HOME` is not set and no helper is bundled, the app shows an error asking you to set it. If a helper is already running on `127.0.0.1:8765`, the app uses that one and doesn't need the variable.
