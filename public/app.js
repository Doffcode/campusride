'use strict';
/* CampusRide MVP: map, shortest paths, dispatch and EV simulation all run here.
   The server (mvp/server.py) serves the campus map (/api/campus) and talks to Sarvam: /api/voice, /api/understand, /api/speak. */

const SPEED = 250 / 60;        // EV speed in meters per sim-second (15 km/h)
const DWELL = 20;              // sim-seconds an EV waits at a pickup while the student boards
const REPLY_LANGS = ['en-IN', 'hi-IN', 'ta-IN'];   // hand-written templates; every other language goes through Sarvam Translate
const LANG_NAMES = {
  'en-IN': 'English', 'hi-IN': 'Hindi', 'ta-IN': 'Tamil', 'te-IN': 'Telugu', 'kn-IN': 'Kannada', 'ml-IN': 'Malayalam',
  'bn-IN': 'Bengali', 'mr-IN': 'Marathi', 'gu-IN': 'Gujarati', 'pa-IN': 'Punjabi', 'od-IN': 'Odia',
};
const NS = 'http://www.w3.org/2000/svg';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const T = {
  confirm: {
    'en-IN': 'Booked! EV {n} will reach {pickup} in about {eta} minutes.',
    'hi-IN': 'राइड बुक हो गई! EV {n} लगभग {eta} मिनट में {pickup} पहुँचेगी।',
    'ta-IN': 'பயணம் பதிவு செய்யப்பட்டது! EV {n} சுமார் {eta} நிமிடங்களில் {pickup} வந்தடையும்.',
  },
  arrived: {
    'en-IN': '{name}, EV {n} has arrived at {pickup}.',
    'hi-IN': '{name}, EV {n} {pickup} पहुँच गई है।',
    'ta-IN': '{name}, EV {n} {pickup} வந்துவிட்டது.',
  },
  ask_drop: {
    'en-IN': 'Picking you up at {pickup}. Where do you want to go?',
    'hi-IN': '{pickup} से पिक करेंगे। आपको कहाँ जाना है?',
    'ta-IN': '{pickup}-இல் அழைத்துச் செல்கிறோம். எங்கே போக வேண்டும்?',
  },
  ask_both: {
    'en-IN': "Sorry, I didn't catch the place. Please say where you want to go.",
    'hi-IN': 'माफ़ कीजिए, जगह समझ नहीं आई। कृपया बताइए आपको कहाँ जाना है।',
    'ta-IN': 'மன்னிக்கவும், இடம் புரியவில்லை. எங்கே போக வேண்டும் என்று சொல்லுங்கள்.',
  },
};
const fill = (key, lang, vars) => (T[key][lang] || T[key]['en-IN']).replace(/\{(\w+)\}/g, (_, k) => vars[k]);

/* ------------------------------------------------------------------ graph */
let C, NODES = {}, ADJ = {}, EDGE_M = {};
const ekey = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);
const SP_CACHE = {};

function dijkstra(src) {
  const dist = { [src]: 0 }, prev = {}, done = new Set();
  for (;;) {
    let u = null;
    for (const k in dist) if (!done.has(k) && (u === null || dist[k] < dist[u])) u = k;
    if (u === null) break;
    done.add(u);
    for (const { to, m } of ADJ[u]) {
      const nd = dist[u] + m;
      if (!(to in dist) || nd < dist[to]) { dist[to] = nd; prev[to] = u; }
    }
  }
  return { dist, prev };
}

/** Shortest road path a -> b: { m: meters, path: [a, ..., b] } */
function sp(a, b) {
  if (!SP_CACHE[a]) SP_CACHE[a] = dijkstra(a);
  const { dist, prev } = SP_CACHE[a];
  const path = [b];
  while (path[0] !== a) path.unshift(prev[path[0]]);
  return { m: dist[b], path };
}

/* ------------------------------------------------------------------ state */
let S, simSpeed = 8, sarvamOk = false, busy = false, pending = null;

function initialState() {
  return {
    simT: 0,
    evs: C.evs.map((e, i) => ({ id: e.id, num: i + 1, color: e.color, node: e.start, route: [], progM: 0, legs: [], dwell: 0 })),
    rides: [], nextId: 1, selected: null, voiceCount: 0,
    me: { node: 'agate', drag: null }, dest: null,
  };
}
const evById = (id) => S.evs.find((e) => e.id === id);
const rideById = (id) => S.rides.find((r) => r.id === id);
const name = (id) => NODES[id].name;

/* ------------------------------------------------------------------ EV logic */
function evPos(ev) {
  const a = NODES[ev.node];
  if (!ev.route.length || ev.progM <= 0) return { x: a.x, y: a.y };
  const b = NODES[ev.route[0]], f = ev.progM / EDGE_M[ekey(ev.node, ev.route[0])];
  return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
}

function evStatus(ev) {
  if (ev.dwell > 0) return 'boarding';
  if (!ev.legs.length) return 'idle';
  return ev.legs[0].kind === 'pickup' ? 'to_pickup' : 'to_drop';
}

