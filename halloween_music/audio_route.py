"""Resolve and select audio output for Bluetooth playback."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)

MPV_DEVICE_LINE = re.compile(r"^\s+'([^']+)'\s+\(([^)]+)\)\s*$")


def list_mpv_audio_devices() -> list[tuple[str, str]]:
    mpv = shutil.which("mpv")
    if not mpv:
        return []
    try:
        result = subprocess.run(
            [mpv, "--audio-device=help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("mpv --audio-device=help failed: %s", exc)
        return []

    text = result.stdout or result.stderr or ""
    devices: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = MPV_DEVICE_LINE.match(line)
        if match:
            devices.append((match.group(1), match.group(2)))
    return devices


def _address_tokens(address: str) -> set[str]:
    upper = address.upper().replace("-", ":")
    dashed = upper.replace(":", "-")
    return {upper, dashed, upper.replace(":", ""), dashed.replace("-", "")}


def mpv_device_for_address(address: str, poll_seconds: float = 8.0) -> str | None:
    """Find mpv coreaudio/avfoundation device id for a Bluetooth MAC address."""
    tokens = _address_tokens(address)
    deadline = time.time() + poll_seconds
    while time.time() < deadline:
        for device_id, _label in list_mpv_audio_devices():
            if device_id == "auto":
                continue
            normalized = device_id.upper().replace("-", ":")
            if any(token in normalized for token in tokens):
                if device_id.startswith("coreaudio/"):
                    return device_id
                if device_id.startswith("avfoundation/"):
                    # Prefer coreaudio when both exist
                    core = device_id.replace("avfoundation/", "coreaudio/", 1)
                    for did, _ in list_mpv_audio_devices():
                        if did == core:
                            return core
                    return device_id
        time.sleep(0.35)
    return None


def ensure_linux_default_sink(address: str) -> None:
    """Set Pulse/PipeWire default sink to the Bluetooth device (best effort)."""
    pactl = shutil.which("pactl")
    if not pactl:
        logger.debug("pactl not found; skipping default sink selection")
        return

    addr = address.upper().replace("-", "_").replace(":", "_")
    addr_compact = address.upper().replace("-", "").replace(":", "")

    try:
        result = subprocess.run(
            [pactl, "list", "sinks", "short"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("pactl list sinks failed: %s", exc)
        return

    sink_name: str | None = None
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[1]
        upper = name.upper()
        if "BLUEZ" in upper and (addr in upper or addr_compact in upper.replace("_", "")):
            sink_name = name
            break
        if addr.replace("_", "") in upper.replace("_", "").replace("-", ""):
            sink_name = name
            break

    if not sink_name:
        logger.warning("No Pulse/PipeWire sink found for Bluetooth address %s", address)
        return

    try:
        subprocess.run(
            [pactl, "set-default-sink", sink_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        logger.info("Set default audio sink to %s", sink_name)
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        logger.warning("Failed to set default sink %s: %s", sink_name, exc)
