/* ── PulseXI – Frontend Application ───────────────────────────────── */
import { initPitch3D } from "./pitch3d.js";

const API_BASE = (location.port && location.port !== "8010") ? "http://localhost:8010" : "";

const state = {
  matchId: null,
  meta: null,
  players: {},
  events: [],
  cues: [],
  minuteSnapshots: [],
  clock: 0,        // seconds into the match (0..~5700)
  maxClock: 5400,
  playing: false,
  speed: 40,
  shownCueIds: new Set(),
  playerSlots: {},  // playerId -> { baseX, baseY, teamId, phase, number }
  followBall: false,
};

let pitch3d = null;

const el = (id) => document.getElementById(id);

// Must match backend/data/generator.py FORMATION_POSITIONS order exactly —
// each squad is built GK, CB, CB, LB, RB, CM, CM, CDM, LW, RW, ST.
const FORMATION_SLOTS = [
  { x: 0.05, y: 0.50 }, // GK
  { x: 0.20, y: 0.32 }, // CB1
  { x: 0.20, y: 0.68 }, // CB2
  { x: 0.24, y: 0.10 }, // LB
  { x: 0.24, y: 0.90 }, // RB
  { x: 0.46, y: 0.30 }, // CM1
  { x: 0.46, y: 0.70 }, // CM2
  { x: 0.38, y: 0.50 }, // CDM
  { x: 0.74, y: 0.14 }, // LW
  { x: 0.72, y: 0.86 }, // RW
  { x: 0.80, y: 0.50 }, // ST
];

function phaseFor(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 1000;
  return h / 1000 * Math.PI * 2;
}

function buildPlayers3D() {
  state.playerSlots = {};
  hidePlayerPopup();

  const playersInfo = {};
  for (const teamId of [state.meta.home.id, state.meta.away.id]) {
    const squad = Object.values(state.players).filter((p) => p.team_id === teamId);
    squad.forEach((p, i) => {
      const slot = FORMATION_SLOTS[i] || FORMATION_SLOTS[FORMATION_SLOTS.length - 1];
      const isHome = teamId === state.meta.home.id;
      const baseX = isHome ? slot.x * 100 : 100 - slot.x * 100;
      const baseY = slot.y * 100;
      const number = i + 1;

      state.playerSlots[p.id] = { baseX, baseY, teamId, phase: phaseFor(p.id), number };
      playersInfo[p.id] = { teamId, isGK: p.position === "GK", number };
    });
  }
  pitch3d.buildPlayers(playersInfo, state.meta.home.id);
}

function updatePlayerPositions(latestEvent) {
  const homeId = state.meta.home.id;
  const ballXFrac = (latestEvent ? latestEvent.x : 50) / 100;
  const shiftHome = Math.max(-0.12, Math.min(0.12, (ballXFrac - 0.5) * 0.4));
  const shiftAway = Math.max(-0.12, Math.min(0.12, (0.5 - ballXFrac) * 0.4));
  const involvedId = latestEvent ? (latestEvent.player_id || null) : null;

  const positions = {};
  for (const [pid, slot] of Object.entries(state.playerSlots)) {
    if (pid === involvedId && latestEvent) {
      positions[pid] = { xPct: latestEvent.x, yPct: latestEvent.y };
      continue;
    }
    const shift = slot.teamId === homeId ? shiftHome : -shiftAway;
    const jitterX = Math.sin(state.clock * 0.5 + slot.phase) * 1.4;
    const jitterY = Math.cos(state.clock * 0.4 + slot.phase) * 1.4;
    positions[pid] = {
      xPct: Math.max(2, Math.min(98, slot.baseX + shift * 100 + jitterX)),
      yPct: Math.max(4, Math.min(96, slot.baseY + jitterY)),
    };
  }
  pitch3d.updatePlayers(positions, involvedId);
}

const BCP47 = { en: "en-US", es: "es-ES", fr: "fr-FR" };

function speakText(text, lang) {
  if (!("speechSynthesis" in window) || !text) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = BCP47[lang] || "en-US";
  utter.rate = 1.05;
  window.speechSynthesis.speak(utter);
}