/** Arrival time (sim-seconds from now) at each of the EV's legs, plus where/when it becomes free. */
function timeline(ev) {
  let t = 0, pos = ev.node;
  if (ev.route.length) {
    let m = EDGE_M[ekey(ev.node, ev.route[0])] - ev.progM;
    for (let i = 1; i < ev.route.length; i++) m += EDGE_M[ekey(ev.route[i - 1], ev.route[i])];
    t += m / SPEED;
    pos = ev.route[ev.route.length - 1];
  }
  const arr = [];
  ev.legs.forEach((leg, k) => {
    if (k === 0 && ev.dwell > 0) { arr.push(0); t += ev.dwell; pos = leg.node; return; }
    t += sp(pos, leg.node).m / SPEED;
    pos = leg.node;
    arr.push(t);
    if (leg.kind === 'pickup') t += DWELL;
  });
  return { arr, endT: t, endNode: pos };
}

/** Best EV for a pickup = the one that can reach it soonest after finishing its current jobs. */
function bestEv(pickup) {
  let best = null;
  for (const ev of [...S.evs].sort((a, b) => (a.id < b.id ? -1 : 1))) {
    const tl = timeline(ev);
    const t = tl.endT + sp(tl.endNode, pickup).m / SPEED;
    if (!best || t < best.t - 1e-9) best = { ev, t };
  }
  return best;
}

function step(ev, dt) {
  if (ev.dwell > 0) {
    ev.dwell -= dt;
    if (ev.dwell <= 0) {
      ev.dwell = 0;
      const r = rideById(ev.legs.shift().rideId);
      r.status = 'onboard';
      changed(r);
    }
    return;
  }
  let d = SPEED * dt;
  for (let guard = 0; d > 0 && guard < 50; guard++) {
    if (!ev.route.length) {
      if (!ev.legs.length) return;
      const leg = ev.legs[0];
      if (leg.node === ev.node) { arrive(ev, leg); return; }
      ev.route = sp(ev.node, leg.node).path.slice(1);
      ev.progM = 0;
    }
    const rem = EDGE_M[ekey(ev.node, ev.route[0])] - ev.progM;
    if (d >= rem) { ev.node = ev.route.shift(); ev.progM = 0; d -= rem; }
    else { ev.progM += d; d = 0; }
  }
}

function arrive(ev, leg) {
  const r = rideById(leg.rideId);
  if (leg.kind === 'pickup') {
    ev.dwell = DWELL;
    r.status = 'boarding';
    toast(`EV ${ev.num} reached ${name(r.pickup)} for ${r.name}`, 'ok');
    if (r.speak && $('#announce').checked) speak(fill('arrived', r.lang, { name: r.name, n: ev.num, pickup: name(r.pickup) }), r.lang);
  } else {
    ev.legs.shift();
    r.status = 'done';
    toast(`${r.name} dropped at ${name(r.drop)} ✓`, 'ok');
    if (r.mine && S.me.node === r.pickup) S.me.node = r.drop;   // the student is now at the drop point
  }
  changed(r);
}

/** Seconds until the EV reaches this ride's next point (pickup, or drop once on board). */
function rideEta(r) {
  if (!r.evId || r.status === 'done') return null;
  const ev = evById(r.evId);
  const want = r.status === 'onboard' ? 'drop' : 'pickup';
  const idx = ev.legs.findIndex((l) => l.rideId === r.id && l.kind === want);
  if (idx < 0) return 0;
  return timeline(ev).arr[idx];
}
const fmtEta = (sec) => (sec == null ? '–' : sec < 30 ? 'now' : `${Math.ceil(sec / 60)} min`);

function bookRide({ pickup, drop, who, lang, via, speakIt }) {
  if (!NODES[pickup] || !NODES[drop]) { toast('Unknown place', 'err'); return null; }
  if (pickup === drop) { toast('Pickup and destination are the same place', 'err'); return null; }
  const t0 = performance.now();
  const best = bestEv(pickup);
  const r = {
    id: `R${S.nextId++}`, name: who, pickup, drop, lang, via, speak: speakIt, mine: true,
    evId: best.ev.id, status: 'assigned', etaAtBooking: Math.max(1, Math.ceil(best.t / 60)),
    tripM: sp(pickup, drop).m, flashUntil: performance.now() + 1600,
  };
  best.ev.legs.push({ rideId: r.id, kind: 'pickup', node: pickup }, { rideId: r.id, kind: 'drop', node: drop });
  S.rides.unshift(r);
  S.selected = r.id;
  renderPanels();
  return { ride: r, ev: best.ev, ms: Math.max(1, Math.round(performance.now() - t0)) };
}

function changed(r) { r.flashUntil = performance.now() + 1600; }

/* ------------------------------------------------------------------ map: static layer */
const svg = () => $('#map');
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

function buildingOffset(n) {
  if (n.b) return { dx: n.b[0], dy: n.b[1] };
  let vx = 0, vy = 0;
  for (const { to } of ADJ[n.id]) {
    const m = NODES[to], dx = n.x - m.x, dy = n.y - m.y, L = Math.hypot(dx, dy) || 1;
    vx += dx / L; vy += dy / L;
  }
  let L = Math.hypot(vx, vy);
  if (L < 0.3) { vx = 0; vy = -1; L = 1; }
  return { dx: (vx / L) * 46, dy: (vy / L) * 46 };
}

