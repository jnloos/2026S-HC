(function () {
  "use strict";

  // --- DOM handles ---------------------------------------------------------
  const stage = document.getElementById("stage");
  const pip = document.getElementById("pip");
  const placeholder = document.getElementById("placeholder");
  const placeholderHint = document.getElementById("placeholder-hint");
  const contentFrame = document.getElementById("content-frame");
  const toast = document.getElementById("reasoning-toast");
  const detectList = document.getElementById("detect-list");
  const audienceGroupEl = document.getElementById("audience-group");
  const canvas = document.getElementById("preview-canvas");
  const ctx = canvas.getContext("2d");

  // Debug panel handles.
  const dbgPanel = document.getElementById("debug-panel");
  const dbgRuns = document.getElementById("dbg-runs");
  const dbgDecision = document.getElementById("dbg-decision");
  const dbgLog = document.getElementById("dbg-log");
  const dbgConfig = document.getElementById("dbg-config");
  const chipVariant = document.getElementById("chip-variant");
  const dotCms = document.getElementById("dot-cms");
  const dotLlm = document.getElementById("dot-llm");
  const dotCam = document.getElementById("dot-cam");
  const camFpsEl = document.getElementById("cam-fps");

  // --- State ---------------------------------------------------------------
  let debugEnabled = false;
  let lastFrameTs = 0;
  // Latest recognized audience (per-face age/gender boxes + scene target group),
  // pushed by the face classifier each pipeline cycle. Replaces the old YoloX
  // "person" detections in the preview overlay.
  let latestAudience = emptyAudience();
  function emptyAudience() {
    return { faces: [], target_group: null, people_count: 0, frame_w: 0, frame_h: 0 };
  }
  // Id of the content currently shown — lets us ignore re-broadcasts of the
  // same content (sent so late-joining tabs catch up) without re-rendering.
  let currentContentId = null;

  // Live camera frame. When a new JPEG data-URL arrives we set frameImg.src;
  // once decoded, onload paints it to the canvas and overlays the boxes.
  const frameImg = new Image();
  frameImg.onload = () => {
    ctx.drawImage(frameImg, 0, 0, canvas.width, canvas.height);
    drawAudience(latestAudience);
  };

  // --- Socket.IO -----------------------------------------------------------
  // The Web UI Brick bundles socket.io; the `io()` constructor connects to
  // the same host that served the page.
  const socket = io();

  socket.on("connect", () => {
    placeholderHint.textContent = "connected — waiting for trigger…";
  });

  socket.on("disconnect", () => {
    placeholderHint.textContent = "disconnected — retrying…";
  });

  socket.on("config", (payload) => {
    debugEnabled = !!payload?.debug;
    if (debugEnabled) {
      pip.classList.remove("hidden");
    } else {
      pip.classList.add("hidden");
      dbgPanel.classList.add("hidden");
      // If we were in swapped state and debug just got turned off, unswap so
      // the user can still see the content.
      stage.classList.remove("swapped");
    }
    placeholderHint.textContent =
      `trigger=${payload?.trigger_mode ?? "?"} · pool=${payload?.pool_id ?? "?"}` +
      (debugEnabled ? " · debug" : "");
  });

  socket.on("content_update", (payload) => {
    const content = payload?.content ?? {};
    const html = content.html || "";
    if (!html) {
      showToast("empty content payload");
      return;
    }
    // Skip re-broadcasts of the content we're already showing (no flicker, no
    // repeated toast). A real new selection has a different id.
    if (content.id != null && content.id === currentContentId) return;
    currentContentId = content.id ?? null;
    placeholder.classList.add("hidden");
    contentFrame.classList.remove("hidden");
    contentFrame.srcdoc = html;
    if (content.reasoning) {
      showToast(content.reasoning, 6000);
    }
  });

  socket.on("pipeline_error", (payload) => {
    showToast("⚠ " + (payload?.message || "pipeline error"), 8000);
  });

  socket.on("debug_detection", (payload) => {
    if (!debugEnabled) return;
    // Carries the live camera frame only. The demographic overlay (per-face
    // age/gender + target group) is driven separately by the "audience" event.
    lastFrameTs = performance.now();
    if (payload?.frame) {
      recordFrameForFps();
      // Setting src triggers frameImg.onload, which paints the frame + audience.
      frameImg.src = payload.frame;
    } else {
      drawPlaceholder();
      drawAudience(latestAudience);
    }
  });

  // --- PiP swap (WhatsApp-style) ------------------------------------------
  // Click the SMALL thumbnail (wherever it is) to bring it to the front —
  // "tap where you want to go". The full-screen view is inert, so a stray click
  // on the big content/camera doesn't swap.
  const mainEl = document.getElementById("main");
  const isSwapped = () => stage.classList.contains("swapped");
  const swap = () => stage.classList.toggle("swapped");
  // #pip (camera) is the thumbnail only when NOT swapped.
  pip.addEventListener("click", () => { if (!isSwapped()) swap(); });
  pip.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && !isSwapped()) {
      e.preventDefault();
      swap();
    }
  });
  // #main (signage) is the thumbnail only when swapped (camera open).
  mainEl.addEventListener("click", () => { if (isSwapped()) swap(); });

  // --- 16:9 TV fit ---------------------------------------------------------
  // The signage iframe renders at a fixed 1280x720 ("TV canvas") and is scaled
  // to fit its host frame via --tv-scale, so the content always keeps TV
  // proportions and never reflows or shows scrollbars.
  const TV_W = 1280;
  const TV_H = 720;
  function fitTv() {
    const r = mainEl.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    contentFrame.style.setProperty("--tv-scale", String(Math.min(r.width / TV_W, r.height / TV_H)));
  }
  // One observer covers every case the host frame resizes: initial layout,
  // window resize, and each frame of the 0.35s swap animation.
  new ResizeObserver(fitTv).observe(mainEl);
  contentFrame.addEventListener("load", fitTv);

  // --- Toast --------------------------------------------------------------
  let toastTimer = null;
  function showToast(text, ms = 4500) {
    toast.textContent = text;
    toast.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), ms);
  }

  // --- Detection rendering -------------------------------------------------
  // Dim grid shown when no live frame is available (e.g. before the first
  // frame arrives or when the camera preview is dropping data).
  function drawPlaceholder() {
    const w = canvas.width;
    const h = canvas.height;
    ctx.fillStyle = "#050608";
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y < h; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
  }

  // Overlay detection boxes on whatever is already painted (live frame or grid).
  // Box coords are absolute camera pixels, so scale them to the canvas using the
  // frame's native resolution; fall back to normalised/raw coords when unknown.
  // Recognized audience arrived (per-face age/gender + scene target group).
  function onAudience(e) {
    latestAudience = {
      faces: Array.isArray(e.faces) ? e.faces : [],
      target_group: e.target_group || null,
      people_count: num(e.people_count),
      frame_w: num(e.frame_w),
      frame_h: num(e.frame_h),
    };
    renderAudience(latestAudience);
    // Repaint the overlay on the current frame so the group updates immediately
    // (the face model runs per cycle, slower than the streamed frames).
    if (frameImg.complete && frameImg.naturalWidth) {
      ctx.drawImage(frameImg, 0, 0, canvas.width, canvas.height);
    }
    drawAudience(latestAudience);
  }

  // Overlay per-face age/gender boxes. Face boxes are [x,y,w,h] in the CLASSIFIED
  // frame's pixels (shipped as frame_w/frame_h) — normalise by those, not the
  // preview frame, since the preview can be downscaled.
  function drawAudience(aud) {
    const w = canvas.width;
    const h = canvas.height;
    const fw = aud.frame_w || frameImg.naturalWidth || 0;
    const fh = aud.frame_h || frameImg.naturalHeight || 0;

    for (const f of aud.faces || []) {
      const box = f.box || [];
      let x = num(box[0]);
      let y = num(box[1]);
      let bw = num(box[2]);
      let bh = num(box[3]);
      if (fw > 0 && fh > 0) {
        const sx = w / fw;
        const sy = h / fh;
        x *= sx; y *= sy; bw *= sx; bh *= sy;
      } else if (Math.max(x, y, bw, bh) <= 1.001) {
        x *= w; y *= h; bw *= w; bh *= h;
      }
      if (bw <= 0 || bh <= 0) continue;

      ctx.strokeStyle = "#46d369";
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, bw, bh);

      const label = `${f.age_band || "?"} · ${f.gender || "?"}`;
      ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
      const tw = ctx.measureText(label).width + 8;
      ctx.fillStyle = "rgba(70, 211, 105, 0.9)";
      ctx.fillRect(x, Math.max(0, y - 14), tw, 14);
      ctx.fillStyle = "#0e1116";
      ctx.fillText(label, x + 4, Math.max(10, y - 4));
    }
  }

  function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  // Target-group badge + per-face list in the PiP overlay.
  function renderAudience(aud) {
    if (audienceGroupEl) {
      const tg = aud.target_group;
      if (tg && tg !== "unknown") {
        audienceGroupEl.textContent = `${tg} · ${aud.people_count}`;
        audienceGroupEl.classList.remove("muted");
      } else {
        audienceGroupEl.textContent = "no audience";
        audienceGroupEl.classList.add("muted");
      }
    }
    detectList.innerHTML = "";
    const faces = aud.faces || [];
    if (!faces.length) {
      const li = document.createElement("li");
      li.textContent = "—";
      li.style.opacity = "0.5";
      detectList.appendChild(li);
      return;
    }
    for (const f of faces.slice(0, 4)) {
      const li = document.createElement("li");
      const ac = Math.round((f.age_conf || 0) * 100);
      li.textContent = `${f.age_band || "?"} · ${f.gender || "?"} · ${ac}%`;
      detectList.appendChild(li);
    }
  }

  // --- Debug panel ---------------------------------------------------------
  const runs = new Map(); // run id -> { trigger, stages: [{stage,dur_ms,status}], total, done }
  const MAX_RUNS = 8;
  let frameStamps = [];

  // Toggle the panel with the "d" key (debug mode only).
  document.addEventListener("keydown", (e) => {
    if (e.key !== "d" && e.key !== "D") return;
    if (!debugEnabled) return;
    if (e.target && /^(input|textarea)$/i.test(e.target.tagName)) return;
    dbgPanel.classList.toggle("hidden");
  });

  socket.on("debug_event", (e) => {
    if (!debugEnabled || !e) return;
    switch (e.kind) {
      case "health": applyHealth(e); break;
      case "run_started": onRunStarted(e); break;
      case "stage": onStage(e); break;
      case "run_done": onRunDone(e); break;
      case "selection": showDecision(e); break;
      case "audience": onAudience(e); break;
      case "cms":
        setDot(dotCms, e.status !== "error");
        pushLog("INFO", `cms ${e.op} ${e.path} → ${e.status} · ${fmtMs(e.dur_ms)}` +
          (e.bytes != null ? ` · ${e.bytes}B` : ""));
        break;
      case "log": pushLog(e.level, `${e.logger}: ${e.message}`); break;
      default: break;
    }
  });

  function applyHealth(e) {
    setDot(dotCms, !!e.cms);
    setDot(dotLlm, !!e.llm);
    setDot(dotCam, !!e.camera);
    const cfg = e.config || {};
    if (cfg.variant) chipVariant.textContent = cfg.variant;
    dbgConfig.textContent =
      `trigger=${cfg.trigger_mode ?? "?"} · pool=${cfg.pool_id ?? "?"} · ` +
      `audience=${cfg.audience_group ?? "?"}\ncms=${cfg.cms_url ?? "?"}`;
  }

  function setDot(dot, ok) {
    if (!dot) return;
    dot.classList.toggle("ok", !!ok);
    dot.classList.toggle("bad", !ok);
  }

  // -- run timeline --
  function onRunStarted(e) {
    runs.set(e.run, { trigger: e.trigger || {}, stages: [], total: null, done: false });
    trimRuns();
    renderRuns();
  }
  function onStage(e) {
    const r = runs.get(e.run);
    if (!r) return;
    r.stages.push({ stage: e.stage, dur_ms: e.dur_ms || 0, status: e.status });
    renderRuns();
    if (e.status === "error") pushLog("ERROR", `${e.stage} failed: ${e.error || "?"}`);
  }
  function onRunDone(e) {
    const r = runs.get(e.run);
    if (!r) return;
    r.total = e.total_ms;
    r.done = true;
    r.status = e.status;
    renderRuns();
  }
  function trimRuns() {
    while (runs.size > MAX_RUNS) {
      const oldest = runs.keys().next().value;
      runs.delete(oldest);
    }
  }
  function renderRuns() {
    dbgRuns.innerHTML = "";
    const ids = [...runs.keys()].sort((a, b) => b - a);
    for (const id of ids) {
      const r = runs.get(id);
      const total = r.total || r.stages.reduce((s, x) => s + (x.dur_ms || 0), 0) || 1;
      const card = document.createElement("div");
      card.className = "run" + (r.status === "error" ? " error" : "");

      const head = document.createElement("div");
      head.className = "run__head";
      const trig = r.trigger?.type || "?";
      head.innerHTML = `<span>#${id} · ${esc(trig)}</span>` +
        `<span class="run__total">${r.done ? fmtMs(r.total) : "…"}</span>`;
      card.appendChild(head);

      const bar = document.createElement("div");
      bar.className = "run__bar";
      for (const s of r.stages) {
        const seg = document.createElement("div");
        seg.className = "seg " + (s.status === "error" ? "err" : s.stage);
        seg.style.width = Math.max(2, ((s.dur_ms || 0) / total) * 100) + "%";
        seg.title = `${s.stage} ${fmtMs(s.dur_ms)}`;
        seg.textContent = (s.dur_ms >= 80) ? s.stage[0] : "";
        bar.appendChild(seg);
      }
      card.appendChild(bar);

      const legend = document.createElement("div");
      legend.className = "run__legend";
      legend.textContent = r.stages.map((s) => `${s.stage} ${fmtMs(s.dur_ms)}`).join(" · ") || "running…";
      card.appendChild(legend);

      dbgRuns.appendChild(card);
    }
  }

  // -- last decision --
  function showDecision(e) {
    const rows = [];
    rows.push(row(`<b>variant</b> ${esc(e.variant || "?")}` +
      (e.inference_ms != null ? ` · inference ${fmtMs(e.inference_ms)}` : "") +
      (e.pool_cache_hit ? ` · <span class="badge ok">pool cached</span>` : "")));

    const badges =
      (e.retried ? `<span class="badge warn">retried</span>` : "") +
      (e.fell_back ? `<span class="badge warn">fell back</span>` : "") +
      (e.error ? `<span class="badge warn">error</span>` : "");
    rows.push(row(`<b>chosen</b> ${e.chosen_id != null ? "#" + e.chosen_id : "—"}${badges}`));
    if (e.reasoning) rows.push(row(`<b>why</b> ${esc(e.reasoning)}`));
    if (e.error) rows.push(row(`<b>err</b> ${esc(e.error)}`));

    const cands = (e.candidates || [])
      .map((c) => `<span class="cand${c.id === e.chosen_id ? " chosen" : ""}">#${c.id} ${esc(c.name || "")}</span>`)
      .join("");
    rows.push(`<div class="dec__cands">${cands}</div>`);

    rows.push(detailsBlock("prompt", e.prompt));
    rows.push(detailsBlock("raw response", e.raw_response));

    dbgDecision.innerHTML = rows.join("");
  }
  function row(html) { return `<div class="dec__row">${html}</div>`; }
  function detailsBlock(label, text) {
    if (!text) return "";
    return `<details><summary>${label} (${text.length} chars)</summary><pre>${esc(text)}</pre></details>`;
  }

  // -- event log --
  function pushLog(level, text) {
    const line = document.createElement("div");
    line.className = "logline " + (level || "INFO");
    line.innerHTML = `<span class="t">${clock()}</span>${esc(text)}`;
    dbgLog.prepend(line);
    while (dbgLog.childElementCount > 60) dbgLog.lastElementChild.remove();
  }

  // -- camera fps --
  function recordFrameForFps() {
    const now = performance.now();
    frameStamps.push(now);
    frameStamps = frameStamps.filter((t) => now - t <= 2000);
    if (camFpsEl) {
      const fps = frameStamps.length > 1 ? frameStamps.length / 2 : 0;
      camFpsEl.textContent = fps.toFixed(1);
    }
    setDot(dotCam, true);
  }

  // -- formatting helpers --
  function fmtMs(ms) {
    if (ms == null) return "—";
    return ms >= 1000 ? (ms / 1000).toFixed(2) + "s" : Math.round(ms) + "ms";
  }
  function clock() {
    const d = new Date();
    return d.toLocaleTimeString([], { hour12: false });
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Initial idle frame so the canvas isn't pure black on load.
  drawPlaceholder();

  // If we haven't received any frames in a while, dim the canvas to signal
  // "no recent data" rather than showing a stale frozen image.
  setInterval(() => {
    if (!debugEnabled) return;
    if (performance.now() - lastFrameTs > 3000) {
      latestAudience = emptyAudience();
      drawPlaceholder();
      renderAudience(latestAudience);
      frameStamps = [];
      if (camFpsEl) camFpsEl.textContent = "0";
      setDot(dotCam, false);
    }
  }, 1500);
})();
