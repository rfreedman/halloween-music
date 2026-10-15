"""Flask web UI and JSON API."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from halloween_music.bluetooth.monitor import BluetoothMonitor
from halloween_music.config import ConfigStore
from halloween_music.player import Player
from halloween_music.scheduler import Scheduler

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _now_playing_fields(player: Player) -> dict:
    info = player.current_now_playing()
    if not info:
        return {"track": None, "title": None, "album": None}
    return {
        "track": info["title"],
        "title": info["title"],
        "album": info["album"],
    }


def create_app(
    config: ConfigStore,
    player: Player,
    scheduler: Scheduler,
    bt_monitor: BluetoothMonitor,
) -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/status")
    def status():
        cfg = config.snapshot()
        bt = bt_monitor.status()
        return jsonify(
            {
                "playing": player.is_playing,
                **_now_playing_fields(player),
                "start": cfg.schedule.start,
                "stop": cfg.schedule.stop,
                "volume": player.get_volume(),
                "override": scheduler.manual_override,
                "audio_device": player.audio_device,
                "audio_error": scheduler.audio_error,
                "bluetooth": {
                    "connected": bt.connected,
                    "name": bt.name,
                    "address": bt.address,
                    "reconnecting": bt.reconnecting,
                    "last_error": bt.last_error,
                },
            }
        )

    @app.post("/api/play")
    def play_now():
        scheduler.manual_play()
        if not player.is_playing and scheduler.audio_error:
            return jsonify({"ok": False, "error": scheduler.audio_error}), 502
        return jsonify({"ok": True, "playing": player.is_playing})

    @app.post("/api/stop")
    def stop_now():
        scheduler.manual_stop()
        return jsonify({"ok": True, "playing": player.is_playing})

    @app.post("/api/skip")
    def skip_track():
        try:
            player.skip_next()
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify(
            {
                "ok": True,
                "playing": player.is_playing,
                **_now_playing_fields(player),
            }
        )

    @app.post("/api/schedule")
    def update_schedule():
        data = request.get_json(silent=True) or {}
        start = data.get("start")
        stop = data.get("stop")
        if not start or not stop:
            return jsonify({"error": "start and stop are required"}), 400
        try:
            cfg = config.update_schedule(str(start), str(stop))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        scheduler.wake()
        scheduler.evaluate_now()
        return jsonify({"start": cfg.schedule.start, "stop": cfg.schedule.stop})

    @app.post("/api/bluetooth")
    def update_bluetooth():
        data = request.get_json(silent=True) or {}
        address = data.get("device_address")
        if not address:
            return jsonify({"error": "device_address is required"}), 400
        old = config.snapshot().bluetooth.device_address
        try:
            cfg = config.update_bluetooth(
                str(address),
                str(data["device_name"]) if "device_name" in data else None,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        bt_monitor.switch_address(old, cfg.bluetooth.device_address)
        scheduler.wake()
        return jsonify(
            {
                "device_address": cfg.bluetooth.device_address,
                "device_name": cfg.bluetooth.device_name,
            }
        )

    @app.post("/api/volume")
    def update_volume():
        data = request.get_json(silent=True) or {}
        if "volume" not in data:
            return jsonify({"error": "volume is required"}), 400
        try:
            volume = int(data["volume"])
        except (TypeError, ValueError):
            return jsonify({"error": "volume must be an integer"}), 400
        volume = player.set_volume(volume)
        config.update_volume(volume)
        return jsonify({"volume": volume})

    @app.post("/api/bluetooth/reconnect")
    def reconnect_bluetooth():
        bt_monitor.request_reconnect()
        try:
            bt_monitor.connect_now()
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, "bluetooth": _bt_payload(bt_monitor)})

    return app


def _bt_payload(bt_monitor: BluetoothMonitor) -> dict:
    bt = bt_monitor.status()
    return {
        "connected": bt.connected,
        "name": bt.name,
        "address": bt.address,
        "reconnecting": bt.reconnecting,
        "last_error": bt.last_error,
    }