const KIND_COLOR = { hostel: '#8b5cf6', academic: '#2563eb', facility: '#d97706', gate: '#475569' };
let G = {};

function drawStatic() {
  const s = svg();
  s.innerHTML = '';
  const defs = el('defs', {}, s);
  defs.innerHTML = `
    <filter id="sh" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1.5" stdDeviation="1.8" flood-opacity=".35"/></filter>
    <pattern id="grass" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="#e7f1e2"/><circle cx="6" cy="8" r="1.1" fill="#d3e5ca"/><circle cx="19" cy="20" r="1.1" fill="#d3e5ca"/></pattern>`;
  el('rect', { x: 0, y: 0, width: 1000, height: 700, rx: 12, fill: 'url(#grass)' }, s);
  el('rect', { x: 12, y: 12, width: 976, height: 676, rx: 10, fill: 'none', stroke: '#b9d3ad', 'stroke-width': 2, 'stroke-dasharray': '6 6' }, s);

  // trees: deterministic scatter, kept away from roads and buildings
  const gTrees = el('g', {}, s);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const segDist = (px, py, a, b) => {
    const vx = b.x - a.x, vy = b.y - a.y, t = Math.max(0, Math.min(1, ((px - a.x) * vx + (py - a.y) * vy) / (vx * vx + vy * vy)));
    return Math.hypot(px - (a.x + t * vx), py - (a.y + t * vy));
  };
  for (let i = 0; i < 260 && gTrees.childNodes.length < 70; i++) {
    const x = 30 + rnd() * 940, y = 30 + rnd() * 640;
    const nearRoad = C.edges.some(([a, b]) => segDist(x, y, NODES[a], NODES[b]) < 26);
    const nearNode = C.nodes.some((n) => { const o = buildingOffset(n); return Math.hypot(x - n.x - o.dx, y - n.y - o.dy) < 62 || Math.hypot(x - n.x, y - n.y) < 40; });
    if (!nearRoad && !nearNode) el('circle', { cx: x, cy: y, r: 5 + rnd() * 5, fill: '#bcd9ae', opacity: 0.9 }, gTrees);
  }

  // roads: asphalt, edge lines, dashed centre line. EVs only ever move along these edges.
  const gRoads = el('g', {}, s);
  const line = (a, b, attrs) => el('line', { x1: NODES[a].x, y1: NODES[a].y, x2: NODES[b].x, y2: NODES[b].y, 'stroke-linecap': 'round', ...attrs }, gRoads);
  for (const [a, b] of C.edges) line(a, b, { stroke: '#e2e8f0', 'stroke-width': 24 });
  for (const [a, b] of C.edges) line(a, b, { stroke: '#4b5563', 'stroke-width': 19 });
  for (const [a, b] of C.edges) line(a, b, { stroke: '#fde68a', 'stroke-width': 1.6, 'stroke-dasharray': '9 9', 'stroke-linecap': 'butt' });

  // layers for moving things (order = z-order)
  G.preview = el('g', {}, s);
  G.routes = el('g', {}, s);

  // stops + buildings
  const gPlaces = el('g', {}, s);
  for (const n of C.nodes) {
    const o = buildingOffset(n);
    const g = el('g', { class: 'node', 'data-id': n.id }, gPlaces);
    el('line', { x1: n.x, y1: n.y, x2: n.x + o.dx, y2: n.y + o.dy, stroke: '#9ca3af', 'stroke-width': 3 }, g);
    el('circle', { cx: n.x, cy: n.y, r: 7, fill: '#fff', stroke: '#111827', 'stroke-width': 2.5 }, g);
    const bx = n.x + o.dx, by = n.y + o.dy;
    el('rect', { x: bx - 17, y: by - 17, width: 34, height: 34, rx: 9, fill: '#fff', stroke: KIND_COLOR[n.kind], 'stroke-width': 3, filter: 'url(#sh)' }, g);
    const ic = el('text', { x: bx, y: by + 6, 'text-anchor': 'middle', class: 'node-icon' }, g);
    ic.textContent = n.icon;
    const below = o.dy >= -10;
    const lb = el('text', { x: bx, y: below ? by + 34 : by - 25, 'text-anchor': 'middle', class: 'node-label' }, g);
    lb.textContent = n.name;
    const title = el('title', {}, g);
    title.textContent = `${n.name}: click to set as destination`;
    g.addEventListener('click', () => setDest(n.id, true));
  }

  G.pins = el('g', {}, s);
  G.evs = el('g', {}, s);
  G.evEls = {};
  for (const ev of S.evs) {
    const g = el('g', { style: 'cursor:pointer' }, G.evs);
    const pulse = el('circle', { r: 15, fill: ev.color, class: 'pulse', visibility: 'hidden' }, g);
    el('circle', { r: 15, fill: ev.color, stroke: '#fff', 'stroke-width': 3, filter: 'url(#sh)' }, g);
    const t = el('text', { y: 5, 'text-anchor': 'middle', class: 'ev-num' }, g);
    t.textContent = ev.num;
    const pax = el('g', { transform: 'translate(13,-13)' }, g);
    el('circle', { r: 8, fill: '#fff', stroke: ev.color, 'stroke-width': 2 }, pax);
    const pt = el('text', { y: 3.5, 'text-anchor': 'middle', 'font-size': 10, 'font-weight': 800, fill: ev.color }, pax);
    G.evEls[ev.id] = { g, pulse, pax, pt };
  }
  drawMe(s);
}

