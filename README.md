# iphone-control-toolkit

[![CI](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

English | [简体中文](README.zh-CN.md)

Let an AI agent operate a real iPhone plugged into a Linux machine.
No Mac, no paid Apple developer account, no jailbreak.

```
Claude Code / any MCP client
        │  MCP (stdio, via docker exec)
        ▼
┌──────────── Docker container on Linux ────────────┐
│  MCP server ── WebDriverAgent (primary)            │
│             └─ CoreDevice HID (fallback, iOS 27+)  │
│  supervisor: reconnects, restarts, re-signs        │
└───────────────────────┬────────────────────────────┘
                        │ USB
                     iPhone
```

## Features

- **See and touch the screen** — screenshots (with zoom), tap, swipe, long-press, type text (including Chinese), hardware buttons.
- **Work with UI elements** — read the element tree, tap buttons by name, launch and close apps, open URLs.
- **Two control paths** — WebDriverAgent does the work; if it is down, screenshots, taps, swipes and keys fall back to Apple's CoreDevice HID service (iOS 27+, no signing needed).
- **Runs unattended** — recovers from replugging, phone reboots, tunnel drops and WebDriverAgent crashes; re-signs WebDriverAgent with a free Apple ID before the 7-day profile expires.
- **Alerts** — Telegram or Bark notifications when re-signing fails, the phone goes offline, or a passcode is needed after a reboot.
- **Optional auto-unlock** — the phone can lock normally; the toolkit types your numeric passcode before acting. Every digit is verified, and a wrong passcode disables auto-unlock after one attempt.

## Requirements

| | |
|---|---|
| Host | Linux, Docker with Compose v2.24+ (tested on x86_64) |
| Phone | iOS 17+; the HID fallback needs iOS 27+ |
| Account | A free Apple ID (use a dedicated one, not your main account) |
| Cable | A USB cable that carries data, not a charge-only cable |

## Quick start

```bash
git clone https://github.com/Derrors/iphone-control-toolkit.git
cd iphone-control-toolkit
bin/iphonectl setup          # guided setup; safe to re-run
bin/iphonectl mcp install    # register with Claude Code
```

`setup` walks you through each step and skips the ones already done:

1. Build the image and start the container (first build compiles from source, ~5–10 min).
2. Pair: tap **Trust** on the phone.
3. Turn on Developer Mode (the phone reboots once).
4. Mount the developer disk image.
5. Sign in to your Apple ID (password and 2FA code are entered only in your terminal).
6. Register the phone, then sign and install WebDriverAgent.
7. On the phone, trust the developer in **Settings → General → VPN & Device Management**.

Then open a new Claude Code session and ask, for example:

> Open the Clock app, switch to the stopwatch, and show me a screenshot.

**Other MCP clients** — the server speaks stdio through `docker exec`; no network port is opened:

```json
{
  "mcpServers": {
    "iphone": {
      "command": "docker",
      "args": ["exec", "-i", "iphone-control-toolkit", "/opt/ictl/mcp-server.sh"]
    }
  }
}
```

## Everyday commands

| Command | What it does |
|---|---|
| `iphonectl status` | Container status and recent supervisor log |
| `iphonectl doctor` | Layer-by-layer health check with a fix for each failure |
| `iphonectl logs [name] [-f]` | Logs: `supervisor`, `wda`, `tunnel`, `resign`, `notify`, … |
| `iphonectl resign [--force]` | Re-sign WebDriverAgent if it expires soon (or now) |
| `iphonectl login` | Sign in to the Apple ID again when the session expires |
| `iphonectl notify-test` | Send a test notification |
| `iphonectl passcode set\|clear` | Turn auto-unlock on or off |
| `iphonectl help` | All commands |

## MCP tools

| Tool | Description |
|---|---|
| `iphone_status` | Connection, lock state, foreground app, screen size |
| `iphone_screenshot` | Screenshot scaled to points; pass `x/y/width/height` to zoom into a region |
| `iphone_list_elements` | Elements with text and their center coordinates |
| `iphone_tap` / `iphone_tap_element` | Tap by coordinates or by element name |
| `iphone_swipe` / `iphone_long_press` | Swipe, long-press |
| `iphone_type_text` | Type into the focused field |
| `iphone_press_button` | `home`, `volume_up`, `volume_down`, `lock` |
| `iphone_list_apps` / `iphone_launch_app` / `iphone_terminate_app` | Manage apps by name or bundle ID |
| `iphone_open_url` | Open a URL or URL scheme |

Screenshot pixels are tap coordinates, so the agent can tap what it sees.
Games, maps and video players draw their own UI and expose no element tree — use screenshots and coordinates there.

## Configuration

`setup` copies `.env.example` to `.env`. Everything has a default; the settings you are most likely to change:

| Setting | Purpose |
|---|---|
| `HTTP_PROXY`, `HTTPS_PROXY` | Proxy for Apple and GitHub, if you need one |
| `TG_BOT_TOKEN`, `TG_CHAT_ID` | Telegram notifications |
| `BARK_SERVER`, `BARK_KEY` | Bark notifications |
| `PUID`, `PGID` | Owner of the data directory (`id -u`, `id -g`) |

All state lives in `data/`: pairing records, the Apple ID session and signing key, certificates and the passcode. **Back it up, and never commit or share it.**

## Status

Early release. Tested only on an **iPhone 15 Pro Max with iOS 27.0.1** and an x86_64 Debian host.

- **Verified on a real device:** recovery after replugging and reboots, passcode-prompt alerts, all 13 MCP tools, the HID fallback, auto-unlock, re-signing.
- **Not yet verified end to end:** a fresh `setup` from scratch (each step was tested on its own), iOS 17–26, other models, arm64 hosts.

Please open an issue with the output of `iphonectl doctor` (remove your UDID first).

## Limitations

- One phone per host. Don't connect two instances to the same phone.
- Free Apple ID profiles last 7 days. Re-signing is automatic, but an expired Apple ID session needs `iphonectl login`.
- After the phone reboots, you must enter the passcode once on the phone to allow UI automation. iOS requires this.
- Elements hidden behind a popup may still be listed, because visibility is judged by position.

## Documentation

Detailed docs are currently in Chinese:
[Architecture](docs/architecture.md) · [Troubleshooting](docs/troubleshooting.md) · [Security](docs/security.md) · [Development](docs/development.md)

## Security and disclaimer

This toolkit can fully control your phone. WebDriverAgent has no authentication, so the toolkit only exposes it on `127.0.0.1`, and auto-unlock is off by default. See [docs/security.md](docs/security.md).

Not affiliated with Apple. Use it only with devices you own, and follow Apple's developer agreement and your local laws. An agent may tap payment, delete or send buttons — keep tool-call confirmation on in your MCP client.

## License

MIT for this project's code. The container image also includes upstream components under other licenses, including GPL-3.0 — see [THIRD_PARTY.md](THIRD_PARTY.md).
