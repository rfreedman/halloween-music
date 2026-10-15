# Halloween Music

Scheduled Halloween playlist player that outputs to a Bluetooth speaker, with a simple local web UI.

Develop on macOS; run in production on a Raspberry Pi.

## Features

- Plays an `.m3u` playlist on a daily start/stop schedule
- Bluetooth connect + auto-reconnect while the schedule window is active
- Web UI: playback status, manual Start/Stop, album and song title (from file tags when available), editable schedule, volume, Bluetooth address + reconnect
- Schedule and Bluetooth address changes are saved to `config.yaml` and apply without restart
- **macOS:** mpv is told to use the Bluetooth speaker directly (`--audio-device=coreaudio/…`); connecting via `blueutil` alone does not switch system output

## Requirements

- Python 3.10+
- [mpv](https://mpv.io/)
- **macOS:** [blueutil](https://github.com/toy/blueutil) (`brew install blueutil`)
- **Raspberry Pi / Linux:** `bluez` (`bluetoothctl`), plus PulseAudio or PipeWire for A2DP

## Setup (Mac or Pi)

```bash
cd halloween-music
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml   # if needed
# Edit config.yaml: schedule, bluetooth.device_address, playlist path
# Edit playlist.m3u with paths to your audio files
```

Find a paired speaker address:

```bash
# macOS
blueutil --paired

# Raspberry Pi
bluetoothctl devices
```

Pair the speaker once on the Pi before relying on auto-connect:

```bash
bluetoothctl
power on
agent on
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
quit
```

## Run

```bash
source .venv/bin/activate
python main.py --config config.yaml
```

Open `http://localhost:8080` (or the Pi’s LAN IP on port 8080).

## Config

See `config.yaml.example`. Important keys:

| Key | Purpose |
|-----|---------|
| `schedule.start` / `schedule.stop` | Daily local-time window (`HH:MM`). If stop is earlier than start, the window crosses midnight. |
| `playlist` | Path to `.m3u` (relative to the config file’s directory) |
| `bluetooth.device_address` | Target speaker MAC |
| `bluetooth.poll_seconds` | How often to check the link while scheduled |
| `audio.volume` | Default mpv volume 0–100 |
| `web.host` / `web.port` | HTTP bind address |

There is no authentication; keep the UI on a trusted LAN.

## Raspberry Pi (systemd)

1. Copy the project to `/home/pi/halloween-music` (adjust user/paths as needed).
2. Create the venv and install requirements on the Pi.
3. Edit `deploy/halloween-music.service` if your paths differ.
4. Install and enable:

```bash
sudo cp deploy/halloween-music.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now halloween-music.service
sudo systemctl status halloween-music.service
```

## API

- `GET /api/status` — includes `title`, `album` (nullable), and `track` (same as `title`, for compatibility)
- `POST /api/schedule` — `{ "start": "17:00", "stop": "22:00" }`
- `POST /api/bluetooth` — `{ "device_address": "AA:BB:CC:DD:EE:FF" }`
- `POST /api/volume` — `{ "volume": 70 }`
- `POST /api/play` — manual start (overrides schedule until the next start/stop boundary)
- `POST /api/stop` — manual stop (overrides schedule until the next start/stop boundary)
- `POST /api/skip` — advance to the next playlist track (only while playing)
- `POST /api/bluetooth/reconnect`