/* ------------------------------------------------------------------ "You" pin (draggable) */
function drawMe(s) {
  const g = el('g', { style: 'cursor:grab' }, s);
  const halo = el('circle', { r: 16, cx: 0, cy: 0, fill: '#db2777', opacity: 0.18 }, g);
  el('path', { d: 'M0 0 C -4 -10 -14 -16 -14 -27 A 14 14 0 1 1 14 -27 C 14 -16 4 -10 0 0 Z', fill: '#db2777', stroke: '#fff', 'stroke-width': 2.5, filter: 'url(#sh)' }, g);
  const face = el('text', { x: 0, y: -21, 'text-anchor': 'middle', 'font-size': 15 }, g);
  face.textContent = '🧍';
  const bubble = el('g', { transform: 'translate(0,-50)' }, g);
  const br = el('rect', { x: -40, y: -15, width: 80, height: 22, rx: 11, fill: '#111827' }, bubble);
  const bt = el('text', { x: 0, y: 0, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: '#fff' }, bubble);
  G.me = { g, halo, bt, br };

  const toSvg = (e) => {
    const p = s.createSVGPoint();
    p.x = e.clientX; p.y = e.clientY;
    return p.matrixTransform(s.getScreenCTM().inverse());
  };
  g.addEventListener('pointerdown', (e) => {
    g.setPointerCapture(e.pointerId);
    g.style.cursor = 'grabbing';
    S.me.drag = toSvg(e);
    e.preventDefault();
  });
  g.addEventListener('pointermove', (e) => { if (S.me.drag) S.me.drag = toSvg(e); });
  const end = () => {
    if (!S.me.drag) return;
    const { x, y } = S.me.drag;
    let best = null;
    for (const n of C.nodes) { const d = Math.hypot(n.x - x, n.y - y); if (!best || d < best.d) best = { n, d }; }
    S.me.drag = null;
    g.style.cursor = 'grab';
    setMe(best.n.id, true);
  };
  g.addEventListener('pointerup', end);
  g.addEventListener('pointercancel', end);
}

function setMe(id, announce) {
  if (S.dest === id) S.dest = null;
  S.me.node = id;
  $('#pickup').value = id;
  $('#drop').value = S.dest || '';
  if (announce) toast(`📍 Your pickup point: ${name(id)}`);
  renderPanels();
}

function setDest(id, fromMap) {
  if (id === S.me.node) { toast('That is where you are. Pick a different destination.', 'err'); return; }
  S.dest = id;
  $('#drop').value = id;
  if (fromMap) switchTab('manual');
  renderPanels();
}

/* ------------------------------------------------------------------ map: dynamic layer (every frame) */
const pts = (path) => path.map((id) => `${NODES[id].x},${NODES[id].y}`).join(' ');

function drawDynamic() {
  // preview of the trip the student is about to book
  let prev = '';
  if (S.dest && S.dest !== S.me.node && !S.me.drag) {
    const p = sp(S.me.node, S.dest);
    prev = `<polyline points="${pts(p.path)}" fill="none" stroke="#db2777" stroke-width="6" stroke-dasharray="1 11" stroke-linecap="round" stroke-linejoin="round"/>`;
    const d = NODES[S.dest];
    prev += `<g transform="translate(${d.x},${d.y})"><circle r="11" fill="#db2777" stroke="#fff" stroke-width="3"/><text y="4" text-anchor="middle" font-size="11" font-weight="800" fill="#fff">B</text></g>`;
  }
  G.preview.innerHTML = prev;

  // trip routes (pickup -> drop) and each EV's current leg
  let html = '';
  const sel = S.selected && rideById(S.selected);
  const selActive = sel && sel.status !== 'done';
  for (const r of S.rides) {
    if (r.status === 'done') continue;
    const ev = evById(r.evId);
    const dim = selActive && r.id !== S.selected ? ' class="path-dim"' : '';
    html += `<polyline${dim} points="${pts(sp(r.pickup, r.drop).path)}" fill="none" stroke="${ev.color}" stroke-width="${r.id === S.selected ? 9 : 6}" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>`;
  }
  for (const ev of S.evs) {
    if (!ev.route.length) continue;
    const dim = selActive && sel.evId !== ev.id ? ' class="path-dim"' : '';
    const p = evPos(ev);
    const rest = ev.route.map((id) => `${NODES[id].x},${NODES[id].y}`).join(' ');
    html += `<polyline${dim} points="${p.x},${p.y} ${rest}" fill="none" stroke="${ev.color}" stroke-width="4" stroke-dasharray="10 7" stroke-linecap="round" stroke-linejoin="round"/>`;
  }
  G.routes.innerHTML = html;

  // EVs
  for (const ev of S.evs) {
    const p = evPos(ev), E = G.evEls[ev.id];
    E.g.setAttribute('transform', `translate(${p.x},${p.y})`);
    E.g.setAttribute('opacity', selActive && sel.evId !== ev.id ? 0.45 : 1);
    E.pulse.setAttribute('visibility', ev.dwell > 0 ? 'visible' : 'hidden');
    const onboard = S.rides.filter((r) => r.evId === ev.id && r.status === 'onboard').length;
    E.pax.setAttribute('visibility', onboard ? 'visible' : 'hidden');
    E.pt.textContent = onboard;
  }

  // you
  const m = S.me.drag || NODES[S.me.node];
  G.me.g.setAttribute('transform', `translate(${m.x},${m.y})`);
}

