"""macOS Bluetooth via blueutil."""

from __future__ import annotations

import logging
import shutil
import subprocess

from halloween_music.audio_route import mpv_device_for_address
from halloween_music.bluetooth.base import BluetoothAdapter

logger = logging.getLogger(__name__)


class MacOSBluetooth(BluetoothAdapter):
    def __init__(self) -> None:
        self._bin = shutil.which("blueutil")
        if not self._bin:
            logger.warning("blueutil not found; Bluetooth control will fail on macOS")

    def _run(self, *args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
        if not self._bin:
            raise RuntimeError("blueutil is not installed (brew install blueutil)")
        return subprocess.run(
            [self._bin, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def is_connected(self, address: str) -> bool:
        result = self._run("--is-connected", address, timeout=10)
        return result.stdout.strip() == "1"

    def connect(self, address: str) -> None:
        result = self._run("--connect", address, timeout=45)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "connect failed").strip()
            raise RuntimeError(err)
        if not self.is_connected(address):
            raise RuntimeError(f"Bluetooth device {address} did not connect")

    def disconnect(self, address: str) -> None:
        result = self._run("--disconnect", address, timeout=20)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "disconnect failed").strip()
            logger.warning("Disconnect %s: %s", address, err)

    def ensure_audio_route(self, address: str, name: str | None = None) -> str | None:
        device = mpv_device_for_address(address)
        if not device:
            label = name or address
            raise RuntimeError(
                f"Bluetooth speaker '{label}' is not available as an mpv audio output. "
                "Ensure the device is connected and A2DP is active."
            )
        logger.info("Using mpv audio device %s for %s", device, address)
        return device
