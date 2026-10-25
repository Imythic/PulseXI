/* ── PulseXI – Frontend Application ───────────────────────────────── */

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
};

const el = (id) => document.getElementById(id);

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
  if (latest) {
    const ball = el("ball");
    ball.style.left = `${latest.x}%`;
    ball.style.top = `${latest.y}%`;
    ball.classList.remove("home", "away");
    ball.classList.add(latest.team_id === state.meta.home.id ? "home" : "away");
  }

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
  if (snap) renderStats(snap);

  el("scrubber").value = Math.floor(state.clock);
}

function showCue(cue) {
  const zone = el("overlayZone");
  const card = document.createElement("div");
  card.className = `cue style-${cue.style}`;
  card.innerHTML = `<span class="cue-time">${String(cue.minute).padStart(2, "0")}:${String(cue.second).padStart(2, "0")}</span>
    <div class="cue-title">${cue.title}</div>
    <div class="cue-body">${cue.body}</div>`;
  zone.prepend(card);
  while (zone.children.length > 4) zone.removeChild(zone.lastChild);
  setTimeout(() => {
    card.classList.add("leaving");
    setTimeout(() => card.remove(), 400);
  }, cue.duration_s * 1000);
}

function renderStats(snap) {
  const home = state.meta.home, away = state.meta.away;
  const hs = snap.team_stats[home.id] || {};
  const as = snap.team_stats[away.id] || {};
  el("homeStats").innerHTML = statBlock(home.name, hs);
  el("awayStats").innerHTML = statBlock(away.name, as);

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
    card.innerHTML = `<span class="pc-time">${String(c.minute).padStart(2, "0")}:${String(c.second).padStart(2, "0")}</span>
      <div class="pc-title">${c.title}</div>
      <div class="pc-body">${c.body}</div>`;
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
    }
  }
  setTimeout(tick, 150);
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
}

(async function init() {
  wireControls();
  await newMatch();
  await loadTimeline();
  tick();
})();
