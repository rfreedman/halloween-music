(() => {
  const playState = document.getElementById("play-state");
  const overrideHint = document.getElementById("override-hint");
  const audioRoute = document.getElementById("audio-route");
  const albumEl = document.getElementById("album");
  const titleEl = document.getElementById("title");
  const startInput = document.getElementById("start");
  const stopInput = document.getElementById("stop");
  const volumeInput = document.getElementById("volume");
  const volumeValue = document.getElementById("volume-value");
  const btIndicator = document.getElementById("bt-indicator");
  const btName = document.getElementById("bt-name");
  const btState = document.getElementById("bt-state");
  const btError = document.getElementById("bt-error");
  const btAddress = document.getElementById("bt-address");
  const flash = document.getElementById("flash");
  const btnNext = document.getElementById("btn-next");

  let volumeTimer = null;
  let editingSchedule = false;
  let editingBluetooth = false;

  function showFlash(message, ok) {
    flash.hidden = false;
    flash.textContent = message;
    flash.className = "flash " + (ok ? "ok" : "err");
    clearTimeout(showFlash._t);
    showFlash._t = setTimeout(() => {
      flash.hidden = true;
    }, 3500);
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options && options.headers) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || res.statusText || "Request failed");
    }
    return data;
  }

  function applyNowPlaying(data) {
    const title = data.title || data.track;
    if (!data.playing) {
      albumEl.hidden = true;
      albumEl.textContent = "";
      titleEl.textContent = "—";
      return;
    }
    if (data.album) {
      albumEl.hidden = false;
      albumEl.textContent = data.album;
    } else {
      albumEl.hidden = true;
      albumEl.textContent = "";
    }
    titleEl.textContent = title || "Unknown track";
  }

  function applyStatus(data) {
    playState.textContent = data.playing ? "Playing" : "Stopped";
    playState.className = "state " + (data.playing ? "playing" : "stopped");
    applyNowPlaying(data);
    btnNext.disabled = !data.playing;

    if (data.override === "play") {
      overrideHint.hidden = false;
      overrideHint.textContent = "Manual play (schedule overridden)";
    } else if (data.override === "stop") {
      overrideHint.hidden = false;
      overrideHint.textContent = "Manual stop (schedule overridden)";
    } else {
      overrideHint.hidden = true;
      overrideHint.textContent = "";
    }

    const routeParts = [];
    if (data.audio_device) {
      routeParts.push("Output: " + data.audio_device);
    }
    if (data.audio_error) {
      routeParts.push(data.audio_error);
    }
    if (routeParts.length) {
      audioRoute.hidden = false;
      audioRoute.textContent = routeParts.join(" · ");
      audioRoute.className = "audio-route" + (data.audio_error ? " error" : "");
    } else {
      audioRoute.hidden = true;
      audioRoute.textContent = "";
    }

    if (!editingSchedule) {
      startInput.value = data.start || "";
      stopInput.value = data.stop || "";
    }

    if (document.activeElement !== volumeInput) {
      volumeInput.value = String(data.volume ?? 70);
      volumeValue.textContent = String(data.volume ?? 70);
    }

    const bt = data.bluetooth || {};
    btName.textContent = bt.name || "Speaker";
    if (!editingBluetooth && document.activeElement !== btAddress) {
      btAddress.value = bt.address || "";
    }

    btIndicator.className = "dot " + (
      bt.reconnecting ? "busy" : bt.connected ? "on" : "off"
    );
    if (bt.reconnecting) {
      btState.textContent = "Reconnecting…";
    } else if (bt.connected) {
      btState.textContent = "Connected to " + (bt.address || "device");
    } else {
      btState.textContent = "Disconnected";
    }

    if (bt.last_error) {
      btError.hidden = false;
      btError.textContent = bt.last_error;
    } else {
      btError.hidden = true;
      btError.textContent = "";
    }
  }

  async function refresh() {
    try {
      const data = await api("/api/status");
      applyStatus(data);
    } catch (err) {
      playState.textContent = "Offline";
      playState.className = "state stopped";
      albumEl.hidden = true;
      albumEl.textContent = "";
      titleEl.textContent = err.message;
      btnNext.disabled = true;
    }
  }

  document.getElementById("schedule-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    editingSchedule = false;
    try {
      await api("/api/schedule", {
        method: "POST",
        body: JSON.stringify({
          start: startInput.value,
          stop: stopInput.value,
        }),
      });
      showFlash("Schedule saved", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
    }
  });

  startInput.addEventListener("focus", () => { editingSchedule = true; });
  stopInput.addEventListener("focus", () => { editingSchedule = true; });
  startInput.addEventListener("blur", () => { editingSchedule = false; });
  stopInput.addEventListener("blur", () => { editingSchedule = false; });

  document.getElementById("bt-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    editingBluetooth = false;
    try {
      await api("/api/bluetooth", {
        method: "POST",
        body: JSON.stringify({ device_address: btAddress.value.trim() }),
      });
      showFlash("Bluetooth address saved", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
    }
  });

  btAddress.addEventListener("focus", () => { editingBluetooth = true; });
  btAddress.addEventListener("blur", () => { editingBluetooth = false; });

  volumeInput.addEventListener("input", () => {
    volumeValue.textContent = volumeInput.value;
    clearTimeout(volumeTimer);
    volumeTimer = setTimeout(async () => {
      try {
        await api("/api/volume", {
          method: "POST",
          body: JSON.stringify({ volume: Number(volumeInput.value) }),
        });
      } catch (err) {
        showFlash(err.message, false);
      }
    }, 200);
  });

  document.getElementById("btn-play").addEventListener("click", async () => {
    try {
      await api("/api/play", { method: "POST", body: "{}" });
      showFlash("Playback started", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
      await refresh();
    }
  });

  document.getElementById("btn-stop").addEventListener("click", async () => {
    try {
      await api("/api/stop", { method: "POST", body: "{}" });
      showFlash("Playback stopped", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
    }
  });

  btnNext.addEventListener("click", async () => {
    try {
      const data = await api("/api/skip", { method: "POST", body: "{}" });
      applyNowPlaying({ ...data, playing: true });
      showFlash("Skipped to next song", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
      await refresh();
    }
  });

  document.getElementById("bt-reconnect").addEventListener("click", async () => {
    try {
      await api("/api/bluetooth/reconnect", { method: "POST", body: "{}" });
      showFlash("Reconnect requested", true);
      await refresh();
    } catch (err) {
      showFlash(err.message, false);
      await refresh();
    }
  });

  refresh();
  setInterval(refresh, 2500);
})();