let pinsKey = '';
function drawPins() {
  const items = [];
  const perNode = {};
  for (const r of [...S.rides].reverse()) {
    if (r.status !== 'assigned' && r.status !== 'boarding') continue;
    const k = (perNode[r.pickup] = (perNode[r.pickup] || 0) + 1) - 1;
    items.push({ r, k, eta: r.status === 'boarding' ? 'EV here' : fmtEta(rideEta(r)) });
  }
  const key = items.map((i) => `${i.r.id}${i.eta}${i.k}${S.selected}`).join();
  if (key === pinsKey) return;
  pinsKey = key;
  G.pins.innerHTML = items.map(({ r, k, eta }) => {
    const n = NODES[r.pickup], ev = evById(r.evId);
    const label = `${esc(r.name)} · ${eta}`;
    const w = 26 + label.length * 6.6;
    const x = n.x < 250 ? n.x + 14 : n.x - 14 - w, y = n.y + 26 + k * 26;
    return `<g transform="translate(${x},${y})" opacity="${S.selected && S.selected !== r.id ? 0.5 : 1}">
      <rect x="0" y="-11" width="${w}" height="22" rx="11" fill="#fff" stroke="${ev.color}" stroke-width="2" filter="url(#sh)"/>
      <text x="10" y="4.5" font-size="12">🙋</text>
      <text x="26" y="4.5" font-size="11.5" font-weight="700" fill="#111827">${label}</text></g>`;
  }).join('');
}

function updateMeBubble() {
  const best = bestEv(S.me.node);
  const txt = `You · nearest EV ${fmtEta(best.t)}`;
  if (G.me.bt.textContent !== txt) {
    G.me.bt.textContent = txt;
    const w = G.me.bt.getComputedTextLength() + 20;
    G.me.br.setAttribute('x', -w / 2);
    G.me.br.setAttribute('width', w);
  }
  return best;
}

/* ------------------------------------------------------------------ panels */
let lastRidesHtml = '', lastFleetHtml = '';
const STATUS_TEXT = { assigned: 'EV on the way', queued: 'Queued', boarding: 'Boarding', onboard: 'On board', done: 'Completed' };

function renderPanels() {
  const best = updateMeBubble();
  drawPins();

  const active = S.rides.filter((r) => r.status !== 'done');
  $('#k-active').textContent = active.length;
  $('#k-done').textContent = S.rides.length - active.length;
  $('#k-eta').textContent = S.rides.length ? `${(S.rides.reduce((a, r) => a + r.etaAtBooking, 0) / S.rides.length).toFixed(1)} min` : '–';
  $('#k-voice').textContent = S.voiceCount;

  // route preview in the manual tab
  const rp = $('#route-preview');
  if (S.dest && S.dest !== S.me.node) {
    const trip = sp(S.me.node, S.dest);
    rp.innerHTML = `<b>${esc(name(S.me.node))} → ${esc(name(S.dest))}</b> · ${(trip.m / 1000).toFixed(1)} km by road · ~${Math.ceil(trip.m / SPEED / 60)} min ride<br>EV ${best.ev.num} can pick you up in <b>${fmtEta(best.t)}</b>`;
  } else {
    rp.innerHTML = `Your pickup: <b>${esc(name(S.me.node))}</b> (drag the pink pin to move). Nearest EV: <b>EV ${best.ev.num}, ${fmtEta(best.t)}</b>. Click a place on the map to set the destination.`;
  }

  // rides
  const list = $('#rides');
  const now = performance.now();
  let ridesHtml = '<div class="empty">No rides yet. Book one above.</div>';
  if (S.rides.length) {
    ridesHtml = S.rides.map((r) => {
      const ev = evById(r.evId);
      let st = r.status;
      if (st === 'assigned' && ev.legs[0] && ev.legs[0].rideId !== r.id) st = 'queued';
      const eta = st === 'boarding' ? 'EV here' : st === 'done' ? '✓' : fmtEta(rideEta(r));
      const etaLabel = r.status === 'onboard' ? 'to drop' : r.status === 'done' ? '' : st === 'boarding' ? '' : 'pickup';
      return `<div class="ride ${r.id === S.selected ? 'sel' : ''} ${r.flashUntil > now ? 'flash' : ''}" data-id="${r.id}" style="border-left-color:${ev.color}">
        <div class="top"><span class="who">${esc(r.name)}</span><span class="lang">${r.via === 'voice' ? '🎙️ ' : ''}${esc(r.lang)}</span>
          <span class="badge st-${st}">${STATUS_TEXT[st]}</span>
          <span class="eta" title="${etaLabel}">${eta}</span></div>
        <div class="route">${esc(name(r.pickup))} → ${esc(name(r.drop))}</div>
        <div class="meta"><span>EV ${ev.num}</span><span>${(r.tripM / 1000).toFixed(1)} km trip</span>${etaLabel ? `<span>ETA ${etaLabel}</span>` : ''}</div>
      </div>`;
    }).join('');
  }
  if (ridesHtml !== lastRidesHtml) { list.innerHTML = ridesHtml; lastRidesHtml = ridesHtml; }

  // fleet
  const fleetHtml = S.evs.map((ev) => {
    const st = evStatus(ev);
    const leg = ev.legs[0];
    const txt = st === 'idle' ? `Idle at ${name(ev.node)}`
      : st === 'boarding' ? `Boarding at ${name(ev.node)}`
      : `${st === 'to_pickup' ? 'Picking up' : 'Dropping'} ${esc(rideById(leg.rideId).name)} at ${name(leg.node)}`;
    const jobs = new Set(ev.legs.map((l) => l.rideId)).size;
    return `<div class="ev-row"><div class="ev-dot" style="background:${ev.color}">${ev.num}</div>
      <div><b>EV ${ev.num}</b><div class="where">${txt}</div></div>
      <span class="badge ${st === 'idle' ? 'st-done' : 'st-assigned'}">${jobs ? `${jobs} ride${jobs > 1 ? 's' : ''}` : 'Free'}</span></div>`;
  }).join('');
  if (fleetHtml !== lastFleetHtml) { $('#fleet').innerHTML = fleetHtml; lastFleetHtml = fleetHtml; }
}

