# PWA over Tauri/Electron for an app-like UI

## Context

Want a "native app" feel without breaking the single-binary, web-app thesis framing.

## Decision

Ship a PWA (manifest + service worker + icons via `vite-plugin-pwa`): installable,
standalone window, offline shell. No Tauri/Electron.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Tauri/Electron wrapper | True native window, tray | Second packaging path, Rust toolchain, "desktop app" vs "web app" |
| Browser app-mode (`--app=`) | One-line | No icon/install, not installable |

## Consequences

**Positive:** native feel, zero new toolchain, keeps web-app identity.
**Negative:** service worker needs a secure context — fine on localhost, degrades on LAN without a self-signed cert.
**Follow-ups:** optional self-signed cert for LAN install.

## Thesis link

Frontend completeness; UX polish.
