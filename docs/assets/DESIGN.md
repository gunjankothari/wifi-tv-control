# TV Remote site: design direction (TVR-32 / TVR-33)

These notes are for the Developer who builds the page. Every asset is in `docs/assets/`. The page stays static: no frameworks, no web fonts, no CDN. Keep IPs and home paths out of the page and the assets (TVR-27).

## Palette
Reuse the tokens that already exist in `docs/style.css`. Do not add new colours.

| Token | Dark | Use |
|---|---|---|
| bg | `#0b0d12` | page |
| panel / panel-2 | `#141821` / `#1b2030` | cards, demo frames |
| line | `#262c3d` | borders |
| text / muted | `#e8ebf2` / `#9aa3b8` | body / secondary (both pass AA on bg and panel) |
| accent | `#5b8cff` → `#a46bff` gradient | buttons, active tab, highlights |
| green / red | `#3ccf91` / `#ff5d6c` | live / connected, blocked / power |

The light-mode overrides in `style.css` still apply to the page chrome. The mockups and parallax layers are dark artwork by design, so show them on a `panel` card with a 20–24px radius in both themes.

## Type
Use the system stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
- Hero h1: `clamp(2.4rem, 5vw, 4rem)`, weight 800, letter-spacing -0.02em
- h2: `clamp(1.8rem, 3.5vw, 2.6rem)`, weight 750
- h3: 1.05rem, weight 650
- Body: 1rem / 1.6, muted for descriptions

Spacing follows an 8px grid. Sections get 128px vertical padding on desktop and 80px on mobile.

## Hero and parallax
Stack these layers in a `position: sticky` or `fixed` hero, from back to front:

| Layer | File | Scroll speed |
|---|---|---|
| 1 | `layer-back.svg` (glow, stars) | 0.2× |
| 2 | `layer-mid.svg` (wifi rings) | 0.5× |
| 3 | `hero-tv.svg` (TV with "Blocked by Kid filter" tile) | 0.8× |
| 4 | `layer-front.svg` (floating chips) | 1.2× |

- Move the layers with `transform: translate3d(0, y, 0)` inside a single `requestAnimationFrame` scroll handler. Do not animate `top` or `background-position`.
- Add a light parallax (0.9×) to each section's demo frame, plus a fade/slide-in that `IntersectionObserver` triggers once.
- Under `prefers-reduced-motion: reduce`, drop all parallax and reveal animations, show the layers static, and make demos change state instantly.

## One interactive demo per section
Each demo sits next to its card grid on desktop (text 5 columns, demo 7 columns) and stacks below the text on mobile.

1. **Remote** (`mock-mac-remote.svg` next to `hero-tv.svg`): make the D-pad, OK, volume and app chips clickable. Use transparent `<button>` hotspots over an inline SVG, or inline the SVG and add handlers to its groups. The D-pad moves the focus ring between the TV tiles, the volume buttons show a "Vol 18" toast on the TV, and the app chips swap the TV header text (YouTube / Netflix / Prime Video).
2. **Phone** (`mock-phone-pin.svg` → `mock-phone.svg`): six digits type in one by one at about 180ms each, Connect pulses, then the screen cross-fades to the remote. Add a "Replay" button.
3. **Rules** (`mock-rules.svg`): the toggles are live. Turning on Kid filter or Block Shorts puts the red "Blocked by …" overlay on a tile in a small TV preview (reuse `hero-tv.svg`). Dragging the screen-time bar changes "78 of 120 min".
4. **History** (`mock-history.svg`): the All / Blocked only pills filter the rows. "Allow" turns the blocked row green with an "Allowed" label.
5. **Platforms**: a Mac / Windows segmented switch that highlights the matching column of the existing feature table.

Every hotspot must be a real `<button>` with an `aria-label` and a visible focus ring (2px accent outline). Demos must work by keyboard.

## Icons
`icons.svg` is a sprite of 24px, 2px-stroke icons drawn in `currentColor`. Use them like this:
`<svg class="ico" aria-hidden="true"><use href="assets/icons.svg#i-wifi"/></svg>`.
Put each icon on a 40px rounded tile with a 15% tint of the accent colour, and draw the icon in `#a46bff` or the text colour.

| Card | Emoji | Icon id |
|---|---|---|
| Find and pair TVs | 📡 | i-wifi |
| Several TVs | 📺 | i-tvs |
| Power and wake | ⏻ | i-power |
| D-pad, Back and Home | 🕹️ | i-dpad |
| Volume | 🔊 | i-volume |
| Now playing | ⏯️ | i-playing |
| Open any installed app | 🧩 | i-apps |
| Search and type | 🔎 | i-search |
| Show my camera | 📷 | i-camera |
| Play from this Mac | 🎞️ | i-file-play |
| Switch it on, then open the link | 📲 | i-phone (or i-qr) |
| Protected by a PIN | 🔢 | i-pin |
| Made for thumbs | 👆 | i-thumb |
| Stays at home | 🏠 | i-home |
| Kid filter | 🧒 | i-kid |
| Adult content filter | 🚫 | i-adult |
| Allowed YouTube channels | ✅ | i-allow |
| Restricted YouTube channels | ⛔ | i-restrict |
| Block YouTube Shorts | 📱 | i-shorts |
| Daily screen time | ⏳ | i-timer |
| Bedtime | 🌙 | i-moon |
| Volume cap | 🔉 | i-volcap |
| Parent mode | 🧑‍🍼 | i-parent |
| Alerts | 🔔 | i-bell |
| Sessions | 🗂️ | i-sessions |
| Today at a glance | 📊 | i-today |
| Weekly report | 📈 | i-weekly |
| Blocked videos | 🛡️ | i-blocked |
| Allow a video | 👍 | i-allow-video |
| Open in the browser | 🌐 | i-browser |
| Export and clear | 📤 | i-export |

## Logo, favicon and social card
- `logo-mark.svg` is the gradient TV-with-play mark. Use it in the nav at 28px. `logo-mono.svg` uses `currentColor` and is for the footer and light contexts.
- Add these tags to `<head>`:
```html
<link rel="icon" type="image/svg+xml" href="assets/logo-mark.svg">
<link rel="icon" type="image/png" sizes="32x32" href="assets/icon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="assets/icon-180.png">
<link rel="icon" type="image/png" sizes="192x192" href="assets/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="assets/icon-512.png">
<meta property="og:image" content="https://<pages-host>/TVRemote/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
```
`og:image` must be an absolute URL. Fill in the GitHub Pages host.

## Mobile (≤ 760px)
- The hero uses only `layer-back` and `hero-tv` (the TV at 100% width). Hide `layer-mid` and `layer-front`.
- Each demo goes below its text. Show the phone mockups at about 280px wide, centred. The rules and history mockups go full width.
- Hotspots must be at least 44×44px. Do not let the demos scroll sideways.

## Notes
- The mockups are faithful SVG recreations of the real UI, not screenshots. `mock-phone*.svg` follow the tokens in `helper/web/index.html`. They use live `<text>` in the system font, so the type can differ slightly between macOS and Windows.
- Re-export the PNGs with headless Chrome, for example:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 --force-device-scale-factor=1 --window-size=W,H --screenshot=OUT file://SVG`
