# TV Remote mobile app (Expo)

An Expo app (TypeScript) for iOS, Android and the web. It is a thin wrapper around the phone page the helper already serves (`helper/web/index.html`): you enter the helper's address once, the app remembers it and shows that page. The PIN is entered on the page itself, exactly as in a phone browser.

## Before you start

1. On the computer, open TV Remote and switch on **Phone access**. It shows an address such as `192.168.1.20:8765` and a PIN.
2. Put the phone on the same Wi-Fi as the computer.
3. Install Node 20 or newer.

## Run

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go (Android) or the Camera app (iOS), or press `i` / `a` for a simulator, or `w` for the browser. Enter the address from step 1 (the port defaults to 8765 if you leave it out), then the PIN.

## Web export

```bash
npx expo export --platform web
```

The static site lands in `mobile/dist`. On the web the app does not embed the page: after checking that the helper answers, it opens the helper's address directly, because the helper's sign-in cookie only works on its own address. Serve the export over `http://` (for example `npx serve dist`); a browser blocks an `https://` page from checking a plain `http://` helper.

## Checks

```bash
npx tsc --noEmit
```

## Notes

- If the helper can't be reached, the app shows a message with **Try again** and **Change address**.
- The helper speaks plain HTTP on the local network, so `app.json` allows local cleartext traffic (iOS `NSAllowsLocalNetworking`, Android `usesCleartextTraffic`). These apply to standalone builds; Expo Go already allows it.
- Store builds (EAS) need a bundle identifier / package name in `app.json`; none is set yet.
