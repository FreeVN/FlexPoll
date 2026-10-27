/* FlexPoll — frontend */
(() => {
  "use strict";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const ICONS = {
    relay: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7 9h3M7 15h3"/><circle cx="16.5" cy="9" r="1.6"/><circle cx="16.5" cy="15" r="1.6"/><path d="M10 9h3.2M10 15h3.2"/></svg>`,
    input: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M8 8v8M16 8v8M8 12h3M13 12h3"/><circle cx="12" cy="12" r="1.3"/></svg>`,
    universal: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7 8v8M12 8v8M17 8v8"/><circle cx="7" cy="12" r="1.1"/><path d="M11 10.5c2 3 2-3 4 0"/><path d="M16 12h2"/></svg>`,
    vav: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h7v14H3z"/><path d="M10 12h11"/><path d="M14 8l4 4-4 4"/><path d="M6 8v2M6 14v2"/></svg>`,
    pump: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="12" r="6.5"/><path d="M11 12l3.5-3.5"/><path d="M17.5 12H21M11 5.5V3M5 8.5 3 7.4"/><path d="M8 19.5 7 21.4"/></svg>`,
    wilo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><path d="M12 5v3M12 16v3M5 12h3M16 12h3"/><path d="M9 15c1.5-4 4.5-4 6 0"/></svg>`,
    heatpump: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="12" r="2.2"/><path d="M8 9.8V12l1.8 1"/><path d="M13 9h5M13 12h5M13 15h3"/></svg>`,
    valve_ev: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8v8l7-4z"/><path d="M21 8v8l-7-4z"/><path d="M12 4v3M12 17v3"/><path d="M9 4h6"/></svg>`,
    valve2: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9v6l6-3z"/><path d="M21 9v6l-6-3z"/><path d="M12 4v4M12 18v2"/><rect x="9.5" y="2.5" width="5" height="2.5" rx=".6"/></svg>`,
    valve6: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 3v12l-4 3-4-3V6z"/><path d="M6 8h-.5M18 8h.5M6 16h-.5M18 16h.5"/><path d="M9 12h6"/></svg>`,
    generic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h4M7 14h7"/><circle cx="17" cy="10" r="1.2"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>`,
    grip: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg>`,
  };

  let TYPES = {}, SIGNAL = {}, OVERRIDE = {}, GMODES = {}, GCMODES = {}, BAUD = [];
  let activeTab = localStorage.getItem("ml-tab") || "rtu";

  const isTcp = (m) => m.transport === "tcp";
  const tabAllows = (key, t) => {
    if (activeTab === "bacnet") return false;
    if (activeTab === "tcp") return t.transport === "tcp" || key === "generic";
    return t.transport !== "tcp";
  };
  const tabAllowsModule = (m) => {
    if (activeTab === "bacnet") return false;
    return activeTab === "tcp" ? isTcp(m) : !isTcp(m);
  };
  let WCONTROL = {}, LGMODES = {};
  let state = null;
  let topologySig = "";
  let paletteBound = false;
  let skew = 0;
  let portsSig = "";
  let newIds = new Set();

  // ------------------------------------------------------------------ API
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* leeg */ }
    if (!res.ok) {
      throw new Error((data && data.error) || `HTTP ${res.status}`);
    }
    return data;
  }

  function toast(msg, kind = "") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3400);
    setTimeout(() => el.remove(), 3800);
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    try {
      const t = await api("/api/types");
      TYPES = t.types; SIGNAL = t.signal_types; OVERRIDE = t.belimo_override;
      GMODES = t.grundfos_modes; GCMODES = t.grundfos_control_modes || {};
      WCONTROL = t.wilo_control || {}; LGMODES = t.lg_modes || {}; BAUD = t.baud_choices;
      renderPalette();
      applyTab();
      fillBaud();
      const s = await api("/api/state");
      applyState(s);
      $("#loghead").addEventListener("click", (e) => {
        if (e.target.closest(".dbg") || e.target.closest("#btn-clear-log")) return;
        $("#logwrap").classList.toggle("open");
        renderLog();
      });
      $("#trace-toggle").addEventListener("change", async () => {
        await saveConfig();
        if (state) state.bus.debug = $("#trace-toggle").checked;
        refresh();
      });
      $("#btn-clear-log").addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await api("/api/clear-log", { method: "POST", body: "{}" });
          if (state) state.log = [];
          renderLog();
        } catch (err) { toast(err.message, "err"); }
      });
      bindControls();
      setInterval(refresh, 3000);
      setInterval(tick, 1000);
    } catch (err) {
      toast("Kon de UI niet laden: " + err.message, "err");
    }
  }

  async function refresh() {
    try {
      const s = await api("/api/state");
      applyState(s);
    } catch (_) { /* stille retry */ }
  }

  function applyState(s) {
    state = s;
    renderBus(s.bus);
    renderTopology(s.modules);
    updateModules(s.modules);
    renderStatus(s);
    renderLog();
    if (typeof s.now === "number") skew = Date.now() / 1000 - s.now;
  }

  // ------------------------------------------------------------------ palette
  function renderPalette() {
    const host = $("#palette-tiles");
    const ORDER = ["Siemens", "Belimo", "Pompen", "Warmtepomp"];
    const groups = new Map();
    for (const [key, t] of Object.entries(TYPES)) {
      if (!tabAllows(key, t)) continue;
      const g = t.group || "Modules";
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push([key, t]);
    }
    const names = [...groups.keys()].sort((a, b) => {
      const ia = ORDER.includes(a) ? ORDER.indexOf(a) : 99;
      const ib = ORDER.includes(b) ? ORDER.indexOf(b) : 99;
      return ia - ib;
    });
    let html = "";
    for (const g of names) {
      html += `<div class="pgroup">${esc(g)}</div><div class="pgroup-items">`;
      for (const [key, t] of groups.get(g)) {
        html += `
      <div class="tile" draggable="true" data-type="${key}"
           style="--tile-accent:${t.accent};--tile-bg:${t.accent}14">
        <span class="ic">${ICONS[t.icon] || ""}</span>
        <div class="txt"><b>${esc(t.name)}</b><span>${esc(t.sub)}</span></div>
        <span class="plus">+</span>
      </div>`;
      }
      html += `</div>`;
    }
    host.innerHTML = html;
    if (paletteBound) return;
    paletteBound = true;

    host.addEventListener("dragstart", (e) => {
      const tile = e.target.closest(".tile");
      if (!tile) return;
      e.dataTransfer.setData("text/x-module", tile.dataset.type);
      e.dataTransfer.effectAllowed = "copy";
      tile.style.opacity = ".55";
      setTimeout(() => (tile.style.opacity = ""), 300);
    });
    host.addEventListener("click", (e) => {
      const tile = e.target.closest(".tile");
      if (tile) addModule(tile.dataset.type, null);
    });
  }

  // ------------------------------------------------------------------ bus
  function fillBaud() {
    $("#baud").innerHTML = BAUD.map((b) => `<option value="${b}">${b} bps</option>`).join("");
  }

  function renderBus(bus) {
    const sel = $("#port");
    const sig = (bus.ports || []).map((p) => p.path).join("|") + "§" + bus.port;
    if (sig !== portsSig) {
      portsSig = sig;
      sel.innerHTML = (bus.ports || []).map((p) =>
        `<option value="${esc(p.path)}">${esc(p.label)} — ${esc(p.real)}${p.present ? "" : " (weg)"}</option>`
      ).join("");
      if (bus.port && !(bus.ports || []).some((p) => p.path === bus.port)) {
        sel.insertAdjacentHTML("beforeend", `<option value="${esc(bus.port)}">${esc(bus.port)}</option>`);
      }
    }
    sel.value = bus.port;
    $("#trace-toggle").checked = !!bus.debug;
    $("#baud").value = bus.baud;
    $("#parity").value = bus.parity;
    $("#stopbits").value = String(bus.stopbits);
  }

  function renderStatus(s) {
    const bus = s.bus;
    const mods = (s.modules || []).filter(tabAllowsModule);
    const anyOk = mods.some((m) => m.state && m.state.ok);
    const pill = $("#buspill");
    let txt = "Bus offline", cls = "err";
    if (activeTab === "bacnet") {
      txt = "BACnet/IP"; cls = "";
    } else if (activeTab === "tcp") {
      if (!mods.length) { txt = "Geen TCP-toestel"; cls = ""; }
      else if (anyOk) { txt = "TCP/IP online"; cls = "ok"; }
      else { txt = "TCP/IP offline"; cls = "err"; }
    } else if (bus.open && anyOk) { txt = "Bus online"; cls = "ok"; }
    else if (bus.open && mods.length === 0) { txt = "Bus open"; cls = ""; }
    else if (bus.open) { txt = "Geen antwoord"; cls = "err"; }
    else if (bus.error) { txt = "Poortfout"; cls = "err"; }
    pill.className = `pill ${cls}`;
    $("#buspill-txt").textContent = txt;
    $("#hostinfo").textContent = activeTab === "bacnet" ? "UDP 47808"
      : activeTab === "tcp"
      ? (mods.length ? `${mods.filter((m) => m.ip).length}/${mods.length} met IP` : "TCP/IP")
      : (bus.port ? bus.port.split("/").pop() : "geen poort");
    $("#modcount").textContent = `${mods.length} module${mods.length === 1 ? "" : "s"}`;
    $("#empty").style.display = mods.length ? "none" : "grid";
    if (s.scanning && s.scan_progress) {
      const bar = $("#scanbar");
      bar.className = "scanbar show";
      bar.innerHTML = `<span class="lbl">Scannen</span><span class="scanhit">adres ${s.scan_progress.current} van ${s.scan_progress.end}…</span>`;
    }
  }

  function tick() {
    const el = $("#cd-last");
    if (!state || !state.last_poll) { el.textContent = "wachten op meting…"; return; }
    const age = Math.max(0, Math.round(Date.now() / 1000 - skew - state.last_poll));
    const interval = (state.bus && state.bus.interval) || 10;
    el.textContent = age <= 1 ? "net gemeten" : `meting ${age} s geleden`;
    el.classList.toggle("stale", age > interval * 1.8 + 2);
  }

  // ------------------------------------------------------------------ topology
  function renderTopology(all) {
    const mods = (all || []).filter(tabAllowsModule);
    const sig = activeTab + "|" + mods.map((m) => `${m.id}:${m.type}:${m.release ? "r" : ""}`).join(",");
    if (sig === topologySig) return;
    topologySig = sig;
    newIds = new Set(mods.map((m) => m.id));
    const host = $("#modules");
    host.innerHTML = mods.map(cardHTML).join("");
    $("#empty").style.display = mods.length ? "none" : "grid";
  }

  function cardHTML(m) {
    const t = m.type_meta || {};
    const accent = t.accent || "#E4002B";
    return `
      <article class="card" data-id="${m.id}"
               style="--card-accent:${accent};--card-bg:${accent}12">
        <div class="card-head">
          <span class="ic">${ICONS[t.icon] || ""}</span>
          <div class="tt">
            <h3>${esc(t.name || m.type)}</h3>
            <p>${esc(t.sub || "")}</p>
          </div>
          <div class="tools">
            <span class="iconbtn grip" draggable="true" data-drag="1" title="Versleep">${ICONS.grip}</span>
            <button class="iconbtn danger" data-act="del" title="Verwijderen">${ICONS.trash}</button>
          </div>
        </div>
        <div class="card-meta">
          ${m.transport === "tcp" ? `
          <div class="addr"><label>IP</label>
            <input type="text" inputmode="decimal" value="${esc(m.ip || "")}" placeholder="192.168.1.50" data-role="ip">
          </div>
          <div class="addr"><label>Unit</label>
            <input type="number" min="1" max="254" value="${m.address}" data-role="address">
          </div>` : `
          <div class="addr"><label>Adres</label>
            <input type="number" min="1" max="247" value="${m.address}" data-role="address">
          </div>`}
          <span class="dot" data-role="dot"></span>
          <span class="serial" data-role="serial">SN —</span>
        </div>
        <div class="card-body">${bodyHTML(m)}</div>
        <div class="card-foot"><span data-role="stamp">wachten op eerste meting…</span></div>
      </article>`;
  }

  function belimoVariantBody(m) {
    const t = TYPES[m.type] || {};
    const ov = t.overrides || OVERRIDE;
    const isEV = m.type === "belimo_ev";
    const is6 = m.type === "belimo_epiv6";
    return `
      <div class="chips">
        <span class="chip" data-role="ovchip">—</span>
        <span class="chip" data-role="cmchip">—</span>
        ${is6 ? '<span class="chip" data-role="seqchip">—</span>' : ""}
        <span class="chip" data-role="fwchip">—</span>
      </div>
      <div class="bigval"><span class="n" data-role="flow">—</span><span class="u">m³/h</span></div>
      <div class="subval" data-role="flowsub">—</div>
      <div class="bar"><i data-role="posbar" style="width:0%"></i></div>
      ${isEV ? `<div style="margin-top:8px">
        <div class="kv"><span>Aanvoer T1</span><b><span data-role="t1">—</span> °C</b></div>
        <div class="kv"><span>Retour T2</span><b><span data-role="t2">—</span> °C</b></div>
        <div class="kv"><span>ΔT</span><b><span data-role="dt">—</span> K</b></div>
        <div class="kv"><span>Vermogen</span><b><span data-role="power">—</span> kW</b></div>
      </div>` : ""}
      <div class="ctrl-row" style="margin-top:10px">
        <label>Override</label>
        <select data-role="override">${Object.entries(ov).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
      </div>
      <div class="ctrl-row">
        <label>Setpunt</label>
        <input type="number" min="0" max="100" step="1" data-role="setpoint" placeholder="%">
        <button class="btn small primary" type="button" data-act="setsp">Zet</button>
      </div>
      ${flowLimits(m)}
      ${isEV ? `<div class="kv" style="margin-top:7px"><span>Vnom (naamplaat)</span><b><span data-role="vnom">—</span> m³/h</b></div>` : ""}`;
  }

  function flowLimits(m) {
    if (m.type === "belimo_epiv6") {
      return `<div class="limrow">
        <label>V'max 1</label><input type="number" min="0" max="97.2" step="0.1" data-role="vmax1" title="Maximaal debiet sequentie 1 (register 209)">
        <span>l/s</span>
        <label>V'max 2</label><input type="number" min="0" max="97.2" step="0.1" data-role="vmax2" title="Maximaal debiet sequentie 2 (register 214)">
        <span>l/s</span>
        <button class="btn tiny primary" type="button" data-act="setvmax">Zet</button>
      </div>`;
    }
    return `<div class="limrow">
      <label>Vmin</label><input type="number" min="0" max="100" step="0.5" data-role="vmin" title="Minimaal debiet in % van Vnom (register 106)">
      <span>%</span>
      <label>Vmax</label><input type="number" min="0" max="100" step="0.5" data-role="vmax" title="Maximaal debiet in % van Vnom (register 107)">
      <span>%</span>
      <button class="btn tiny primary" type="button" data-act="setvlim">Zet</button>
    </div>`;
  }

  function lrRow() {
    return `<div class="lr">
      <span class="lbl">Aansturing</span>
      <button class="lrbtn" type="button" data-act="local" title="Lokaal: sturing via pompdisplay of digitale ingang">Local</button>
      <button class="lrbtn" type="button" data-act="remote" title="Remote: sturing via Modbus">Remote</button>
    </div>`;
  }

  function releasedBanner() {
    return `<div class="released">
      <b>Framing vrijgegeven</b>
      <span>Module wordt niet gepolld — het eerste frame zet de framing weer vast.</span>
      <button class="btn tiny ghost" type="button" data-act="resume">Weer pollen</button>
    </div>`;
  }

  function siemensTools() {
    return `<div class="em-tools">
      <span class="comm" data-role="comm">framing onbekend</span>
      <button class="btn tiny ghost" type="button" data-act="baudauto"
              title="4x0310/4x0311 terug op Auto + herstart — signaaltypes blijven bewaard">Baud → auto</button>
      <button class="btn tiny danger" type="button" data-act="factory"
              title="Factory reset (4x0320 = 0xCAFE): wist alle terminalconfiguratie">Reset</button>
    </div>`;
  }

  function bodyHTML(m) {
    switch (m.type) {
      case "em18r":
        return (m.release ? releasedBanner() : "") + `<div class="io-grid">${Array.from({ length: 8 }, (_, i) => `
          <button class="io" type="button" data-ch="${i + 1}" data-role="do">
            <span class="led"></span><b>DO${i + 1}</b><small>—</small>
          </button>`).join("")}</div>` + siemensTools();

      case "em18d":
        return (m.release ? releasedBanner() : "") + `<div class="io-grid">${Array.from({ length: 8 }, (_, i) => `
          <div class="io" data-ch="${i + 1}" data-role="di">
            <span class="led"></span><b>DI${i + 1}</b><small>—</small>
          </div>`).join("")}</div>` + siemensTools();

      case "em18u":
        return (m.release ? releasedBanner() : "") + `<div class="uio-grid">${Array.from({ length: 8 }, (_, i) => {
          const ch = i + 1;
          const opts = Object.entries(SIGNAL)
            .map(([k, v]) => `<option value="${k}">${esc(v.name)}</option>`).join("");
          return `<div class="uio" data-ch="${ch}">
            <div class="uio-top"><b>X${ch}</b>
              <span class="val" data-role="val">—</span>
              <span class="rel" data-role="rel"></span>
            </div>
            <div class="uio-bot"><select data-role="stype">${opts}</select></div>
            <div class="ao">
              <input type="number" min="0" max="10" step="0.1" data-role="aoval" title="Uitgangsspanning">
              <button type="button" data-act="setao">Zet</button>
            </div>
          </div>`;
        }).join("")}</div>` + siemensTools();

      case "belimo":
        return `
          <div class="chips">
            <span class="chip" data-role="ovchip">—</span>
            <span class="chip" data-role="fwchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="flow">—</span><span class="u">m³/h</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div class="bar"><i data-role="posbar" style="width:0%"></i></div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Override</label>
            <select data-role="override">${Object.entries(OVERRIDE).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </div>
          <div class="ctrl-row">
            <label>Setpunt</label>
            <input type="number" min="0" max="100" step="0.5" data-role="setpoint" placeholder="%">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>
          ${flowLimits(m)}`;

      case "wilo_stratos":
        return `
          <div class="chips">
            <span class="chip" data-role="onchip">—</span>
            <span class="chip" data-role="cmchip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="flow">—</span><span class="u">m³/h</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Opvoerhoogte</span><b><span data-role="head">—</span> m</b></div>
            <div class="kv"><span>Toerental</span><b><span data-role="speed">—</span> rpm</b></div>
            <div class="kv"><span>Vermogen</span><b><span data-role="power">—</span> W</b></div>
            <div class="kv"><span>Medium</span><b><span data-role="temp">—</span> °C</b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Aan / uit</label>
            <label class="switch"><input type="checkbox" data-role="onoff"><i></i></label>
          </div>
          ${lrRow()}
          <div class="ctrl-row">
            <label>Regelfunctie</label>
            <select data-role="controlmode" style="flex:1">${Object.entries(WCONTROL).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </div>
          <div class="ctrl-row">
            <label>Setpunt</label>
            <input type="number" min="0" max="100" step="1" data-role="setpoint" placeholder="%">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>`;

      case "lg_ub40":
        return `
          <div class="chips">
            <span class="chip" data-role="onchip">—</span>
            <span class="chip" data-role="modechip">—</span>
            <span class="chip" data-role="compchip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="tout">—</span><span class="u">°C</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Retour</span><b><span data-role="tin">—</span> °C</b></div>
            <div class="kv"><span>Buiten</span><b><span data-role="toutdoor">—</span> °C</b></div>
            <div class="kv"><span>DHW</span><b><span data-role="tdhw">—</span> °C</b></div>
            <div class="kv"><span>Debiet</span><b><span data-role="flowrate">—</span> l/min</b></div>
            <div class="kv"><span>Waterdruk</span><b><span data-role="pressure">—</span> bar</b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Aan / uit</label>
            <label class="switch"><input type="checkbox" data-role="onoff"><i></i></label>
          </div>
          <div class="ctrl-row">
            <label>Modus</label>
            <select data-role="lgmode" style="flex:1">${Object.entries(LGMODES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </div>
          <div class="ctrl-row">
            <label>Aanvoer</label>
            <input type="number" min="5" max="65" step="0.5" data-role="setpoint" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>
          <div class="ctrl-row">
            <label>DHW</label>
            <input type="number" min="30" max="80" step="0.5" data-role="dhw" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setdhw">Zet</button>
          </div>`;

      case "belimo_ev":
      case "belimo_epiv2":
      case "belimo_epiv6":
        return belimoVariantBody(m);

      case "generic":
        return `
          <div class="chips">
            <span class="chip" data-role="pcount">0 punten</span>
          </div>
          <div class="plist" data-role="plist"><div class="pempty">Nog geen punten.</div></div>
          <button class="btn small ghost" type="button" data-act="addpoint" style="margin-top:8px;width:100%">+ punt toevoegen</button>`;

      case "carrier_sms":
        return `
          <div class="chips">
            <span class="chip" data-role="onchip">—</span>
            <span class="chip" data-role="modechip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="lwt">—</span><span class="u">°C</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Ingang water</span><b><span data-role="ewt">—</span> °C</b></div>
            <div class="kv"><span>Buiten</span><b><span data-role="oat">—</span> °C</b></div>
            <div class="kv"><span>Buffervat</span><b><span data-role="buffer">—</span> °C</b></div>
            <div class="kv"><span>DHW-vat</span><b><span data-role="dhwtank">—</span> °C</b></div>
            <div class="kv"><span>Actieve pompen</span><b><span data-role="running">—</span></b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Aan / uit</label>
            <label class="switch"><input type="checkbox" data-role="onoff"><i></i></label>
          </div>
          <div class="ctrl-row">
            <label>Regeling</label>
            <select data-role="cmode" style="flex:1">
              <option value="1">Koelen</option><option value="2">Verwarmen</option><option value="3">Automatisch</option>
            </select>
          </div>
          <div class="ctrl-row">
            <label>DHW</label>
            <input type="number" min="25" max="75" step="0.5" data-role="dhw" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setdhw">Zet</button>
          </div>`;

      case "clivet":
        return `
          <div class="chips">
            <span class="chip" data-role="onchip">—</span>
            <span class="chip" data-role="modechip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="two">—</span><span class="u">°C</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Ingang water</span><b><span data-role="twi">—</span> °C</b></div>
            <div class="kv"><span>Water</span><b><span data-role="tw">—</span> °C</b></div>
            <div class="kv"><span>Buiten</span><b><span data-role="t4">—</span> °C</b></div>
            <div class="kv"><span>Compressor</span><b><span data-role="hz">—</span> Hz</b></div>
            <div class="kv"><span>Stroom</span><b><span data-role="amp">—</span> A</b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Modus</label>
            <select data-role="cmode" style="flex:1">
              <option value="1">Koelen</option><option value="2">Verwarmen</option>
              <option value="4">DHW</option><option value="8">UIT</option>
            </select>
          </div>
          <div class="ctrl-row">
            <label>Setpunt</label>
            <input type="number" min="5" max="65" step="0.5" data-role="setpoint" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>
          <div class="ctrl-row">
            <label>DHW</label>
            <input type="number" min="20" max="60" step="0.5" data-role="dhw" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setdhw">Zet</button>
          </div>
          <div class="em-tools">
            <span class="comm" data-role="errchip">foutcode —</span>
            <button class="btn tiny ghost" type="button" data-act="clearerr" title="Lock-errors wissen (register 6)">Fouten wissen</button>
          </div>`;

      case "clivet_slave":
        return `
          <div class="chips">
            <span class="chip" data-role="unitchip">unit —</span>
            <span class="chip" data-role="modechip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="two">—</span><span class="u">°C</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Ingang water</span><b><span data-role="twi">—</span> °C</b></div>
            <div class="kv"><span>Water</span><b><span data-role="tw">—</span> °C</b></div>
            <div class="kv"><span>Buiten</span><b><span data-role="t4">—</span> °C</b></div>
            <div class="kv"><span>Compressor</span><b><span data-role="hz">—</span> Hz</b></div>
            <div class="kv"><span>Stroom</span><b><span data-role="amp">—</span> A</b></div>
            <div class="kv"><span>Ventilator</span><b><span data-role="fan">—</span> rpm</b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Slave</label>
            <select data-role="unit" style="flex:1" title="Intern adres op de masterbus: registers verschuiven met 100 per unit">
              ${[1,2,3,4,5,6,7,8].map((n) => `<option value="${n}">Unit ${n}</option>`).join("")}
            </select>
          </div>
          <div class="em-tools">
            <span class="comm" data-role="errchip">enkel lezen — vrijgave via master</span>
          </div>`;

      case "daikin":
        return `
          <div class="chips">
            <span class="chip" data-role="statuschip">—</span>
            <span class="chip" data-role="modechip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="lwt">—</span><span class="u">°C</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Verdamper in</span><b><span data-role="ewt">—</span> °C</b></div>
            <div class="kv"><span>Actief setpunt</span><b><span data-role="asp">—</span> °C</b></div>
            <div class="kv"><span>Capaciteit</span><b><span data-role="cap">—</span> %</b></div>
            <div class="kv"><span>Verdamperpomp</span><b><span data-role="pump">—</span></b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Aan / uit</label>
            <label class="switch"><input type="checkbox" data-role="onoff"><i></i></label>
          </div>
          <div class="ctrl-row">
            <label>Regeling</label>
            <select data-role="dmode" style="flex:1">
              <option value="0">Koelen</option><option value="1">Verwarmen</option>
            </select>
          </div>
          <div class="ctrl-row">
            <label>Setpunt</label>
            <input type="number" min="-15" max="60" step="0.5" data-role="setpoint" placeholder="°C">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>
          <div class="em-tools">
            <span class="comm" data-role="faultchip">storing —</span>
            <button class="btn tiny ghost" type="button" data-act="clearalarm" title="Alarmen wissen (4x0010)">Alarmen wissen</button>
          </div>`;

      case "grundfos":
        return `
          <div class="chips">
            <span class="chip" data-role="onchip">—</span>
            <span class="chip" data-role="remotechip">—</span>
            <span class="chip" data-role="alarmchip">—</span>
          </div>
          <div class="bigval"><span class="n" data-role="flow">—</span><span class="u">m³/h</span></div>
          <div class="subval" data-role="flowsub">—</div>
          <div style="margin-top:8px">
            <div class="kv"><span>Opvoerhoogte</span><b><span data-role="head">—</span> bar</b></div>
            <div class="kv"><span>Toerental</span><b><span data-role="rpm">—</span> rpm</b></div>
            <div class="kv"><span>Frequentie</span><b><span data-role="freq">—</span> Hz</b></div>
            <div class="kv"><span>Motorstroom</span><b><span data-role="amp">—</span> A</b></div>
            <div class="kv"><span>Temperatuur</span><b><span data-role="temp">—</span> °C</b></div>
          </div>
          <div class="ctrl-row" style="margin-top:10px">
            <label>Aan / uit</label>
            <label class="switch"><input type="checkbox" data-role="onoff"><i></i></label>
            <label style="margin-left:auto">Modus</label>
            <select data-role="mode" style="flex:0 0 108px">${Object.entries(GMODES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </div>
          ${lrRow()}
          <div class="ctrl-row">
            <label>Regelmethode</label>
            <select data-role="controlmode" style="flex:1">${Object.entries(GCMODES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </div>
          <div class="ctrl-row">
            <label>Setpunt</label>
            <input type="number" min="0" max="100" step="1" data-role="setpoint" placeholder="%">
            <button class="btn small primary" type="button" data-act="setsp">Zet</button>
          </div>`;
    }
    return "";
  }

  // ------------------------------------------------------------------ values
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const num = (v, d = 1) => (isNum(v) ? v.toFixed(d).replace(".", ",") : "—");
  const clock = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("nl-BE", { hour12: false }) : "—";

  function setText(card, role, txt) {
    const el = card.querySelector(`[data-role="${role}"]`);
    if (el && el.textContent !== txt) el.textContent = txt;
  }

  function renderGenericPoints(card, m, values) {
    const pts = m.points || [];
    setText(card, "pcount", `${pts.length} punt${pts.length === 1 ? "" : "en"}`);
    const list = card.querySelector('[data-role="plist"]');
    if (!list) return;
    const byId = new Map((values || []).map((p) => [String(p.id), p]));
    const sig = pts.map((p) => p.id).join(",") + "|" +
      pts.map((p) => {
        const s = byId.get(String(p.id)) || {};
        return s.ok ? s.value : (s.error ? "E" : "-");
      }).join(",");
    if (list.dataset.sig === sig || list.contains(document.activeElement)) return;
    list.dataset.sig = sig;
    list.innerHTML = pts.length ? pts.map((p) => {
      const st = byId.get(String(p.id)) || {};
      const shown = st.ok ? (typeof st.value === "number" && !Number.isInteger(st.value) ? num(st.value, 2) : String(st.value)) : "";
      const val = st.ok ? `${shown}${p.unit ? " " + p.unit : ""}` : (st.error ? "fout" : "—");
      let ctl = "";
      if (p.rw) {
        ctl = p.ctrl === "button"
          ? `<button class="btn tiny" data-act="pwrite" data-pid="${p.id}" data-val="1">AAN</button><button class="btn tiny ghost" data-act="pwrite" data-pid="${p.id}" data-val="0">UIT</button>`
          : `<input class="pin" type="number" step="any" data-pin="${p.id}" placeholder="${st.ok ? st.value : ""}"><button class="btn tiny primary" data-act="pwrite" data-pid="${p.id}">Zet</button>`;
      }
      return `<div class="prow"><span class="pn">${esc(p.name || `FC${p.fc} ${p.addr}`)}</span><span class="pv ${st.ok ? "" : "bad"}">${esc(String(val))}</span>${ctl}<button class="btn tiny ghost" data-act="pdel" data-pid="${p.id}" title="verwijderen">×</button></div>`;
    }).join("") : `<div class="pempty">Nog geen punten.</div>`;
  }

  function updateModules(mods) {
    for (const m of mods) {
      const card = $(`.card[data-id="${m.id}"]`);
      if (!card) continue;
      const st = m.state || {};
      const ok = !!st.ok;
      card.classList.toggle("offline", !ok);
      const dot = card.querySelector('[data-role="dot"]');
      if (dot) dot.className = "dot " + (ok ? "ok" : "err");

      const addrInput = card.querySelector('[data-role="address"]');
      if (addrInput && document.activeElement !== addrInput) addrInput.value = m.address;

      if (m.type === "clivet_slave") {
        const us = card.querySelector('[data-role="unit"]');
        if (us && document.activeElement !== us) us.value = String(m.unit || 1);
        const uc = card.querySelector('[data-role="unitchip"]');
        if (uc && !ok) uc.textContent = `unit ${m.unit || 1}`;
      }

      const serial = card.querySelector('[data-role="serial"]');
      if (serial) {
        if (st.serial) serial.innerHTML = `SN <b>${esc(st.serial)}</b>`;
        else serial.innerHTML = `SN <b>—</b>`;
      }

      const stamp = card.querySelector('[data-role="stamp"]');
      if (stamp) {
        stamp.innerHTML = ok
          ? `${clock(st.ts)} · ${st.ms > 0 ? st.ms + " ms" : "<1 ms"}`
          : `<span class="err">${esc(st.error || "geen antwoord")}</span>`;
      }

      if (!ok || !st.values) {
        // offline: bij de algemene deelnemer blijven de punten zichtbaar (met streepjes)
        if (m.type === "generic") renderGenericPoints(card, m, (st.values || {}).points || []);
        continue;
      }
      const v = st.values;

      if (m.type === "belimo" || m.type === "belimo_ev") {
        for (const [role, key] of [["vmin", "vmin"], ["vmax", "vmax"]]) {
          const el = card.querySelector(`[data-role="${role}"]`);
          if (el && document.activeElement !== el) el.value = isNum(v[key]) ? String(v[key]) : "";
        }
        if (m.type === "belimo_ev") setText(card, "vnom", isNum(v.vnom) ? num(v.vnom, 2) : "—");
      }
      if (m.type === "belimo_epiv6") {
        for (const [role, key] of [["vmax1", "vmax1_ls"], ["vmax2", "vmax2_ls"]]) {
          const el = card.querySelector(`[data-role="${role}"]`);
          if (el && document.activeElement !== el) el.value = isNum(v[key]) ? String(v[key]) : "";
        }
      }
      if (m.type === "generic") renderGenericPoints(card, m, v.points || []);
      if (m.type === "carrier_sms") {
        setText(card, "lwt", num(v.lwt, 1));
        setText(card, "ewt", num(v.ewt, 1));
        setText(card, "oat", num(v.oat, 1));
        setText(card, "buffer", num(v.buffer, 1));
        setText(card, "dhwtank", num(v.dhw_tank, 1));
        setText(card, "running", v.running != null ? `${v.running}/4` : "—");
        setText(card, "flowsub", `${v.prod_mode_txt || "—"} · HP1 ${v.hp1_unit_txt || "—"}`);
        const oc = card.querySelector('[data-role="onchip"]');
        if (oc) { oc.textContent = v.on_txt || "—"; oc.className = "chip " + (v.on ? "ok" : ""); }
        const mc = card.querySelector('[data-role="modechip"]');
        if (mc) { mc.textContent = v.mode_cmd_txt || "—"; mc.className = "chip blue"; }
        const ac = card.querySelector('[data-role="alarmchip"]');
        if (ac) { ac.textContent = v.hp1_alarm_txt || "—"; ac.className = "chip " + (v.hp1_alarm === 1 ? "ok" : "err"); }
        const sw = card.querySelector('[data-role="onoff"]');
        if (sw) sw.checked = !!v.on;
        const cs = card.querySelector('[data-role="cmode"]');
        if (cs && document.activeElement !== cs) cs.value = String(v.mode_cmd);
      }
      if (m.type === "clivet") {
        setText(card, "two", num(v.two, 1));
        setText(card, "twi", num(v.twi, 1));
        setText(card, "tw", num(v.tw, 1));
        setText(card, "t4", num(v.t4, 1));
        setText(card, "hz", v.comp_hz != null ? String(v.comp_hz) : "—");
        setText(card, "amp", num(v.comp_a, 1));
        setText(card, "flowsub", `${v.odu_txt || "—"} · setpunt ${num(v.setpoint, 0)} °C`);
        const oc = card.querySelector('[data-role="onchip"]');
        if (oc) { oc.textContent = v.on ? "AAN" : "UIT"; oc.className = "chip " + (v.on ? "ok" : ""); }
        const mc = card.querySelector('[data-role="modechip"]');
        if (mc) { mc.textContent = v.mode_txt || "—"; mc.className = "chip blue"; }
        const ac = card.querySelector('[data-role="alarmchip"]');
        if (ac) { ac.textContent = v.error ? `E${v.error}` : "geen fout"; ac.className = "chip " + (v.error ? "err" : "ok"); }
        const ec = card.querySelector('[data-role="errchip"]');
        if (ec) ec.textContent = v.error ? `foutcode ${v.error}` : "geen foutcode";
        const cs = card.querySelector('[data-role="cmode"]');
        if (cs && document.activeElement !== cs) cs.value = String(v.mode);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.setpoint, 0)} °C`;
      }
      if (m.type === "clivet_slave") {
        setText(card, "two", num(v.two, 1));
        setText(card, "twi", num(v.twi, 1));
        setText(card, "tw", num(v.tw, 1));
        setText(card, "t4", num(v.t4, 1));
        setText(card, "hz", v.comp_hz != null ? String(v.comp_hz) : "—");
        setText(card, "amp", num(v.comp_a, 1));
        setText(card, "fan", v.fan1 != null ? String(v.fan1) : "—");
        setText(card, "flowsub", `unit ${v.unit ?? m.unit} · ${v.odu_txt || "—"}${v.t5s != null ? ` · vat ${num(v.t5s, 0)} °C` : ""}`);
        const uc = card.querySelector('[data-role="unitchip"]');
        if (uc) { uc.textContent = `unit ${v.unit ?? m.unit}`; uc.className = "chip blue"; }
        const mc = card.querySelector('[data-role="modechip"]');
        if (mc) { mc.textContent = v.odu_txt || "—"; mc.className = "chip"; }
        const ac = card.querySelector('[data-role="alarmchip"]');
        if (ac) {
          ac.textContent = v.error == null ? "geen foutcode" : (v.error ? `E${v.error}` : "geen fout");
          ac.className = "chip " + (v.error ? "err" : "ok");
        }
        const ec = card.querySelector('[data-role="errchip"]');
        if (ec) ec.textContent = "enkel lezen — vrijgave via master";
      }
      if (m.type === "daikin") {
        setText(card, "lwt", num(v.lwt, 1));
        setText(card, "ewt", num(v.ewt, 1));
        setText(card, "asp", num(v.active_sp, 1));
        setText(card, "cap", v.capacity != null ? String(v.capacity) : "—");
        setText(card, "pump", v.pump ? "aan" : "uit");
        setText(card, "flowsub", `${v.source_txt || "—"} · ${v.status_txt || "—"} · capaciteit ${v.capacity ?? "—"} %`);
        const sc = card.querySelector('[data-role="statuschip"]');
        if (sc) { sc.textContent = v.status_txt || "—"; sc.className = "chip " + (v.status === 3 ? "ok" : ""); }
        const mc = card.querySelector('[data-role="modechip"]');
        if (mc) { mc.textContent = v.mode_txt || "—"; mc.className = "chip blue"; }
        const ac = card.querySelector('[data-role="alarmchip"]');
        if (ac) { ac.textContent = v.alarm ? "ALARM" : "normaal"; ac.className = "chip " + (v.alarm ? "err" : "ok"); }
        const fc = card.querySelector('[data-role="faultchip"]');
        if (fc) fc.textContent = v.fault || v.problem ? `storing ${v.fault || v.problem}` : "geen storing";
        const sw = card.querySelector('[data-role="onoff"]');
        if (sw) sw.checked = !!v.on;
        const dm = card.querySelector('[data-role="dmode"]');
        if (dm && document.activeElement !== dm) dm.value = String(v.mode === 3 ? 1 : 0);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.active_sp, 1)} °C`;
      }

      if (m.type === "grundfos" || m.type === "wilo_stratos") {
        let lrmode = null;
        if (m.type === "grundfos") lrmode = (v.remote_req ?? v.remote) ? "remote" : "local";
        else if (v.bus_cmd === 1) lrmode = "remote";
        else if (v.bus_cmd === 4 || v.bus_cmd === 5) lrmode = "local";
        card.querySelectorAll(".lrbtn").forEach((b) => {
          b.classList.toggle("on", b.dataset.act === lrmode);
          b.disabled = lrmode === null;
        });
      }

      if (m.type === "em18r" || m.type === "em18d" || m.type === "em18u") {
        const comm = card.querySelector('[data-role="comm"]');
        if (comm) {
          comm.textContent = v.comm_text || "framing onbekend";
          comm.classList.toggle("fixed", !!(v.comm_baud_reg));
        }
      }

      if (m.type === "em18r") {
        (v.do || []).forEach((val, i) => {
          const el = card.querySelector(`.io[data-ch="${i + 1}"]`);
          if (!el) return;
          el.classList.toggle("on", !!val);
          el.classList.toggle("off", !val);
          el.querySelector("small").textContent = val ? "AAN" : "UIT";
        });
      }

      if (m.type === "em18d") {
        (v.di || []).forEach((val, i) => {
          const el = card.querySelector(`.io[data-ch="${i + 1}"]`);
          if (!el) return;
          el.classList.toggle("on", !!val);
          el.classList.toggle("off", !val);
          el.querySelector("small").textContent = val ? "NC" : "NO";
        });
      }

      if (m.type === "em18u") {
        (v.channels || []).forEach((c) => {
          const el = card.querySelector(`.uio[data-ch="${c.ch}"]`);
          if (!el) return;
          el.classList.toggle("ao-on", c.type === 10);
          const valEl = el.querySelector('[data-role="val"]');
          let txt = "—";
          if (c.type === 6) txt = c.value == null ? "—" : (c.value ? "1" : "0");
          else if (c.value != null && c.type !== 0) txt = `${num(c.value, c.type === 4 ? 0 : 1)}${c.unit ? " " + c.unit : ""}`;
          if (valEl.innerHTML !== txt) valEl.innerHTML = esc(txt);

          const rel = el.querySelector('[data-role="rel"]');
          const bad = c.rel !== 0 && c.rel !== 32762;
          rel.className = "rel" + (bad ? " bad" : "");
          rel.textContent = c.rel === 0 ? "OK" : c.rel_txt;

          const sel = el.querySelector('[data-role="stype"]');
          if (sel && document.activeElement !== sel) sel.value = String(c.type);

          const ao = el.querySelector('[data-role="aoval"]');
          if (ao && document.activeElement !== ao && c.type === 10) ao.value = num(c.value, 1).replace(",", ".");
        });
      }

      if (m.type === "belimo") {
        setText(card, "flow", num(v.flow, 1));
        const q = v.qnom ? ` · ${num(v.flow_rel, 0)} % van qnom ${num(v.qnom, 0)}` : "";
        setText(card, "flowsub", `klep ${num(v.position, 0)} % open${q}`);
        const bar = card.querySelector('[data-role="posbar"]');
        if (bar) bar.style.width = `${Math.max(0, Math.min(100, v.position || 0))}%`;
        const ov = card.querySelector('[data-role="ovchip"]');
        if (ov) {
          ov.textContent = v.override_txt || "Auto";
          ov.className = "chip " + (v.override ? "blue" : "ok");
        }
        const fw = card.querySelector('[data-role="fwchip"]');
        if (fw) fw.textContent = v.firmware ? `FW ${v.firmware}` : "";
        const sel = card.querySelector('[data-role="override"]');
        if (sel && document.activeElement !== sel) sel.value = String(v.override);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.setpoint, 1)} %`;
      }

      if (m.type === "grundfos") {
        setText(card, "flow", num(v.flow, 2));
        setText(card, "flowsub", `${num(v.rel_perf, 0)} % van max · ${v.mode_txt || ""} · ${v.controlmode_txt || ""}`);
        setText(card, "head", num(v.head, 2));
        setText(card, "rpm", num(v.rpm, 0));
        setText(card, "freq", num(v.freq, 1));
        setText(card, "amp", num(v.current, 1));
        setText(card, "temp", num(v.temp_liquid, 1));
        const on = card.querySelector('[data-role="onchip"]');
        if (on) { on.textContent = v.on ? "AAN" : "UIT"; on.className = "chip " + (v.on ? "ok" : ""); }
        const rem = card.querySelector('[data-role="remotechip"]');
        if (rem) { rem.textContent = v.remote ? "Remote" : "Lokaal"; rem.className = "chip " + (v.remote ? "blue" : ""); }
        const al = card.querySelector('[data-role="alarmchip"]');
        if (al) {
          al.textContent = v.alarm ? `Alarm ${v.alarm_code}` : (v.warning ? `Waarschuwing ${v.warning_code}` : "Geen alarm");
          al.className = "chip " + (v.alarm ? "err" : "ok");
        }
        const sw = card.querySelector('[data-role="onoff"]');
        if (sw && document.activeElement !== sw) sw.checked = !!v.on;
        const sel = card.querySelector('[data-role="mode"]');
        if (sel && document.activeElement !== sel) sel.value = String(v.mode);
        const cm = card.querySelector('[data-role="controlmode"]');
        if (cm && document.activeElement !== cm) cm.value = String(v.controlmode_actual ?? v.controlmode);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.setpoint, 0)} %`;
      }

      if (m.type === "wilo_stratos") {
        setText(card, "flow", num(v.flow, 2));
        setText(card, "flowsub", `${num(v.head, 2)} m opvoerhoogte · ${num(v.power, 0)} W`);
        setText(card, "head", num(v.head, 2));
        setText(card, "speed", num(v.speed, 0));
        setText(card, "power", num(v.power, 0));
        setText(card, "temp", num(v.temp, 1));
        const on = card.querySelector('[data-role="onchip"]');
        if (on) { on.textContent = v.on ? "AAN" : "UIT"; on.className = "chip " + (v.on ? "ok" : ""); }
        const cm = card.querySelector('[data-role="cmchip"]');
        if (cm) cm.textContent = v.controlmode_txt || "—";
        const al = card.querySelector('[data-role="alarmchip"]');
        if (al) {
          al.textContent = v.error ? `Fout ${v.error}` : "Geen fout";
          al.className = "chip " + (v.error ? "err" : "ok");
        }
        const sw = card.querySelector('[data-role="onoff"]');
        if (sw && document.activeElement !== sw) sw.checked = !!v.on;
        const sel = card.querySelector('[data-role="controlmode"]');
        if (sel && document.activeElement !== sel) sel.value = String(v.controlmode);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.setpoint, 1)} %`;
      }

      if (m.type === "lg_ub40") {
        setText(card, "tout", num(v.t_out, 1));
        setText(card, "flowsub", `buiten ${num(v.t_outdoor, 1)} °C · ${v.mode_txt || ""} · ${num(v.flow, 1)} l/min`);
        setText(card, "tin", num(v.t_in, 1));
        setText(card, "toutdoor", num(v.t_outdoor, 1));
        setText(card, "tdhw", num(v.t_dhw, 1));
        setText(card, "flowrate", num(v.flow, 1));
        setText(card, "pressure", num(v.pressure, 2));
        const on = card.querySelector('[data-role="onchip"]');
        if (on) { on.textContent = v.on ? "AAN" : "UIT"; on.className = "chip " + (v.on ? "ok" : ""); }
        const mc = card.querySelector('[data-role="modechip"]');
        if (mc) { mc.textContent = v.mode_txt || "—"; mc.className = "chip blue"; }
        const cc = card.querySelector('[data-role="compchip"]');
        if (cc) { cc.textContent = v.compressor ? "Compressor" : "Compressor uit"; cc.className = "chip " + (v.compressor ? "ok" : ""); }
        const al = card.querySelector('[data-role="alarmchip"]');
        if (al) {
          al.textContent = v.error ? `Fout ${v.error}` : (v.defrost ? "Ontdooien" : "Geen alarm");
          al.className = "chip " + (v.error ? "err" : "ok");
        }
        const sw = card.querySelector('[data-role="onoff"]');
        if (sw && document.activeElement !== sw) sw.checked = !!v.on;
        const sel = card.querySelector('[data-role="lgmode"]');
        if (sel && document.activeElement !== sel) sel.value = String(v.mode);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.target, 1)} °C`;
        const dhw = card.querySelector('[data-role="dhw"]');
        if (dhw && document.activeElement !== dhw) dhw.placeholder = `${num(v.dhw_target, 1)} °C`;
      }

      if (m.type === "belimo_ev" || m.type === "belimo_epiv2" || m.type === "belimo_epiv6") {
        setText(card, "flow", num(v.flow, 2));
        let sub = `klep ${num(v.position, 0)} % open`;
        if (m.type === "belimo_ev") sub = `${num(v.power, 2)} kW · ΔT ${num(v.dt, 1)} K · klep ${num(v.position, 0)} %`;
        else if (m.type === "belimo_epiv2") sub += ` · setpunt ${num(v.setpoint, 0)} %`;
        else if (m.type === "belimo_epiv6") sub += ` · Vmax ${num(v.vmax1, 0)} / ${num(v.vmax2, 0)} m³/h`;
        setText(card, "flowsub", sub);
        const bar = card.querySelector('[data-role="posbar"]');
        if (bar) bar.style.width = `${Math.max(0, Math.min(100, v.position || 0))}%`;
        const ov = card.querySelector('[data-role="ovchip"]');
        if (ov) { ov.textContent = v.override_txt || "Auto"; ov.className = "chip " + (v.override ? "blue" : "ok"); }
        const cm = card.querySelector('[data-role="cmchip"]');
        if (cm) cm.textContent = v.controlmode_txt || "—";
        const fw = card.querySelector('[data-role="fwchip"]');
        if (fw) fw.textContent = v.firmware ? `FW ${v.firmware}` : "";
        const seq = card.querySelector('[data-role="seqchip"]');
        if (seq) seq.textContent = v.sequence ? `Seq ${v.sequence}` : "—";
        const sel = card.querySelector('[data-role="override"]');
        if (sel && document.activeElement !== sel) sel.value = String(v.override);
        const sp = card.querySelector('[data-role="setpoint"]');
        if (sp && document.activeElement !== sp) sp.placeholder = `${num(v.setpoint, 0)} %`;
        if (m.type === "belimo_ev") {
          setText(card, "t1", num(v.t1, 1));
          setText(card, "t2", num(v.t2, 1));
          setText(card, "dt", num(v.dt, 1));
          setText(card, "power", num(v.power, 2));
        }
      }
    }
  }

  // ------------------------------------------------------------------ config
  function payload() {
    return {
      bus: {
        port: $("#port").value,
        baud: Number($("#baud").value),
        parity: $("#parity").value,
        stopbits: Number($("#stopbits").value),
        interval: state ? state.bus.interval : 10,
        timeout: state ? state.bus.timeout : 0.5,
        debug: $("#trace-toggle").checked,
      },
      modules: (state ? state.modules : []).map((m) => ({
        id: m.id, type: m.type, address: m.address, label: m.label || "",
        transport: m.transport || "rtu", ip: m.ip || "", port: m.port || 502,
        points: m.points || [],
        unit: m.type === "clivet_slave" ? m.unit : undefined,
      })),
    };
  }

  async function saveConfig() {
    try {
      const s = await api("/api/config", { method: "POST", body: JSON.stringify(payload()) });
      applyState(s);
    } catch (err) {
      toast("Opslaan mislukt: " + err.message, "err");
    }
  }

  async function doAction(id, op, extra = {}) {
    try {
      const res = await api("/api/action", {
        method: "POST",
        body: JSON.stringify({ id, op, ...extra }),
      });
      if (state) {
        const mod = state.modules.find((m) => m.id === id);
        if (mod) mod.state = res.state;
        updateModules(state.modules);
      }
    } catch (err) {
      toast(err.message, "err");
    }
  }

  // ------------------------------------------------------------------ reeks
  function seriesPreview() {
    const from = Math.max(1, Math.min(247, parseInt($("#series-from").value, 10) || 1));
    const count = Math.max(1, Math.min(32, parseInt($("#series-count").value, 10) || 1));
    const to = Math.min(247, from + count - 1);
    $("#series-note").textContent = `${count} module${count === 1 ? "" : "s"} op adres ${from}${count > 1 ? "–" + to : ""}.`;
  }

  function openSeries() {
    const sel = $("#series-type");
    sel.innerHTML = Object.entries(TYPES).map(([k, t]) => `<option value="${k}">${esc(t.name)}</option>`).join("");
    sel.value = "em18u";
    $("#series-from").value = nextAddress();
    $("#series-count").value = 13;
    seriesPreview();
    $("#series-modal").classList.add("show");
    $("#series-from").focus();
  }

  function closeSeries() { $("#series-modal").classList.remove("show"); }

  // ------------------------------------------------------------------ algemene deelnemer
  let pointTarget = null;

  function openPointModal(id) {
    pointTarget = id;
    ["pt-name", "pt-unit"].forEach((f) => ($("#" + f).value = ""));
    $("#pt-addr").value = 0;
    $("#pt-scale").value = 1;
    $("#pt-offset").value = 0;
    $("#pt-fc").value = "3";
    $("#pt-type").value = "u16";
    $("#pt-order").value = "AB";
    $("#pt-ctrl").value = "input";
    $("#pt-swap").checked = false;
    $("#pt-rw").checked = false;
    $("#point-modal").classList.add("show");
  }

  function closePointModal() { $("#point-modal").classList.remove("show"); pointTarget = null; }

  function addPoint() {
    const mod = state && state.modules.find((m) => m.id === pointTarget);
    if (!mod) { closePointModal(); return; }
    const fc = Number($("#pt-fc").value);
    const pt = {
      id: Math.random().toString(16).slice(2, 8),
      name: $("#pt-name").value.trim(),
      fc,
      addr: Number($("#pt-addr").value) || 0,
      type: $("#pt-type").value,
      order: $("#pt-order").value,
      swap: $("#pt-swap").checked,
      scale: Number($("#pt-scale").value) || 1,
      offset: Number($("#pt-offset").value) || 0,
      unit: $("#pt-unit").value.trim(),
      rw: $("#pt-rw").checked,
      ctrl: $("#pt-ctrl").value,
    };
    if (fc === 1 || fc === 2) pt.type = "bit";
    mod.points = [...(mod.points || []), pt];
    closePointModal();
    topologySig = null;
    renderTopology(state.modules);
    saveConfig();
    toast("Punt toegevoegd", "ok");
  }

  // ------------------------------------------------------------------ BACnet/IP
  const BN_WRITABLE = new Set([1, 2, 4, 5, 14, 19]);
  const BN_BINARY = new Set([3, 4, 8]);
  let bnDevices = [];
  let bnCurrent = null;

  function bnValueText(p) {
    if (!p.ok) return "—";
    if (typeof p.value === "boolean") return p.value ? "AAN" : "UIT";
    if (typeof p.value === "number") return Number.isInteger(p.value) ? String(p.value) : num(p.value, 2);
    return String(p.value ?? "—");
  }

  async function bnInit() {
    try {
      const res = await api("/api/bacnet/subnets");
      const nets = res.broadcasts || [];
      if (!$("#bn-subnet").value && nets.length) $("#bn-subnet").value = nets[0];
      $("#bn-hint").textContent = nets.length
        ? `deze machine: ${nets.join(", ")}`
        : "geen IPv4-interface gevonden";
    } catch (err) {
      $("#bn-hint").textContent = "";
    }
  }

  async function bnScan() {
    const subnet = $("#bn-subnet").value.trim();
    $("#bn-status").textContent = "bezig met zoeken…";
    $("#bn-scan").disabled = true;
    try {
      const res = await api(`/api/bacnet/whois?subnet=${encodeURIComponent(subnet)}`);
      bnDevices = res.devices || [];
      $("#bn-status").textContent = bnDevices.length ? `${bnDevices.length} toestel(len)` : "geen toestel gevonden";
    } catch (err) {
      bnDevices = [];
      $("#bn-status").textContent = "fout: " + err.message;
    } finally {
      $("#bn-scan").disabled = false;
      bnRenderDevices();
    }
  }

  function bnRenderDevices() {
    const host = $("#bn-devices");
    if (!bnDevices.length) { host.innerHTML = ""; return; }
    host.innerHTML = bnDevices.map((d, i) => `
      <button class="bndev" data-i="${i}">
        <span class="bndev-id">${d.device}</span>
        <span class="bndev-main"><b>${esc(d.name || "(naamloos)")}</b>
          <i>${esc(d.ip)} · vendor ${d.vendor}${d.model ? " · " + esc(d.model) : ""}</i></span>
        <span class="bndev-go">punten →</span>
      </button>`).join("");
  }

  function bnEdeHref() {
    if (!bnCurrent) return;
    const project = $("#bn-project").value.trim() || `Device${bnCurrent.device}`;
    $("#bn-ede").href = `/api/bacnet/ede.zip?ip=${encodeURIComponent(bnCurrent.ip)}`
      + `&device=${bnCurrent.device}&project=${encodeURIComponent(project)}`;
  }

  async function bnLoadPoints(dev) {
    bnCurrent = dev;
    $("#bn-detail").hidden = false;
    $("#bn-title").textContent = `Device ${dev.device} — ${dev.name || "(naamloos)"} · ${dev.ip}`;
    const project = dev.name || `Device${dev.device}`;
    $("#bn-project").value = project;
    bnEdeHref();
    $("#bn-points").innerHTML = `<div class="pempty">punten ophalen…</div>`;
    try {
      const res = await api("/api/bacnet/points", { method: "POST", body: JSON.stringify({ ip: dev.ip, device: dev.device }) });
      bnRenderPoints(res.points || []);
      toast(`${(res.points || []).length} punten gelezen`, "ok");
    } catch (err) {
      $("#bn-points").innerHTML = `<div class="pempty">fout: ${esc(err.message)}</div>`;
    }
  }

  function bnRenderPoints(points) {
    if (!points.length) { $("#bn-points").innerHTML = `<div class="pempty">geen objecten</div>`; return; }
    $("#bn-points").innerHTML = `
      <div class="bnh">Type</div><div class="bnh">Object</div><div class="bnh">Waarde</div><div class="bnh">Actie</div>` +
      points.map((p) => {
        const writable = BN_WRITABLE.has(p.type);
        let actie = "";
        if (writable && BN_BINARY.has(p.type)) {
          actie = `<button class="btn tiny" data-bnw="on" data-t="${p.type}" data-i="${p.inst}">AAN</button>
                   <button class="btn tiny ghost" data-bnw="off" data-t="${p.type}" data-i="${p.inst}">UIT</button>`;
        } else if (writable) {
          actie = `<input class="pin" type="number" step="any" data-bnin="${p.type}-${p.inst}">
                   <button class="btn tiny primary" data-bnw="set" data-t="${p.type}" data-i="${p.inst}">Zet</button>`;
        } else {
          actie = `<span class="bnro">lezen</span>`;
        }
        return `<div class="bnr">
            <span class="bnt">${esc(p.abbr)}</span>
            <span class="bnn">${esc(p.name || `instance ${p.inst}`)}<i>${p.abbr},${p.inst}</i></span>
            <span class="bnv ${p.ok ? "" : "bad"}">${esc(bnValueText(p))}${p.unit ? " " + esc(p.unit) : ""}</span>
            <span class="bna">${actie}</span>
          </div>`;
      }).join("");
  }

  async function bnWrite(type, inst, value) {
    if (!bnCurrent) return;
    try {
      const res = await api("/api/bacnet/write", { method: "POST", body: JSON.stringify({ ip: bnCurrent.ip, type, inst, value }) });
      toast(`geschreven → ${res.value}`, "ok");
      bnLoadPoints(bnCurrent);
    } catch (err) {
      toast("schrijven mislukt: " + err.message, "err");
    }
  }

  function applyTab() {
    localStorage.setItem("ml-tab", activeTab);
    document.querySelectorAll("#tabs .tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === activeTab));
    const isBn = activeTab === "bacnet";
    if (isBn) bnInit();
    $("#busbar").style.display = activeTab === "rtu" ? "" : "none";
    $("#bacnet-panel").hidden = !isBn;
    $("#bacnet-panel").style.display = isBn ? "" : "none";
    document.querySelector(".canvas-panel").style.display = isBn ? "none" : "";
    document.querySelector(".palette").style.display = isBn ? "none" : "";
    const isTcpTab = activeTab === "tcp";
    document.querySelector(".canvas-head h2").textContent = isTcpTab ? "Modbus TCP/IP" : "Modbus-lijn";
    document.querySelector(".canvas-head .hint").textContent = isTcpTab
      ? "TCP · elk toestel zijn eigen IP" : "RS-485 · 2-draads";
    document.querySelector(".trunk").style.display = isTcpTab ? "none" : "";
    document.querySelector(".trunk-label").style.display = isTcpTab ? "none" : "";
    $("#tab-note").textContent = {
      rtu: "RS-485 · één framing per lijn",
      tcp: "Modbus TCP · elk toestel zijn eigen IP",
      bacnet: "BACnet/IP · UDP 47808",
    }[activeTab];
    topologySig = null;
    renderPalette();
    if (state) {
      renderTopology(state.modules);
      updateModules(state.modules);
      renderStatus(state);
    }
  }

  async function addSeries() {
    const type = $("#series-type").value;
    const from = Math.max(1, Math.min(247, parseInt($("#series-from").value, 10) || 1));
    const count = Math.max(1, Math.min(32, parseInt($("#series-count").value, 10) || 1));
    if (from + count - 1 > 247) { toast("Reeks loopt voorbij adres 247", "err"); return; }
    const used = new Set(state.modules.map((m) => m.address));
    for (let i = 0; i < count; i++) {
      if (used.has(from + i)) { toast(`Adres ${from + i} is al bezet`, "err"); return; }
    }
    const mods = [...state.modules];
    for (let i = 0; i < count; i++) {
      mods.push({
        id: Math.random().toString(16).slice(2, 10),
        type, address: from + i, label: "",
        type_meta: TYPES[type], state: { ok: false, error: "nog niet gelezen" },
      });
    }
    state.modules = mods;
    topologySig = null;
    renderTopology(mods);
    updateModules(mods);
    closeSeries();
    await saveConfig();
    toast(`${count} × ${TYPES[type].name} toegevoegd (${from}–${from + count - 1})`, "ok");
  }

  // ------------------------------------------------------------------ modules
  function nextAddress() {
    const used = new Set((state ? state.modules : []).map((m) => m.address));
    for (let a = 1; a <= 247; a++) if (!used.has(a)) return a;
    return 1;
  }

  async function addModule(type, index) {
    if (!state) return;
    const id = Math.random().toString(16).slice(2, 10);
    const mod = { id, type, address: nextAddress(), label: "", type_meta: TYPES[type], state: { ok: false, error: "nog niet gelezen" } };
    if (TYPES[type].transport === "tcp" || activeTab === "tcp") { mod.transport = "tcp"; mod.ip = ""; mod.port = 502; }
    if (type === "generic") mod.points = [];
    if (type === "clivet_slave") {
      const master = state.modules.find((m) => m.type === "clivet");
      if (master) mod.address = master.address;
      mod.unit = 1;
    }
    const mods = [...state.modules];
    mods.splice(index == null ? mods.length : index, 0, mod);
    state.modules = mods;
    topologySig = null;
    renderTopology(mods);
    updateModules(mods);
    await saveConfig();
    toast(`${TYPES[type].name} toegevoegd op adres ${mod.address}`, "ok");
  }

  async function moveModule(id, index) {
    if (!state) return;
    const mods = [...state.modules];
    const from = mods.findIndex((m) => m.id === id);
    if (from < 0) return;
    const [m] = mods.splice(from, 1);
    if (index > from) index -= 1;
    mods.splice(Math.max(0, Math.min(mods.length, index)), 0, m);
    state.modules = mods;
    topologySig = null;
    renderTopology(mods);
    updateModules(mods);
    await saveConfig();
  }

  // ------------------------------------------------------------------ events
  function bindControls() {
    const field = $("#linefield");
    const line = $("#insertline");

    field.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      field.classList.add("dragover");
      const idx = dropIndex(e.clientX);
      const cards = $$(".card", $("#modules"));
      const scroller = $("#linescroll");
      const fr = scroller.getBoundingClientRect();
      let x;
      if (cards.length === 0) x = 18;
      else if (idx < cards.length) x = cards[idx].getBoundingClientRect().left - fr.left + scroller.scrollLeft - 9;
      else x = cards[cards.length - 1].getBoundingClientRect().right - fr.left + scroller.scrollLeft + 6;
      line.style.display = "block";
      line.style.left = `${x}px`;
    });
    field.addEventListener("dragleave", (e) => {
      if (e.relatedTarget && field.contains(e.relatedTarget)) return;
      field.classList.remove("dragover");
      line.style.display = "none";
    });
    field.addEventListener("drop", (e) => {
      e.preventDefault();
      field.classList.remove("dragover");
      line.style.display = "none";
      const idx = dropIndex(e.clientX);
      const type = e.dataTransfer.getData("text/x-module");
      const mid = e.dataTransfer.getData("text/x-module-id");
      if (type && TYPES[type]) addModule(type, idx);
      else if (mid) moveModule(mid, idx);
    });

    $("#modules").addEventListener("dragstart", (e) => {
      const grip = e.target.closest("[data-drag]");
      if (!grip) { e.preventDefault(); return; }
      const card = grip.closest(".card");
      e.dataTransfer.setData("text/x-module-id", card.dataset.id);
      e.dataTransfer.effectAllowed = "move";
      card.style.opacity = ".5";
      setTimeout(() => (card.style.opacity = ""), 400);
    });

    $("#modules").addEventListener("click", (e) => {
      const card = e.target.closest(".card");
      if (!card) return;
      const id = card.dataset.id;
      const mod = state.modules.find((m) => m.id === id);
      if (!mod) return;

      if (e.target.closest('[data-act="addpoint"]')) {
        openPointModal(id);
        return;
      }
      if (e.target.closest('[data-act="pdel"]')) {
        const btn = e.target.closest('[data-act="pdel"]');
        const pts = (mod.points || []).filter((p) => String(p.id) !== String(btn.dataset.pid));
        mod.points = pts;
        topologySig = null;
        renderTopology(state.modules);
        saveConfig();
        return;
      }
      if (e.target.closest('[data-act="pwrite"]')) {
        const btn = e.target.closest('[data-act="pwrite"]');
        const pid = btn.dataset.pid;
        let val = btn.dataset.val;
        if (val == null) {
          const inp = btn.closest(".prow").querySelector('[data-pin]');
          val = inp ? inp.value : "";
          if (val === "") { toast("Vul een waarde in", "err"); return; }
        }
        doAction(id, "write_point", { pid, value: Number(val) });
        return;
      }
      if (e.target.closest('[data-act="clearerr"]')) {
        doAction(id, "clear_errors", {});
        return;
      }
      if (e.target.closest('[data-act="clearalarm"]')) {
        if (confirm(`Alarmen van adres ${mod.address} wissen?`)) doAction(id, "clear_alarms", {});
        return;
      }
      if (e.target.closest('[data-act="resume"]')) {
        doAction(id, "resume", {});
        return;
      }
      if (e.target.closest('[data-act="local"]') || e.target.closest('[data-act="remote"]')) {
        const remote = !!e.target.closest('[data-act="remote"]');
        doAction(id, "set_remote", { value: remote ? 1 : 0 });
        return;
      }
      if (e.target.closest('[data-act="setvlim"]')) {
        const c = e.target.closest(".card");
        const vmin = parseFloat(c.querySelector('[data-role="vmin"]').value);
        const vmax = parseFloat(c.querySelector('[data-role="vmax"]').value);
        if (!isFinite(vmin) || !isFinite(vmax)) { toast("Vul Vmin en Vmax in", "err"); return; }
        if (vmin > vmax) { toast("Vmin mag niet groter zijn dan Vmax", "err"); return; }
        doAction(id, "set_vminmax", { vmin, vmax });
        return;
      }
      if (e.target.closest('[data-act="setvmax"]')) {
        const c = e.target.closest(".card");
        const seq1 = parseFloat(c.querySelector('[data-role="vmax1"]').value);
        const seq2 = parseFloat(c.querySelector('[data-role="vmax2"]').value);
        if (!isFinite(seq1) || !isFinite(seq2)) { toast("Vul beide V'max-waarden in", "err"); return; }
        doAction(id, "set_vmax_seq", { seq1, seq2 });
        return;
      }
      if (e.target.closest('[data-act="baudauto"]')) {
        if (confirm(`Adres ${mod.address}: framing terug op Auto zetten?\n\nDe module herstart (~6 s) en detecteert daarna zelf opnieuw. De signaaltypes blijven bewaard, dus de volgende integrator kan met elke baudrate werken.`)) {
          doAction(id, "baud_auto", {});
        }
        return;
      }
      if (e.target.closest('[data-act="factory"]')) {
        if (confirm(`FACTORY RESET van adres ${mod.address}?\n\nAlle terminalconfiguratie (signaaltypes) wordt gewist en de module herstart (~6 s). Alleen doen als de module toch leeg de kast uit gaat.`)) {
          doAction(id, "factory_reset", {});
        }
        return;
      }
      if (e.target.closest('[data-act="del"]')) {
        state.modules = state.modules.filter((m) => m.id !== id);
        topologySig = null;
        renderTopology(state.modules);
        updateModules(state.modules);
        saveConfig();
        return;
      }
      if (e.target.closest('[data-act="setsp"]')) {
        const input = card.querySelector('[data-role="setpoint"]');
        const val = parseFloat(input.value);
        if (!isFinite(val)) { toast("Vul een setpunt in", "err"); return; }
        doAction(id, "set_setpoint", { value: val });
        return;
      }
      if (e.target.closest('[data-act="setdhw"]')) {
        const input = card.querySelector('[data-role="dhw"]');
        const val = parseFloat(input.value);
        if (!isFinite(val)) { toast("Vul een DHW-setpunt in", "err"); return; }
        doAction(id, "set_dhw", { value: val });
        return;
      }
      if (e.target.closest('[data-act="setao"]')) {
        const uio = e.target.closest(".uio");
        const input = uio.querySelector('[data-role="aoval"]');
        const val = parseFloat(input.value);
        if (!isFinite(val)) { toast("Vul een uitgangsspanning in", "err"); return; }
        doAction(id, "set_ao", { ch: Number(uio.dataset.ch), value: val });
        return;
      }
      const io = e.target.closest(".io[data-role='do']");
      if (io && mod.state && mod.state.ok) {
        const ch = Number(io.dataset.ch);
        const now = io.classList.contains("on") ? 1 : 0;
        doAction(id, "toggle_do", { ch, value: now ? 0 : 1 });
      }
    });

    $("#modules").addEventListener("change", (e) => {
      const card = e.target.closest(".card");
      if (!card) return;
      const id = card.dataset.id;
      const role = e.target.dataset.role;
      const mod = state.modules.find((m) => m.id === id);

      if (role === "address") {
        let v = parseInt(e.target.value, 10);
        if (!isFinite(v)) v = 1;
        v = Math.max(1, Math.min(247, v));
        e.target.value = v;
        if (mod) mod.address = v;
        saveConfig();
        return;
      }
      if (role === "stype") {
        const ch = Number(e.target.closest(".uio").dataset.ch);
        doAction(id, "set_type", { ch, value: Number(e.target.value) });
        return;
      }
      if (role === "override") {
        doAction(id, "set_override", { value: Number(e.target.value) });
        return;
      }
      if (role === "ip") {
        if (mod) mod.ip = e.target.value.trim();
        saveConfig();
        return;
      }
      if (role === "unit" && mod?.type === "clivet_slave") {
        mod.unit = Math.max(1, Math.min(8, Number(e.target.value) || 1));
        e.target.value = mod.unit;
        saveConfig();
        toast(`Slave-tegel leest nu unit ${mod.unit}`, "ok");
        return;
      }
      if (role === "onoff" && ["carrier_sms", "clivet", "daikin"].includes(mod?.type)) {
        doAction(id, "set_onoff", { value: e.target.checked ? 1 : 0 });
        return;
      }
      if (role === "cmode" && ["carrier_sms", "clivet"].includes(mod?.type)) {
        doAction(id, "set_mode", { value: Number(e.target.value) });
        return;
      }
      if (role === "dmode" && mod?.type === "daikin") {
        doAction(id, "set_mode", { value: Number(e.target.value) });
        return;
      }
      if (role === "mode") {
        doAction(id, "set_mode", { value: Number(e.target.value) });
        return;
      }
      if (role === "controlmode") {
        doAction(id, "set_controlmode", { value: Number(e.target.value) });
        return;
      }
      if (role === "lgmode") {
        doAction(id, "set_mode", { value: Number(e.target.value) });
        return;
      }
      if (role === "onoff") {
        doAction(id, "set_onoff", { value: e.target.checked ? 1 : 0 });
      }
    });

    $("#modules").addEventListener("keydown", (e) => {
      if (e.target.dataset.role === "address" && e.key === "Enter") e.target.blur();
    });

    for (const id of ["#port", "#baud", "#parity", "#stopbits"]) {
      $(id).addEventListener("change", saveConfig);
    }

    $("#btn-series").addEventListener("click", openSeries);
    $("#series-cancel").addEventListener("click", closeSeries);
    $("#series-ok").addEventListener("click", addSeries);
    $("#tabs").addEventListener("click", (e) => {
      const tab = e.target.closest(".tab");
      if (!tab || tab.dataset.tab === activeTab) return;
      activeTab = tab.dataset.tab;
      applyTab();
    });
    $("#bn-scan").addEventListener("click", bnScan);
    $("#bn-devices").addEventListener("click", (e) => {
      const btn = e.target.closest(".bndev");
      if (btn) bnLoadPoints(bnDevices[Number(btn.dataset.i)]);
    });
    $("#bn-refresh").addEventListener("click", () => { if (bnCurrent) bnLoadPoints(bnCurrent); });
    $("#bn-project").addEventListener("input", bnEdeHref);
    $("#bn-points").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-bnw]");
      if (!btn) return;
      const type = Number(btn.dataset.t);
      const inst = Number(btn.dataset.i);
      if (btn.dataset.bnw === "on") return bnWrite(type, inst, 1);
      if (btn.dataset.bnw === "off") return bnWrite(type, inst, 0);
      const inp = $("#bn-points").querySelector(`[data-bnin="${type}-${inst}"]`);
      if (!inp || inp.value === "") { toast("Vul een waarde in", "err"); return; }
      bnWrite(type, inst, Number(inp.value));
    });
    $("#point-modal").addEventListener("click", (e) => { if (e.target.id === "point-modal") closePointModal(); });
    $("#pt-cancel").addEventListener("click", closePointModal);
    $("#pt-ok").addEventListener("click", addPoint);
    $("#pt-fc").addEventListener("change", () => {
      const fc = Number($("#pt-fc").value);
      $("#pt-type").value = (fc === 1 || fc === 2) ? "bit" : "u16";
      $("#pt-rw").checked = fc === 1 || fc === 3;
    });
    $("#series-modal").addEventListener("click", (e) => { if (e.target.id === "series-modal") closeSeries(); });
    for (const sel of ["#series-from", "#series-count"]) $(sel).addEventListener("input", seriesPreview);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#series-modal").classList.contains("show")) closeSeries();
    });

    $("#btn-reconnect").addEventListener("click", async () => {
      const btn = $("#btn-reconnect");
      btn.disabled = true;
      try {
        await saveConfig();
        const s = await api("/api/reconnect", { method: "POST", body: "{}" });
        applyState(s);
        toast("Poort heropend", "ok");
      } catch (err) {
        toast("Verbinding mislukt: " + err.message, "err");
      } finally {
        btn.disabled = false;
      }
    });

    $("#btn-framing").addEventListener("click", async () => {
      const btn = $("#btn-framing");
      const addr = Math.max(1, Math.min(247, parseInt($("#scan-from").value, 10) || 1));
      btn.disabled = true;
      btn.textContent = "Zoeken…";
      try {
        const res = await api("/api/framing", { method: "POST", body: JSON.stringify({ address: addr }) });
        if (res.state) applyState(res.state);
        if (res.applied) {
          toast(`Adres ${addr} antwoordt op ${res.applied.baud} 8${res.applied.parity}${res.applied.stopbits}`, "ok");
        } else {
          toast(`Geen framing gevonden op adres ${addr}`, "err");
        }
      } catch (err) {
        toast("Framing-zoektocht mislukt: " + err.message, "err");
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h10M4 12h16M4 17h7"/><circle cx="18" cy="7" r="2"/><circle cx="14" cy="17" r="2"/></svg> Framing`;
      }
    });

    $("#btn-scan").addEventListener("click", async () => {
      const btn = $("#btn-scan");
      const from = Math.max(1, Math.min(247, parseInt($("#scan-from").value, 10) || 1));
      const to = Math.max(from, Math.min(247, parseInt($("#scan-to").value, 10) || from));
      $("#scan-from").value = from;
      $("#scan-to").value = to;
      btn.disabled = true;
      btn.textContent = "Scannen…";
      try {
        const res = await api("/api/scan", { method: "POST", body: JSON.stringify({ start: from, end: to }) });
        renderScan(res.found, from, to);
      } catch (err) {
        toast("Scan mislukt: " + err.message, "err");
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg> Scan adressen`;
      }
    });
  }

  function dropIndex(clientX) {
    const cards = $$(".card", $("#modules"));
    for (let i = 0; i < cards.length; i++) {
      const r = cards[i].getBoundingClientRect();
      if (clientX < r.left + r.width / 2) return i;
    }
    return cards.length;
  }

  function renderScan(found, from = 1, to = 32) {
    const bar = $("#scanbar");
    if (!found || !found.length) {
      bar.className = "scanbar show";
      bar.innerHTML = `<span class="lbl">Scan ${from}–${to}</span><span class="scanhit">Geen modules gevonden — check bedrading, baudrate en pariteit.</span>`;
      return;
    }
    bar.className = "scanbar show";
    bar.innerHTML = `<span class="lbl">Scan ${from}–${to} · gevonden</span>` + found.map((h) => {
      const conf = Number(h.confidence ?? 0);
      const cls = conf >= 90 ? "high" : conf >= 70 ? "mid" : "low";
      return `
      <span class="scanhit"><b>${h.address}</b> ${esc(h.name)}
        <span class="conf ${cls}" title="${esc(h.reason || "")}">${conf}%</span>
        <button data-addr="${h.address}" data-mtype="${h.type}">+ toevoegen</button>
      </span>`;
    }).join("");
    bar.querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
      await addModule(b.dataset.mtype, null);
      const mods = state.modules;
      const last = mods[mods.length - 1];
      last.address = Number(b.dataset.addr);
      await saveConfig();
      b.closest(".scanhit").remove();
    }));
  }

  // ------------------------------------------------------------------ log
  function renderLog() {
    const wrap = $("#logwrap");
    const body = $("#logbody");
    $("#logcount").textContent = state ? `${state.log.length}` : "";
    if (!wrap.classList.contains("open") || !state) return;
    body.innerHTML = state.log.map((l) => `
      <div class="logline ${esc(l.level)}">
        <time>${clock(l.ts)}</time>
        <span class="lvl">${esc(l.level.toUpperCase())}</span>
        <span class="msg">${esc(l.msg)}</span>
      </div>`).join("") || `<div class="logline"><span class="msg">Nog geen gebeurtenissen.</span></div>`;
  }

  boot();
})();
