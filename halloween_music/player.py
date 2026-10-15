"""mpv-backed audio player with JSON IPC."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class NowPlaying(TypedDict):
    title: str
    album: str | None


class Player:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._ipc_path: str | None = None
        self._volume = 70
        self._playlist_path: Path | None = None
        self._audio_device: str | None = None

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(
        self,
        playlist_path: Path,
        volume: int | None = None,
        audio_device: str | None = None,
    ) -> None:
        with self._lock:
            if volume is not None:
                self._volume = max(0, min(100, volume))
            self._audio_device = audio_device
            self._playlist_path = playlist_path.resolve()
            self._stop_unlocked()

            fd, ipc_path = tempfile.mkstemp(prefix="halloween-mpv-", suffix=".sock")
            os.close(fd)
            os.unlink(ipc_path)
            self._ipc_path = ipc_path

            cmd = [
                "mpv",
                "--no-video",
                "--really-quiet",
                f"--volume={self._volume}",
		f"--af=dynaudnorm=f=150:g=15",
                "--loop-playlist=inf",
                f"--input-ipc-server={ipc_path}",
            ]
            if audio_device:
                cmd.append(f"--audio-device={audio_device}")
            cmd.append(str(self._playlist_path))
            logger.info("Starting mpv: %s", " ".join(cmd))
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Give IPC socket a moment to appear
            deadline = time.time() + 3
            while time.time() < deadline:
                if Path(ipc_path).exists():
                    break
                time.sleep(0.05)

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                try:
                    self._command({"command": ["quit"]}, timeout=1.0)
                except Exception:
                    pass
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            self._proc = None
        if self._ipc_path:
            try:
                os.unlink(self._ipc_path)
            except OSError:
                pass
            self._ipc_path = None

    def set_volume(self, volume: int) -> int:
        volume = max(0, min(100, int(volume)))
        with self._lock:
            self._volume = volume
            if self.is_playing:
                self._command({"command": ["set_property", "volume", volume]})
            return self._volume

    def get_volume(self) -> int:
        with self._lock:
            if self.is_playing:
                result = self._command({"command": ["get_property", "volume"]})
                if result is not None and "data" in result:
                    try:
                        self._volume = int(float(result["data"]))
                    except (TypeError, ValueError):
                        pass
            return self._volume

    def current_now_playing(self) -> NowPlaying | None:
        with self._lock:
            return self._current_now_playing_unlocked()

    def current_track(self) -> str | None:
        info = self.current_now_playing()
        return info["title"] if info else None

    def _current_now_playing_unlocked(self) -> NowPlaying | None:
        if not self.is_playing:
            return None
        album = self._get_property_string("metadata/album")
        title = self._get_property_string("metadata/title")
        if not title:
            for prop in ("media-title", "filename", "path"):
                raw = self._get_property_string(prop)
                if raw:
                    title = Path(raw).name if prop == "path" else raw
                    break
        if not title:
            return None
        return NowPlaying(title=title, album=album)

    def _get_property_string(self, prop: str) -> str | None:
        result = self._command({"command": ["get_property", prop]})
        if result and result.get("error") == "success" and result.get("data"):
            data = result["data"]
            if isinstance(data, str) and data.strip():
                return data.strip()
        return None

    def skip_next(self) -> None:
        """Advance to the next playlist entry."""
        with self._lock:
            if not self.is_playing:
                raise RuntimeError("Not playing")
            result = self._command({"command": ["playlist-next"]})
            if not result or result.get("error") != "success":
                raise RuntimeError("Skip failed")

    def restart_if_playing(self, audio_device: str | None = None) -> None:
        """Restart playback with the same playlist (e.g. after BT reconnect)."""
        with self._lock:
            if self._playlist_path is None:
                return
            if not self.is_playing:
                return
            path = self._playlist_path
            volume = self._volume
            device = audio_device if audio_device is not None else self._audio_device
            self._stop_unlocked()
            # Release lock briefly by calling start which re-acquires
        self.start(path, volume, audio_device=device)

    @property
    def audio_device(self) -> str | None:
        with self._lock:
            return self._audio_device

    def _command(self, payload: dict, timeout: float = 1.5) -> dict | None:
        if not self._ipc_path or not Path(self._ipc_path).exists():
            return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(self._ipc_path)
                sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                chunks: list[bytes] = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if b"\n" in chunk:
                        break
                raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
                if not raw:
                    return None
                return json.loads(raw.split("\n", 1)[0])
        except (OSError, json.JSONDecodeError, TimeoutError) as exc:
            logger.debug("mpv IPC failed: %s", exc)
            return None
