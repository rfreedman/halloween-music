---
todos:
  - id: "route-mpv"
    content: "Route mpv to BT CoreAudio device on macOS; pactl default sink on Linux"
    status: completed
  - id: "manual-override"
    content: "Add scheduler play/stop override cleared on schedule boundary"
    status: completed
  - id: "api-ui"
    content: "Add /api/play,/api/stop and Start/Stop buttons; expose override in status"
    status: completed
isProject: false
---

# Fix Bluetooth audio routing + manual Start/Stop

Implemented: mpv `--audio-device` for macOS CoreAudio BT sinks, Linux `pactl` default sink, manual Start/Stop with schedule-boundary override reset, UI and API updates.
