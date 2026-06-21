# smart-vent mobile app — spec

> **Status: deferred / reference only.** As of v1, smart-vent vents
> commission via the Home Assistant Companion app out of the box —
> client scans the QR sticker on each vent, picks a room, done. A
> custom branded app duplicates the HA app's commissioning flow
> without adding engineering value; the only reasons to build one
> are branding or a streamlined onboarding UX for non-technical
> clients. This document remains as the contract a future
> branded-app effort would target. The companion contract document
> [`mobile-api.md`](mobile-api.md) is useful regardless — it
> describes what any integration (custom app, automation script,
> third-party tool) would talk to.

The smart-vent mobile app, **if built**, would be the
**client-facing** half of the deployment plan (workstream 6). It
would live in a separate Flutter repo (`smart-vent-app`, not in this
repo); this document defines what it needs to do. The API contract
it would build against is in [`mobile-api.md`](mobile-api.md).

## Audience + scope

The app is for the **end client**, not the provider. The provider
uses `smart-vent-provision` to prep kits; the client uses the app
to turn a freshly delivered kit into a working installation.

The app handles three things:

1. Pair the phone to the user's hub (mDNS discovery + HA token).
2. Add each vent to the user's home: scan QR sticker, the hub
   commissions it, the user picks a room.
3. Day-2: a thin "control my vents" surface so a user can open/
   close a vent without opening HA. (HA is still available; we just
   want one-tap control for non-techy users.)

Anything more complex than that — automations, advanced configuration,
multi-user sharing — happens in HA's own app. We don't reimplement
HA.

## Why Flutter + WS-API approach

The phone **does not** run a Matter SDK. The Pi does. Concretely:

- The phone is on the home WiFi.
- The Pi has BLE and 802.15.4 radios; it's the Matter controller.
- The app sends JSON to `ws://<hub>:5580/ws` and HA's REST.

This was the major decision documented in the design plan
(workstream 6.1). The trade-off: the Pi must be within BLE range
(~10 m) of each vent during commissioning. That's fine because OTBR
needs the Pi central in the house anyway.

Flutter is the single-codebase choice (Android + iOS); no platform
forks.

## Screen-by-screen flow

### Screen 0 — Welcome / discovery

- Logo, "Get started" button.
- On tap, browse mDNS for `_smart-vent._tcp.local.`.
- If one hub found, auto-select it. If multiple, list them with
  TXT-record version. If none, "Enter hub address" manual input.
- "Where do I find this?" link → kit-card photo with the AP
  SSID/password shown.

### Screen 1 — HA token

- "We need to connect to your hub" panel.
- "Sign in to Home Assistant" button → opens HA's OAuth flow in a
  WebView at `http://<hub>:8123/auth/authorize?...`.
- On callback, store the long-lived access token in
  keychain/keystore. Verify with a `GET /api/` ping.

### Screen 2 — Home

After auth, the home screen shows:

- A list of already-commissioned vents (from `get_nodes` →
  filter for WindowCovering), grouped by HA Area.
- Per vent: name, room, current position (% open), open/close
  buttons.
- Floating "+" button → **Add a vent** (Screen 3).
- Top-right gear → settings (re-auth, change hub, factory reset).

### Screen 3 — Add a vent

- "Point at the sticker" camera viewport.
- Auto-detect Matter QR (the `MT:...` prefix). Once detected:
  vibrate, show a "Pair this vent?" confirmation with the last 4
  of the EUI (from the sticker).
- On confirm: full-screen progress card. Streams matter-server's
  WS events:
  1. "Connecting over Bluetooth…" (PASE)
  2. "Sending Thread credentials…" (push)
  3. "Confirming…" (CASE)
- On failure: show the error code from
  [`mobile-api.md`](mobile-api.md#commission_with_code) verbatim
  + a one-line plain-English explanation + "Try again" button.
- On success: → Screen 4.

### Screen 4 — Place this vent

- "Which room is this vent in?"
- Picker reads existing HA Areas. Below the picker: "+ New room"
  → name input, optional Floor picker (or "+ New floor").
- "Optional: give this vent a name" text field. Defaults to the
  next-free `<room>-vent-<n>` slot.
- Continue → calls HA WS:
  1. Create the Area + Floor if needed
  2. Set the cover entity's `area_id`
  3. Rename the entity to `cover.<room>_vent_<n>` (slugified)
- → Screen 5.

### Screen 5 — Test the vent

- "Let's make sure it works." Big "Open" + "Close" buttons.
- On tap: `device_command` to the WindowCovering cluster. Watch
  for the position attribute to update; show the new position.
- "Done" button → back to Home (Screen 2) with the new vent
  listed.

### Screen 6 — Per-vent control (from Home, tap a vent)

- Cover entity name + room.
- Big position slider (0-100%).
- "Open", "Close", "Set to 50%" quick buttons.
- "Rename" / "Move to another room" / "Remove vent" overflow menu.
- "Identify" button → calls Matter Identify cluster, vent wiggles.

### Screen 7 — Settings

- Hub: name, version (from mDNS TXT), "Switch hub" button.
- Account: HA user email, "Sign out" (clears token).
- About: app version, contract version, link to docs.
- "Factory reset" — clears the keychain entry and returns to
  Screen 0.

## State-management notes (for the implementer)

- Cache `get_nodes` for ~30s; refresh on focus.
- Stream live position updates via matter-server's subscription
  mechanism (`start_listening` then attribute-changed events) for
  the Home screen and per-vent screen.
- WS reconnection: exponential backoff, max 60s. Show a
  non-blocking "Reconnecting…" banner; don't gate the UI.
- Token refresh: HA's long-lived token doesn't expire (by design).
  No refresh dance needed.

## Branding hooks

Provider can ship a white-labeled build by overriding:

- `assets/logo.svg`
- `lib/theme.dart` — primary color, accent, dark variant
- `strings.arb` — support email, app name

These are pulled at build time from `--dart-define` flags so the
same CI workflow produces both a default build and per-provider
builds.

## Out of scope (for v1)

- Multi-fabric / Apple Home commissioning. Matter spec supports
  multi-admin handoff; we punt it to v2.
- In-app firmware updates for vents. OTA needs the Matter
  OTAProvider cluster which we don't ship yet.
- iPad / tablet-specific layouts. Phone-first for v1.
- Notifications (filter clean reminders etc.). v2 once we figure
  out a sensor strategy.

## Build + ship

- iOS: TestFlight for beta, App Store for GA. Apple developer
  account is the provider's responsibility.
- Android: GitHub Releases for `.apk` sideloads, Play Store for GA.
- Same versioning scheme as the rest of the project (`app-vX.Y.Z`).

## Contract changes

If the hub side (matter-server commands, HA WS messages, mDNS TXT
shape) needs to change in a way that breaks older app builds, the
hub bumps its `_smart-vent._tcp.local.` TXT `version` field to a
new major. The app shows a "your hub is newer than this app, please
update" screen and refuses to commission. Provider then ships an
app update.