/* ------------------------------------------------------------------ Sarvam: voice + text understanding */
function setStep(step, state, ms) {
  const li = document.querySelector(`#steps li[data-step="${step}"]`);
  li.className = state || '';
  li.querySelector('.ms').textContent = ms != null ? `${ms} ms` : state === 'skip' ? 'skipped' : '';
}
function resetSteps() { ['stt', 'llm', 'dispatch', 'tts'].forEach((s) => setStep(s, '')); }

function replyLang(serverLang, text) {
  const chosen = $('#lang').value;
  if (chosen !== 'unknown') return chosen;
  if (/[஀-௿]/.test(text)) return 'ta-IN';
  if (/[ऀ-ॿ]/.test(text)) return 'hi-IN';
  // Romanized Hinglish: Saaras may transcribe it in Latin script and tag it en-IN.
  if (/\b(se|jana|jaana|hai|mujhe|muje|chahiye|kaha|kahan)\b/i.test(text)) return 'hi-IN';
  if (LANG_NAMES[serverLang]) return serverLang;
  return 'en-IN';
}

function showResult(said, chipsHtml, reply) {
  $('#result').classList.remove('hidden');
  $('#res-said').textContent = said;
  $('#res-chips').innerHTML = chipsHtml;
  $('#res-reply').innerHTML = reply ? `<span>🔊</span><span>${esc(reply)}</span>` : '';
}

async function handleUnderstood(res, via) {
  const lang = replyLang(res.lang, res.transcript);
  let { pickup, drop } = res;
  const one = pickup && drop ? null : drop || pickup;

  // Conversation memory: we asked "where do you want to go?" last time.
  if (pending && one) { pickup = pending.pickup; drop = one; }
  pending = null;
  // Only one place said: that's the destination; pickup = where the student's pin is.
  if (!pickup && drop) pickup = S.me.node;
  if (pickup && drop === pickup) drop = null;

  const chip = (label, id) => id ? `<span class="chip">${label}: ${esc(name(id))}</span>` : `<span class="chip missing">${label}: ?</span>`;
  const srcChip = res.source === 'sarvam-llm' ? '<span class="chip src">Sarvam-105B</span>' : '<span class="chip src" title="LLM unavailable, used offline rules">offline rules</span>';
  const langChip = LANG_NAMES[lang] ? `<span class="chip lang">🗣 ${LANG_NAMES[lang]}${via === 'voice' ? ' · Saaras' : ''}</span>` : '';
  const chips = chip('From', pickup) + chip('To', drop) + langChip + srcChip;

  if (!drop) {
    setStep('dispatch', 'skip');
    const key = pickup ? 'ask_drop' : 'ask_both';
    if (pickup) { pending = { pickup }; setMe(pickup); }
    const reply = fill(key, lang, { pickup: pickup ? name(pickup) : '' });
    showResult(res.transcript, chips, reply);
    await speakStep(reply, lang);
    return;
  }
  if (pickup !== S.me.node) setMe(pickup);
  const who = $('#name').value.trim() || `Student ${S.nextId}`;
  const out = bookRide({ pickup, drop, who, lang, via, speakIt: true });
  if (!out) { setStep('dispatch', 'fail'); return; }
  setStep('dispatch', 'done', out.ms);
  if (via === 'voice') S.voiceCount++;
  S.dest = null;
  $('#drop').value = '';
  const reply = fill('confirm', lang, { n: out.ev.num, pickup: name(pickup), eta: out.ride.etaAtBooking });
  showResult(res.transcript, chips, reply);
  renderPanels();
  await speakStep(reply, lang);
}

