![Telegram Calls for Kodi](assets/banner.png)

# Telegram Calls for Kodi

**English** · [Deutsch](README.de.md)

**Make and take Telegram voice calls on the TV: a Kodi add-on for LibreELEC
that uses your own Telegram account, a USB webcam microphone and the AV
receiver, operated entirely with the remote.**

You can only be reached while the add-on is open. There is no background
service and no pop-up over other Kodi content.

> This add-on is an unofficial project and is not affiliated with Telegram.
> It uses [ntgcalls](https://github.com/pytgcalls/ntgcalls) /
> [py-tgcalls](https://github.com/pytgcalls/pytgcalls) for calls and
> [Telethon](https://github.com/LonamiWebs/Telethon) for the account.

---

## Status

| Part | State |
|---|---|
| 1. Feasibility test (call from the command line) | done |
| 2. One-to-one voice calls in the add-on | working, final acceptance test with real calls pending |
| 3. One-to-one video, full screen | planned |
| 4. Group calls | planned |

## Requirements

| | |
|---|---|
| Device | Raspberry Pi 5 (aarch64), tested. The bundled libraries are built for aarch64. |
| System | LibreELEC 12 with Kodi 21 "Omega" (Python 3.11) |
| Microphone | USB webcam with a microphone (tested: Logitech C922) |
| Audio out | HDMI, e.g. to an AV receiver |
| Telegram | your existing account and your own `api_id` / `api_hash` from <https://my.telegram.org> |

## Installation

There is no release zip yet. The add-on is built and copied from a Linux
development machine:

```
tools/build-bundle.sh            # downloads the aarch64 libraries into addon/…/vendor (about 220 MB)
tools/deploy.sh                  # copies the add-on to the box and enables it in Kodi
```

`tools/deploy.sh` copies to `root@192.168.178.10` by default; pass another
target as the second argument. It never touches the add-on's data folder
(session, favourites).

## First start

1. Enter `api_id` and `api_hash` in the add-on settings
   (**Add-ons → Program add-ons → Telegram-Anrufe → Settings**).
2. Open the add-on. On the first start it shows a QR code. Scan it in the
   official Telegram app under **Settings → Devices → Link Desktop Device**.
   Or choose **Log in with phone number**: Telegram sends a code to your app,
   and asks for your two-step verification password if you set one.

Scanning the QR code with an unofficial client (tested: Forkgram) failed with
"An error occurred"; logging in with the phone number works.

## Usage

- **Start screen:** your favourites as tiles, plus **All contacts**. OK on a
  tile calls that person.
- **All contacts:** alphabetical, groups at the end (group calls will come
  later). The context menu offers **Search …** and **Add to / Remove from
  favourites**. On the start screen, the context menu removes or moves a
  favourite.
- **During a call:** **Mute** and **Hang up**. Back and Stop also hang up.
  The volume is set on the receiver.
- **Incoming call:** a ringing dialog over every screen of the add-on. OK
  answers, Back declines. After 45 s the call counts as missed. A second
  call during a conversation is declined as busy.
- Anything Kodi is playing (e.g. Spotify) is paused when a call starts.
- Back on the start screen asks before closing; once closed, you cannot be
  reached.

## Settings

| Setting | Default | |
|---|---|---|
| api_id / api_hash | – | from my.telegram.org |
| Log out this device | – | logs the session out at Telegram and deletes it (close the add-on first) |
| Direct output when HDMI is free | off | plays the call straight to HDMI instead of through Kodi: about 0.35 s less delay, but Kodi's interface sounds stay silent until Kodi plays something again |
| Echo handling | WebRTC | WebRTC echo cancellation, duck microphone, or off |
| Microphone | `plughw:CARD=Webcam,DEV=0` | ALSA device (expert level) |

## How it works

```
Kodi add-on (Python in Kodi)          call process (system Python, own process)
  screens, remote control   ◀─ Unix socket, JSON lines ─▶  Telethon: login, contacts
  plays the call audio                                      ntgcalls: the call
       ▲                                                    webcam mic ─▶ echo cancellation ─▶ Telegram
       └──────── RTP 48 kHz + SDP file ◀────────────────── Telegram ─▶ audio out
```

- **Separate process:** ntgcalls is native code. If it crashes, the call
  ends, Kodi keeps running, and the add-on restarts the call process (at most
  three times a minute).
- **48 kHz only:** after an AV receiver is switched on, 44.1 kHz over HDMI can
  sound too high and crackle; ntgcalls 3.0.3 also crashes when receiving at
  44.1 kHz.
- **Audio through Kodi** by default: about 0.45 s from the network to the
  speakers on the test setup.
- **Echo cancellation** with the WebRTC audio processing from the
  [LiveKit](https://github.com/livekit/python-sdks) package. The speakers are
  heard by the webcam; the far-end audio is used as reference, delayed by the
  measured output delay.
- **PulseAudio is not used**: microphone and output go through ALSA, so other
  add-ons using PulseAudio (e.g. [Soloist](https://github.com/willheisenberg/kodi-soloist))
  are not affected.

## Privacy and security

- The Telegram session file (full access to the account) stays on the box,
  readable only by root, and is never copied by the tools.
- Phone number, login code and password are only passed on to Telegram and
  never stored or logged.
- The socket between add-on and call process is readable only by root and
  accepts a fixed list of commands.

## Troubleshooting

- `addon_data/script.telegram.calls/worker.log` is the log of the call
  process; `kodi.log` contains the add-on's messages with the prefix
  `script.telegram.calls:`.
- "No microphone": check that the webcam is connected. The C922 resets its
  ALSA control `Mic Capture Volume` to 0 when it is plugged in again; the
  call process sets it back to 10 of 15 by itself (`amixer -c Webcam`).
- `tools/wctl.py` controls the call process from the command line without
  Kodi (log in, list contacts, call, answer).

## Development

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q      # 151 tests, no Kodi or Telegram needed
.venv/bin/ruff check .
tools/make_icon.sh       # icon and banner from assets/*.svg (needs rsvg-convert)
```

The code has to stay compatible with Python 3.11 (LibreELEC 12). Design
documents and measurements are in `docs/` (German).

## License

Not chosen yet. The bundled libraries keep their own licences (ntgcalls and
py-tgcalls: LGPL-3.0, Telethon: MIT, LiveKit: Apache-2.0). The handset in the
icon is the "call" icon from Google's Material Icons (Apache-2.0).