async function api(path, opts) {
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function newMatch() {
  const data = await api("/api/match/new", { method: "POST" });
  state.matchId = data.match_id;
  state.meta = data.meta;
  state.players = data.players;
  el("homeName").textContent = data.meta.home.name;
  el("awayName").textContent = data.meta.away.name;

  const teamSelect = el("teamSelect");
  teamSelect.innerHTML = '<option value="">Any</option>';
  for (const t of [data.meta.home, data.meta.away]) {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = t.name;
    teamSelect.appendChild(opt);
  }
  populatePlayerSelect();
  buildPlayers3D();
}

function populatePlayerSelect() {
  const teamId = el("teamSelect").value;
  const playerSelect = el("playerSelect");
  playerSelect.innerHTML = "";
  const players = Object.values(state.players).filter((p) => !teamId || p.team_id === teamId);
  for (const p of players) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.position})`;
    playerSelect.appendChild(opt);
  }
}

async function loadTimeline() {
  const data = await api(`/api/match/${state.matchId}/timeline`);
  state.events = data.events;
  state.cues = data.cues;
  state.minuteSnapshots = data.minute_snapshots;
  const last = state.events[state.events.length - 1];
  state.maxClock = last ? last.minute * 60 + last.second + 5 : 5400;
  el("scrubber").max = state.maxClock;
  resetPlayback();
  await refreshPersonaFeed();
}

function resetPlayback() {
  state.clock = 0;
  state.shownCueIds.clear();
  el("overlayZone").innerHTML = "";
  el("scrubber").value = 0;
  renderFrame();
}

function timeAt(e) { return e.minute * 60 + e.second; }

function renderFrame() {
  const mm = Math.floor(state.clock / 60);
  const ss = Math.floor(state.clock % 60);
  el("clock").textContent = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;

  // ball position: snap to most recent event at/before current clock
  let latest = null;
  for (const e of state.events) {
    if (timeAt(e) <= state.clock) latest = e; else break;
  }
  if (latest) pitch3d.updateBall(latest.x, latest.y);
  updatePlayerPositions(latest);

  // reveal any cues we've just passed
  for (const cue of state.cues) {
    const t = cue.minute * 60 + cue.second;
    if (t <= state.clock && !state.shownCueIds.has(cue.id)) {
      state.shownCueIds.add(cue.id);
      showCue(cue);
    }
  }

  // stats panel from nearest minute snapshot
  const snap = [...state.minuteSnapshots].reverse().find((s) => s.minute * 60 <= state.clock) || state.minuteSnapshots[0];
  state.currentSnapshot = snap;
  if (snap) renderStats(snap);
  if (state.openPlayerId) showPlayerPopup(state.openPlayerId, state.playerSlots[state.openPlayerId].number,
    state.playerSlots[state.openPlayerId].teamId === state.meta.home.id);

  el("scrubber").value = Math.floor(state.clock);
  updateZoomLabel();
}

function showPlayerPopup(playerId, number, isHome) {
  const popup = el("playerPopup");
  const p = state.players[playerId];
  if (!popup || !pitch3d || !p) return;
  const pos = pitch3d.screenPositionOf(playerId);
  if (!pos) return;
  state.openPlayerId = playerId;

  const ps = (state.currentSnapshot && state.currentSnapshot.player_stats[playerId]) || {};
  popup.className = `player-popup ${isHome ? "home-team" : "away-team"}`;
  popup.innerHTML = `
    <div class="pp-name">#${number} ${p.name}</div>
    <div class="pp-sub">${p.position} — ${isHome ? state.meta.home.name : state.meta.away.name}</div>
    <div class="pp-row"><span>Passes</span><span>${ps.passes_completed ?? 0}/${ps.passes_attempted ?? 0} (${Math.round((ps.pass_accuracy ?? 0) * 100)}%)</span></div>
    <div class="pp-row"><span>Distance</span><span>${Math.round(ps.distance_covered_m ?? 0)} m</span></div>
    <div class="pp-row"><span>Top speed</span><span>${(ps.top_speed_kmh ?? 0).toFixed(1)} km/h</span></div>
    <div class="pp-row"><span>Shots</span><span>${ps.shots ?? 0} (${ps.shots_on_target ?? 0} on target)</span></div>
    <div class="pp-row"><span>Tackles</span><span>${ps.tackles ?? 0}</span></div>
  `;

  const canvas = el("pitchCanvas");
  const stageRect = canvas.parentElement.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  const originX = canvasRect.left - stageRect.left;
  const originY = canvasRect.top - stageRect.top;
  let left = originX + pos.x + 16;
  let top = originY + pos.y - 10;
  if (left + 200 > stageRect.width) left = originX + pos.x - 214;
  popup.style.left = `${Math.max(4, left)}px`;
  popup.style.top = `${Math.max(4, top)}px`;
  popup.classList.remove("hidden");
}

function hidePlayerPopup() {
  state.openPlayerId = null;
  state.pinnedPlayerId = null;
  el("playerPopup").classList.add("hidden");
}

function showCue(cue) {
  const zone = el("overlayZone");
  const card = document.createElement("div");
  card.className = `cue style-${cue.style}`;
  const badge = cue.verified
    ? '<span class="verified-badge">✓ Verified</span>'
    : '<span class="verified-badge corrected">~ Corrected</span>';
  card.innerHTML = `<span class="cue-time">${String(cue.minute).padStart(2, "0")}:${String(cue.second).padStart(2, "0")}</span>
    <div class="cue-title">${cue.title}${badge}</div>
    <div class="cue-body">${cue.body}</div>`;
  zone.prepend(card);
  while (zone.children.length > 4) zone.removeChild(zone.lastChild);
  setTimeout(() => {
    card.classList.add("leaving");
    setTimeout(() => card.remove(), 400);
  }, cue.duration_s * 1000);

  if (el("audioToggle").checked) {
    speakText(`${cue.title}. ${cue.body}`, el("langSelect").value);
  }
}

function renderStats(snap) {
  const home = state.meta.home, away = state.meta.away;
  const hs = snap.team_stats[home.id] || {};
  const as = snap.team_stats[away.id] || {};
  el("homeStats").innerHTML = statBlock(home.name, hs);
  el("awayStats").innerHTML = statBlock(away.name, as);
  el("scoreDisplay").textContent = `${hs.goals ?? 0} – ${as.goals ?? 0}`;

  const momentum = snap.momentum ?? 0; // -1..1
  const pct = 50 + momentum * 50;
  const fill = el("momentumFill");
  fill.style.left = `${Math.min(pct, 50)}%`;
  fill.style.width = `${Math.abs(pct - 50)}%`;
}

function statBlock(name, s) {
  return `<strong>${name}</strong><br/>
    Possession: ${s.possession_pct ?? 0}%<br/>
    Pass acc: ${s.pass_accuracy ?? 0}%<br/>
    Shots: ${s.shots ?? 0} (${s.shots_on_target ?? 0} on target)`;
}

async function refreshPersonaFeed() {
  if (!state.matchId) return;
  const mode = el("modeSelect").value;
  const teamId = el("teamSelect").value;
  const playerId = el("playerSelect").value;
  const lang = el("langSelect").value;
  const params = new URLSearchParams({ mode, language: lang });
  if (teamId) params.set("favorite_team_id", teamId);
  if (mode === "player_focus" && playerId) params.set("favorite_player_id", playerId);

  const data = await api(`/api/match/${state.matchId}/personalize?${params.toString()}`);
  const feed = el("personaFeed");
  feed.innerHTML = "";
  if (!data.cards.length) {
    feed.innerHTML = '<div class="persona-card">No moments yet for this filter.</div>';
    return;
  }
  for (const c of data.cards) {
    const card = document.createElement("div");
    card.className = "persona-card";
    const badge = c.verified
      ? '<span class="verified-badge">✓ Verified</span>'
      : '<span class="verified-badge corrected">~ Corrected</span>';
    card.innerHTML = `<span class="pc-time">${String(c.minute).padStart(2, "0")}:${String(c.second).padStart(2, "0")}</span>
      <button class="speak-btn" type="button">🔊</button>
      <div class="pc-title">${c.title}${badge}</div>
      <div class="pc-body">${c.body}</div>`;
    card.querySelector(".speak-btn").addEventListener("click", () => speakText(`${c.title}. ${c.body}`, lang));
    feed.appendChild(card);
  }
}

function tick() {
  if (state.playing) {
    state.clock = Math.min(state.clock + 0.15 * state.speed, state.maxClock);
    renderFrame();
    if (state.clock >= state.maxClock) {
      state.playing = false;
      el("playBtn").textContent = "▶ Play";
      showRecap();
    }
  }
  setTimeout(tick, 150);
}

async function showRecap() {
  if (!state.matchId) return;
  const backdrop = el("recapBackdrop");
  backdrop.classList.remove("hidden");
  el("recapSummary").textContent = "Loading recap…";
  const recap = await api(`/api/match/${state.matchId}/recap`);
  el("recapHeadline").textContent = recap.headline;
  el("recapScore").textContent = `${state.meta.home.name} vs ${state.meta.away.name} — Full Time`;
  el("recapSummary").textContent = recap.summary;
  const badge = el("recapBadge");
  badge.textContent = recap.verified ? "✓ Verified" : "~ Corrected";
  badge.className = `verified-badge${recap.verified ? "" : " corrected"}`;
  el("recapSpeakBtn").onclick = () => speakText(recap.summary, el("langSelect").value);
}

function hideRecap() {
  el("recapBackdrop").classList.add("hidden");
}

function wireControls() {
  el("playBtn").addEventListener("click", () => {
    state.playing = !state.playing;
    el("playBtn").textContent = state.playing ? "⏸ Pause" : "▶ Play";
  });
  el("speedSelect").addEventListener("change", (e) => (state.speed = Number(e.target.value)));
  el("scrubber").addEventListener("input", (e) => {
    state.clock = Number(e.target.value);
    state.shownCueIds.clear();
    el("overlayZone").innerHTML = "";
    renderFrame();
  });
  el("newMatchBtn").addEventListener("click", async () => {
    state.playing = false;
    el("playBtn").textContent = "▶ Play";
    hideRecap();
    await newMatch();
    await loadTimeline();
  });
  el("modeSelect").addEventListener("change", () => {
    el("playerLabel").classList.toggle("hidden", el("modeSelect").value !== "player_focus");
    refreshPersonaFeed();
  });
  el("teamSelect").addEventListener("change", () => {
    populatePlayerSelect();
    refreshPersonaFeed();
  });
  el("playerSelect").addEventListener("change", refreshPersonaFeed);
  el("langSelect").addEventListener("change", refreshPersonaFeed);

  el("zoomInBtn").addEventListener("click", () => {
    pitch3d.zoomBy(0.82);
    updateZoomLabel();
  });
  el("zoomOutBtn").addEventListener("click", () => {
    pitch3d.zoomBy(1.22);
    updateZoomLabel();
  });
  el("resetCamBtn").addEventListener("click", () => {
    pitch3d.resetCamera();
    updateZoomLabel();
  });
  el("followBallToggle").addEventListener("change", (e) => {
    state.followBall = e.target.checked;
    pitch3d.setFollowBall(state.followBall);
  });

  const canvas = el("pitchCanvas");
  canvas.addEventListener("mousemove", (e) => {
    if (state.pinnedPlayerId) return; // pinned popup ignores hover until unpinned
    const hitId = pitch3d.hitTest(e.clientX, e.clientY);
    if (hitId) {
      const slot = state.playerSlots[hitId];
      showPlayerPopup(hitId, slot.number, slot.teamId === state.meta.home.id);
    } else {
      hidePlayerPopup();
    }
  });
  canvas.addEventListener("click", (e) => {
    const hitId = pitch3d.hitTest(e.clientX, e.clientY);
    if (hitId && hitId !== state.pinnedPlayerId) {
      state.pinnedPlayerId = hitId;
      const slot = state.playerSlots[hitId];
      showPlayerPopup(hitId, slot.number, slot.teamId === state.meta.home.id);
    } else {
      state.pinnedPlayerId = null;
      if (!hitId) hidePlayerPopup();
    }
  });

  el("recapBtn").addEventListener("click", showRecap);
  el("recapCloseBtn").addEventListener("click", hideRecap);
  el("recapBackdrop").addEventListener("click", (e) => {
    if (e.target.id === "recapBackdrop") hideRecap();
  });
}

function updateZoomLabel() {
  el("zoomLabel").textContent = `${pitch3d.getZoomRatio().toFixed(1)}x`;
}

(async function init() {
  pitch3d = initPitch3D(el("pitchCanvas"));
  wireControls();
  await newMatch();
  await loadTimeline();
  tick();
  setTimeout(() => el("dragHint").classList.add("faded"), 4000);
})();