async function speakStep(text, lang) {
  if (!sarvamOk) { setStep('tts', 'skip'); return; }
  setStep('tts', 'active');
  // Resolve as soon as the audio is ready (not when it finishes playing), so the next request isn't blocked.
  await new Promise((done) => speak(text, lang, (r) => {
    setStep('tts', r ? 'done' : 'fail', r ? r.ms : null);
    // Sarvam Translate produced the reply in the student's language: show that instead of the English template.
    if (r && r.text && r.text !== text) $('#res-reply').innerHTML = `<span>🔊</span><span>${esc(r.text)}</span>`;
    done();
  }));
}

/** Speak `text` in `lang` with Sarvam Bulbul. Languages without a hand-written template are
    translated by Sarvam Translate first. `onReady` fires as soon as the audio is fetched. */
let audioChain = Promise.resolve();
function speak(text, lang, onReady = () => {}) {
  if (!sarvamOk) { onReady(null); return Promise.resolve(null); }
  // Fetch right away; only playback is queued, so clips never talk over each other.
  const fetched = (async () => {
    try {
      const body = { text, lang, translate: !REPLY_LANGS.includes(lang) };
      const resp = await fetch('/api/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || resp.status);
      const r = { ms: (data.timings.translate_ms || 0) + data.timings.tts_ms, text: data.text, b64: data.audio_b64 };
      onReady(r);
      return r;
    } catch (e) {
      console.warn('TTS failed', e);
      onReady(null);
      return null;
    }
  })();
  audioChain = audioChain.then(async () => {
    const r = await fetched;
    if (!r) return;
    const audio = new Audio(`data:audio/wav;base64,${r.b64}`);
    // Never let one stuck clip block later announcements: give up after 20 s.
    await new Promise((ok) => { audio.onended = ok; audio.onerror = ok; audio.play().catch(ok); setTimeout(ok, 20000); });
  });
  return fetched;
}

async function understandText() {
  const text = $('#say-text').value.trim();
  if (!text || busy) return;
  busy = true;
  resetSteps();
  setStep('stt', 'skip');
  setStep('llm', 'active');
  try {
    const lang = $('#lang').value === 'unknown' ? replyLang('', text) : $('#lang').value;
    const resp = await fetch('/api/understand', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, lang }) });
    const res = await resp.json();
    if (!resp.ok) throw new Error(res.error || resp.status);
    setStep('llm', res.source === 'sarvam-llm' ? 'done' : 'fail', res.timings.llm_ms);
    $('#say-text').value = '';
    await handleUnderstood(res, 'text');
  } catch (e) {
    setStep('llm', 'fail');
    toast(`Could not understand: ${e.message}`, 'err');
  } finally { busy = false; }
}

let rec = null, recTimer = null;
async function toggleMic() {
  if (rec && rec.state === 'recording') { rec.stop(); return; }
  if (busy) return;
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch { toast('Microphone blocked. Allow mic access, or type instead.', 'err'); return; }
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find((m) => MediaRecorder.isTypeSupported(m)) || '';
  rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  rec.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    clearTimeout(recTimer);
    $('#mic-btn').classList.remove('rec');
    $('#mic-hint').textContent = 'Tap and say where you want to go';
    sendVoice(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }));
  };
  rec.start();
  $('#mic-btn').classList.add('rec');
  $('#mic-hint').textContent = 'Listening… tap again when done';
  recTimer = setTimeout(() => rec.state === 'recording' && rec.stop(), 12000);
}

async function sendVoice(blob) {
  busy = true;
  resetSteps();
  setStep('stt', 'active');
  try {
    const fd = new FormData();
    fd.append('audio', blob, blob.type.includes('ogg') ? 'speech.ogg' : 'speech.webm');
    fd.append('lang', $('#lang').value);
    const resp = await fetch('/api/voice', { method: 'POST', body: fd });
    const res = await resp.json();
    if (!resp.ok) throw new Error(res.error || resp.status);
    setStep('stt', 'done', res.timings.stt_ms);
    setStep('llm', res.source === 'sarvam-llm' ? 'done' : 'fail', res.timings.llm_ms);
    await handleUnderstood(res, 'voice');
  } catch (e) {
    setStep('stt', 'fail');
    toast(`Voice failed: ${e.message}`, 'err');
  } finally { busy = false; }
}

/* ------------------------------------------------------------------ misc UI */
function toast(msg, kind = '') {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), 3500);
  while ($('#toasts').children.length > 4) $('#toasts').firstChild.remove();
}

function switchTab(tab) {
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === tab));
  $('#tab-voice').classList.toggle('hidden', tab !== 'voice');
  $('#tab-manual').classList.toggle('hidden', tab !== 'manual');
}

function loadSamples() {
  const samples = [
    { who: 'Aarav', pickup: 'opal', drop: 'lhc', lang: 'en-IN' },
    { who: 'Divya', pickup: 'zircon', drop: 'library', lang: 'ta-IN' },
    { who: 'Rahul', pickup: 'main_gate', drop: 'garnet', lang: 'hi-IN' },
  ];
  for (const s of samples) {
    const out = bookRide({ ...s, via: 'text', speakIt: false });
    if (out) out.ride.mine = false;
  }
  S.selected = null;
  toast('3 sample rides booked by other students', 'ok');
}

function wireUi() {
  const opts = C.nodes.map((n) => `<option value="${n.id}">${esc(n.name)}</option>`).join('');
  $('#pickup').innerHTML = opts;
  $('#drop').innerHTML = '<option value="">Choose destination…</option>' + opts;
  $('#pickup').value = S.me.node;
  $('#pickup').onchange = (e) => setMe(e.target.value);
  $('#drop').onchange = (e) => (e.target.value ? setDest(e.target.value) : ((S.dest = null), renderPanels()));
  $('#book-btn').onclick = () => {
    if (!S.dest) { toast('Choose a destination (click a place on the map)', 'err'); return; }
    const lang = $('#lang').value === 'unknown' ? 'en-IN' : $('#lang').value;
    const who = $('#name').value.trim() || `Student ${S.nextId}`;
    const pickup = S.me.node;
    const out = bookRide({ pickup, drop: S.dest, who, lang, via: 'text', speakIt: true });
    if (!out) return;
    toast(`${who}: EV ${out.ev.num} assigned, pickup in ${out.ride.etaAtBooking} min`, 'ok');
    S.dest = null;
    $('#drop').value = '';
    renderPanels();
    speak(fill('confirm', lang, { n: out.ev.num, pickup: name(pickup), eta: out.ride.etaAtBooking }), lang);
  };
  $('#demo-btn').onclick = loadSamples;
  $('#mic-btn').onclick = toggleMic;
  $('#say-btn').onclick = understandText;
  $('#say-text').onkeydown = (e) => { if (e.key === 'Enter') understandText(); };
  document.querySelectorAll('.tabs button').forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
  document.querySelectorAll('#speed-seg button').forEach((b) => (b.onclick = () => {
    simSpeed = Number(b.dataset.s);
    document.querySelectorAll('#speed-seg button').forEach((x) => x.classList.toggle('on', x === b));
  }));
  $('#reset-btn').onclick = () => {
    S = initialState();
    pending = null;
    drawStatic();
    $('#result').classList.add('hidden');
    resetSteps();
    $('#pickup').value = S.me.node;
    $('#drop').value = '';
    renderPanels();
    toast('Reset: all EVs back at their depots');
  };
  $('#rides').onclick = (e) => {
    const card = e.target.closest('.ride');
    if (!card) return;
    S.selected = S.selected === card.dataset.id ? null : card.dataset.id;
    renderPanels();
  };
  $('#legend').innerHTML = S.evs.map((ev) => `<span><i style="background:${ev.color}"></i>EV ${ev.num}</span>`).join('')
    + '<span><span class="line"></span>Trip route</span><span><span class="line dash"></span>EV heading to next stop</span>'
    + '<span><i style="background:#db2777"></i>You (drag me)</span>'
    + Object.entries({ Hostel: 'hostel', Academic: 'academic', Facility: 'facility' }).map(([l, k]) => `<span><i style="background:#fff;border:3px solid ${KIND_COLOR[k]};border-radius:4px"></i>${l}</span>`).join('');
}

function wireMapDeselect() {
  svg().addEventListener('click', (e) => {
    if (e.target === svg() || e.target.tagName === 'rect' && !e.target.closest('.node')) { S.selected = null; renderPanels(); }
  });
}

async function checkSarvam() {
  const pill = $('#sarvam-pill');
  try {
    const h = await (await fetch('/api/health')).json();
    sarvamOk = !!h.sarvam_key;
  } catch { sarvamOk = false; }
  pill.className = `pill ${sarvamOk ? 'ok' : 'warn'}`;
  pill.lastElementChild.textContent = sarvamOk ? 'Sarvam AI connected' : 'Sarvam key missing: voice off';
  $('#mic-btn').disabled = !sarvamOk;
  if (!sarvamOk) $('#mic-hint').textContent = 'Add SARVAM_API_KEY to .env to enable voice. Typing still works (offline rules).';
}

/* ------------------------------------------------------------------ boot */
// setInterval, not requestAnimationFrame: rAF pauses in background tabs / some projector setups,
// and the simulation must keep running for the demo.
let last = performance.now(), uiAcc = 0;
function frame() {
  const now = performance.now();
  const dtReal = Math.min(0.1, (now - last) / 1000);
  last = now;
  const dt = dtReal * simSpeed;
  S.simT += dt;
  for (const ev of S.evs) for (let rem = dt; rem > 1e-9; rem -= 0.5) step(ev, Math.min(0.5, rem));
  drawDynamic();
  uiAcc += dtReal;
  if (uiAcc > 0.25) { uiAcc = 0; renderPanels(); }
}

async function boot() {
  C = await (await fetch('/api/campus', { cache: 'no-store' })).json();
  for (const n of C.nodes) { NODES[n.id] = n; ADJ[n.id] = []; }
  for (const [a, b] of C.edges) {
    const m = Math.round(Math.hypot(NODES[a].x - NODES[b].x, NODES[a].y - NODES[b].y) * C.meters_per_px);
    EDGE_M[ekey(a, b)] = m;
    ADJ[a].push({ to: b, m });
    ADJ[b].push({ to: a, m });
  }
  S = initialState();
  drawStatic();
  wireMapDeselect();
  wireUi();
  renderPanels();
  checkSarvam();
  setInterval(frame, 1000 / 30);
}

window.CampusRide = { sp, bestEv, timeline, bookRide, get state() { return S; } };  // for debugging in the console
boot();
