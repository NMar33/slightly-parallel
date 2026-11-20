// Flow sheets of the feature map: draws SPEC into svg#fig. Three variants.
// Plain SVG, no library; text is measured after the fonts load.
const NS = 'http://www.w3.org/2000/svg'
const INK = '#0b0b0b', INK2 = '#52514e', MUTED = '#898781', REC = '#3d3c39', SURF = '#fbfbf9', GRID = '#e6e5df'
const fmt = (n) => (n == null ? '' : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '))
let SVG

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag)
  for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k])
  ;(parent || SVG).appendChild(e)
  return e
}
function txt(x, y, s, o = {}, parent) {
  const e = el('text', {
    x, y, 'font-size': o.size || 14, 'font-weight': o.weight || 500, fill: o.fill || INK,
    'text-anchor': o.anchor || 'start', class: o.mono ? 'm' : null, 'letter-spacing': o.ls || null,
    'dominant-baseline': o.base || 'middle', transform: o.transform || null, opacity: o.opacity || null,
    stroke: o.halo ? SURF : null, 'stroke-width': o.halo ? 5 : null, 'paint-order': o.halo ? 'stroke' : null, 'stroke-linejoin': o.halo ? 'round' : null,
  }, parent)
  e.textContent = s
  return e
}
function width(e) { return e.getComputedTextLength() }
function ribbon(x0, a0, b0, x1, a1, b1, color, op = 0.42, parent) {
  const m = (x0 + x1) / 2
  return el('path', {
    d: `M${x0},${a0} C${m},${a0} ${m},${a1} ${x1},${a1} L${x1},${b1} C${m},${b1} ${m},${b0} ${x0},${b0} Z`,
    fill: color, 'fill-opacity': op,
  }, parent)
}
function thread(x0, y0, x1, y1, color, dash) {
  const m = (x0 + x1) / 2
  return el('path', { d: `M${x0},${y0} C${m},${y0} ${m},${y1} ${x1},${y1}`, fill: 'none', stroke: color, 'stroke-width': 1.3, 'stroke-dasharray': dash ? '3 3' : null, opacity: 0.9 })
}
function zigzag(x, y, w, color) {
  // a break mark across a bar: two parallel zigzags on the surface colour
  const g = el('g', {})
  for (const dy of [-3, 3]) {
    let d = `M${x - 4},${y + dy}`
    const n = 4, step = (w + 8) / n
    for (let i = 1; i <= n; i++) d += ` L${x - 4 + i * step},${y + dy + (i % 2 ? -3 : 3)}`
    el('path', { d, stroke: SURF, 'stroke-width': 2.4, fill: 'none' }, g)
  }
  return g
}

// Units: a stream's drawn size. Over BIG it is drawn at CAP with a break.
function unitsOf(S, n) { return n > S.big ? S.cap : n }

function prep(S) {
  const C = S.colors
  const rec = Object.fromEntries(S.records.map((r) => [r.id, { ...r, inU: 0, ins: [], brk: false }]))
  for (const s of S.streams) {
    s.u = unitsOf(S, s.n)
    s.brk = s.n > S.big
    s.color = C[s.who]
    s.acolor = C[s.actor_who]
    rec[s.rec].inU += s.u
    rec[s.rec].ins.push(s)
    if (s.brk) rec[s.rec].brk = true
  }
  return { C, rec }
}

const GROUPS = [
  { who: 'o', title: 'ОПЕРАТОР', sub: (S) => `${fmt(S.messages)} сообщений · команда в ${fmt(S.with_command)}` },
  { who: 'a', title: 'АГЕНТ САМ', sub: () => 'без команды' },
  { who: 's', title: 'ПРОГРАММА САМА', sub: () => 'хук и сервер' },
]
const ACTORS = [
  { id: 'agent', label: 'Агент', sub: 'пишет через MCP', who: 'a' },
  { id: 'srv', label: 'Сервер', sub: 'хранит слова, двигает задачи', who: 's' },
  { id: 'hook', label: 'Хук', sub: 'записывает чат, узнаёт тег', who: 's' },
]
const CLUSTERS = { tasks: 'Задачи', cores: 'Ядра', work: 'Работа агента', kept: 'Слова оператора', marks: 'Метки', prog: 'Сама программа' }

// ---------------------------------------------------------------- river
function river(S) {
  const W = 1412
  const { C, rec } = prep(S)
  const X1 = 372, X2 = 650, X3 = 900, BW = 10
  const MIN = 18, GAP = 3, GGAP = 44
  // stream order: by group, then actor, then record order
  const recOrder = Object.fromEntries(S.records.map((r, i) => [r.id, i]))
  const actOrder = { agent: 0, srv: 1, hook: 2 }
  const groups = GROUPS.map((g) => ({ ...g, items: S.streams.filter((s) => s.who === g.who)
    .sort((a, b) => actOrder[a.actor] - actOrder[b.actor] || recOrder[a.rec] - recOrder[b.rec]) }))
  const totalU = S.streams.reduce((t, s) => t + s.u, 0)
  const K = 0.5
  const h = (u) => Math.max(u * K, u > 0 ? 1.6 : 0)
  // column 1
  let y = 34
  for (const g of groups) {
    y += GGAP
    g.y0 = y
    for (const s of g.items) {
      const hh = h(s.u)
      const slot = Math.max(hh, MIN)
      s.y = y + (slot - hh) / 2
      s.h = hh
      s.cy = y + slot / 2
      y += slot + GAP
    }
    g.y1 = y - GAP
  }
  const H1 = y
  // column 3: records
  let yr = 34 + GGAP
  let lastCl = null
  const recs = S.records.map((r) => rec[r.id])
  for (const r of recs) {
    if (lastCl && r.cluster !== lastCl) yr += 16
    lastCl = r.cluster
    const hh = h(r.inU)
    const slot = Math.max(hh, 22)
    r.y = yr + (slot - hh) / 2
    r.h = hh
    r.cy = yr + slot / 2
    yr += slot + 6
  }
  // column 2: actors, sized by what goes through
  const acts = ACTORS.map((a) => ({ ...a, items: S.streams.filter((s) => s.actor === a.id) }))
  for (const a of acts) a.u = a.items.reduce((t, s) => t + s.u, 0)
  const AG = 70
  const H2 = acts.reduce((t, a) => t + h(a.u), 0) + AG * (acts.length - 1)
  const Htot = Math.max(H1, yr) + 10
  let ya = 34 + GGAP + Math.max(0, (Math.max(H1, yr) - 34 - GGAP - H2) / 2)
  for (const a of acts) { a.y = ya; a.h = h(a.u); ya += a.h + AG }
  SVG.setAttribute('width', W); SVG.setAttribute('height', Htot)
  SVG.setAttribute('viewBox', `0 0 ${W} ${Htot}`)

  // column heads
  const head = (x, s, anchor) => txt(x, 10, s, { mono: true, size: 11.5, fill: MUTED, ls: 1.2, anchor })
  head(0, 'КТО НАЧИНАЕТ')
  head(X1 + BW, 'ЧТО ПРИХОДИТ · ЗА 30 ДНЕЙ', 'end')
  head(X2 - 30, 'КТО ДЕЛАЕТ')
  head(X3, 'ЗАПИСИ')

  // ribbons column 1 → 2 (colour: who started)
  for (const a of acts) {
    let off = a.y
    for (const s of a.items.sort((p, q) => p.cy - q.cy)) {
      s.ay = off; off += s.h
      if (s.n === 0) thread(X1 + BW, s.cy, X2, s.ay, s.color, true)
      else ribbon(X1 + BW, s.y, s.y + s.h, X2, s.ay, s.ay + s.h, s.color)
    }
  }
  // ribbons column 2 → 3 (colour: who does it), one per actor and record
  const pairs = []
  for (const a of acts) {
    const by = {}
    for (const s of a.items) (by[s.rec] = by[s.rec] || { a, r: rec[s.rec], u: 0, n: 0, zero: true }), by[s.rec].u += s.u, by[s.rec].n += s.n, by[s.rec].zero &&= s.n === 0
    let off = a.y
    for (const p of Object.values(by).sort((p, q) => p.r.cy - q.r.cy)) { p.ay = off; p.h = h(p.u); off += p.h; pairs.push(p) }
  }
  for (const r of recs) {
    let off = r.y
    for (const p of pairs.filter((p) => p.r === r).sort((p, q) => actOrder[p.a.id] - actOrder[q.a.id])) {
      p.ry = off; off += p.h
      if (p.zero) thread(X2 + 16, p.ay, X3, r.cy, C[p.a.who], true)
      else ribbon(X2 + 16, p.ay, p.ay + p.h, X3, p.ry, p.ry + p.h, C[p.a.who])
    }
  }

  // column 1 bars, labels, group heads
  for (const g of groups) {
    const gc = C[g.who]
    el('rect', { x: 0, y: g.y0, width: 4, height: g.y1 - g.y0, fill: gc, rx: 2 })
    txt(0, g.y0 - 28, g.title, { mono: true, size: 12.5, weight: 600, fill: INK, ls: 1.2 })
    txt(0, g.y0 - 11, g.sub(S), { size: 13, fill: INK2 })
    for (const s of g.items) {
      el('rect', { x: X1, y: s.y, width: BW, height: Math.max(s.h, 1.6), fill: gc })
      if (s.brk) zigzag(X1, s.y + s.h / 2, BW)
      const isCmd = s.label.startsWith('#')
      txt(X1 - 8, s.cy, fmt(s.n), { mono: true, size: 13, weight: 500, anchor: 'end', fill: s.n ? INK : MUTED })
      txt(X1 - 62, s.cy, s.label, { mono: isCmd, size: isCmd ? 13.5 : 14, weight: isCmd ? 600 : 500, anchor: 'end' })
    }
  }
  // actors
  for (const a of acts) {
    el('rect', { x: X2, y: a.y, width: 16, height: a.h, fill: C[a.who], rx: 2 })
    txt(X2 - 30, a.y - 30, a.label, { size: 18, weight: 800, halo: true })
    txt(X2 - 30, a.y - 12, a.sub, { size: 12.5, fill: INK2, halo: true })
  }
  // records
  let rightmost = 0
  lastCl = null
  for (const r of recs) {
    el('rect', { x: X3, y: r.y, width: BW, height: Math.max(r.h, 1.6), fill: REC })
    if (r.brk) zigzag(X3, r.y + r.h / 2, BW)
    const t1 = txt(X3 + BW + 10, r.cy, r.label, { size: 14.5, weight: 700 })
    let x = X3 + BW + 10 + width(t1) + 7
    const t2 = txt(x, r.cy, r.id === 'reply' ? '' : fmt(r.n), { mono: true, size: 13.5, weight: 600 })
    x += (r.id === 'reply' ? 0 : width(t2) + 9)
    const t3 = txt(x, r.cy, r.page, { size: 12.5, fill: MUTED })
    r.end = r.page ? x + width(t3) : x - 9
    rightmost = Math.max(rightmost, r.end)
    if (r.cluster !== lastCl) {
      txt(X3 - 8, r.y - 2, CLUSTERS[r.cluster].toUpperCase(), { mono: true, size: 10.5, fill: INK2, anchor: 'end', ls: 1, base: 'auto', halo: true })
      lastCl = r.cluster
    }
  }
  linksRail(S, rec, recs, rightmost, head)
}

function linksRail(S, rec, recs, rightmost, head) {
  const links = S.links.filter((l) => rec[l.a] && rec[l.b]).map((l) => ({ ...l, ya: rec[l.a].cy, yb: rec[l.b].cy }))
    .map((l) => ({ ...l, lo: Math.min(l.ya, l.yb), hi: Math.max(l.ya, l.yb) }))
  links.sort((p, q) => (p.hi - p.lo) - (q.hi - q.lo))
  const LANE = 9
  const RX = rightmost + 14
  const LX = RX + 14 + LANE * links.length + 10
  head(RX, 'СВЯЗИ МЕЖДУ ЗАПИСЯМИ')
  for (const r of recs) if (links.some((l) => l.a === r.id || l.b === r.id)) {
    el('path', { d: `M${r.end + 8},${r.cy} H${RX}`, stroke: REC, 'stroke-opacity': 0.35, 'stroke-width': 1, 'stroke-dasharray': '1 3' })
    el('circle', { cx: RX, cy: r.cy, r: 3.2, fill: REC })
  }
  const placed = []
  links.forEach((l, i) => {
    const x = RX + 14 + LANE * i
    const sw = l.n == null ? 1.4 : Math.max(1.6, Math.min(Math.sqrt(l.n) * 0.4, 6))
    const r = 6
    el('path', { d: `M${RX},${l.lo} H${x - r} Q${x},${l.lo} ${x},${l.lo + r} V${l.hi - r} Q${x},${l.hi} ${x - r},${l.hi} H${RX}`,
      fill: 'none', stroke: REC, 'stroke-opacity': 0.6, 'stroke-width': sw, 'stroke-dasharray': l.n === 0 ? '3 3' : null, 'stroke-linejoin': 'round' })
    const free = (y) => !placed.some((p) => Math.abs(p - y) < 19)
    let ly = [l.yb, l.ya, (l.ya + l.yb) / 2].find(free)
    if (ly == null) { ly = (l.ya + l.yb) / 2; while (!free(ly)) ly += 19 }
    placed.push(ly)
    el('path', { d: `M${x},${ly} H${LX - 4}`, stroke: REC, 'stroke-opacity': 0.45, 'stroke-width': 1, 'stroke-dasharray': '1 2.5' })
    const tn = txt(LX, ly, fmt(l.n), { mono: true, size: 13, weight: 600 })
    txt(LX + (l.n == null ? 0 : width(tn) + 6), ly, l.label, { size: 12.5, fill: INK2 })
  })
}

function draw(S, variant) {
  SVG = document.getElementById('fig')
  if (variant === 'river') river(S)
  else if (variant === 'star') star(S)
  else metro(S)
}

// a ribbon between two vertical segments, the second on a circle: (x0, a0..b0) → points q0, q1 with outward normal n
function ribbonTo(x0, a0, b0, q0, q1, n, color, dir = 1, op = 0.42) {
  const d0 = Math.abs(q0[0] - x0) * 0.5, d1 = Math.abs(q1[0] - x0) * 0.5
  return el('path', {
    d: `M${x0},${a0} C${x0 + dir * d0},${a0} ${q0[0] + n[0] * d0 * 0.8},${q0[1] + n[1] * d0 * 0.8} ${q0[0]},${q0[1]} L${q1[0]},${q1[1]} C${q1[0] + n[0] * d1 * 0.8},${q1[1] + n[1] * d1 * 0.8} ${x0 + dir * d1},${b0} ${x0},${b0} Z`,
    fill: color, 'fill-opacity': op,
  })
}
function labelRecord(r, x, y) {
  const t1 = txt(x, y, r.label, { size: 14.5, weight: 700 })
  let e = x + width(t1) + 7
  if (r.id !== 'reply') { const t2 = txt(e, y, fmt(r.n), { mono: true, size: 13.5, weight: 600 }); e += width(t2) + 9 }
  if (r.page) { const t3 = txt(e, y, r.page, { size: 12.5, fill: MUTED }); e += width(t3) } else e -= 9
  return e
}

// ---------------------------------------------------------------- star
function star(S) {
  const W = 1412
  const { C, rec } = prep(S)
  const K = 0.36, MIN = 18, GAP = 3, GGAP = 44, BW = 10
  const h = (u) => Math.max(u * K, u > 0 ? 1.6 : 0)
  const recOrder = Object.fromEntries(S.records.map((r, i) => [r.id, i]))
  const actOrder = { agent: 0, srv: 1, hook: 2 }
  const groups = GROUPS.map((g) => ({ ...g, items: S.streams.filter((s) => s.who === g.who)
    .sort((a, b) => actOrder[a.actor] - actOrder[b.actor] || recOrder[a.rec] - recOrder[b.rec]) }))
  let y = 30
  for (const g of groups) {
    y += GGAP; g.y0 = y
    for (const s of g.items) { const hh = h(s.u), slot = Math.max(hh, MIN); s.y = y + (slot - hh) / 2; s.h = hh; s.cy = y + slot / 2; y += slot + GAP }
    g.y1 = y - GAP
  }
  const H = y + 10
  const recs = S.records.map((r) => rec[r.id])
  let yr = 30 + GGAP, lastCl = null
  for (const r of recs) { if (lastCl && r.cluster !== lastCl) yr += 14; lastCl = r.cluster; const hh = h(r.inU), slot = Math.max(hh, 22); r.y = yr + (slot - hh) / 2; r.h = hh; r.cy = yr + slot / 2; yr += slot + 5 }
  const off0 = (H - yr) / 2
  for (const r of recs) { r.y += off0; r.cy += off0 }
  SVG.setAttribute('width', W); SVG.setAttribute('height', H); SVG.setAttribute('viewBox', `0 0 ${W} ${H}`)

  // the hub
  const cx = 600, cy = H / 2 + 10, R = 250
  const RX = 330, RY = H / 2 - 30
  const colX = (yy, side) => cx + side * RX * Math.sqrt(Math.max(0, 1 - ((yy - cy) / (RY + 60)) ** 2))
  const acts = ACTORS.map((a) => ({ ...a, items: S.streams.filter((s) => s.actor === a.id) }))
  for (const a of acts) a.u = a.items.reduce((t, s) => t + s.u, 0)
  // arc length on each side: actors stacked top → bottom on the left (in) and right (out)
  const totalArc = acts.reduce((t, a) => t + h(a.u), 0)
  const GA = 0.16
  const span = totalArc / R + GA * 2
  let ang = Math.PI / 2 + (Math.PI - span) / 2  // from the top-left, going down the left side
  const P = (t, side) => { const x = cx + Math.cos(t) * R * (side < 0 ? 1 : -1), yy = cy - Math.sin(t) * R; return [x, yy] }
  const N = (t, side) => [Math.cos(t) * (side < 0 ? 1 : -1), -Math.sin(t)]
  for (const a of acts) { a.t0 = ang; a.t1 = ang + h(a.u) / R; ang = a.t1 + GA }

  // inflow
  for (const g of groups) for (const s of g.items) s.x = colX(s.cy, -1)
  for (const a of acts) {
    let t = a.t0
    for (const s of a.items.sort((p, q) => p.cy - q.cy)) {
      const t2 = t + s.h / R
      if (s.n === 0) { const q = P(t, -1); thread(s.x + BW, s.cy, q[0], q[1], s.color, true) }
      else ribbonTo(s.x + BW, s.y, s.y + s.h, P(t, -1), P(t2, -1), N(t, -1), s.color, 1)
      t = t2
    }
  }
  // outflow
  for (const r of recs) r.x = colX(r.cy, 1)
  const pairs = []
  for (const a of acts) {
    const by = {}
    for (const s of a.items) (by[s.rec] = by[s.rec] || { a, r: rec[s.rec], u: 0, zero: true }), by[s.rec].u += s.u, by[s.rec].zero &&= s.n === 0
    let t = a.t0
    for (const p of Object.values(by).sort((p, q) => p.r.cy - q.r.cy)) { p.h = h(p.u); p.t0 = t; p.t1 = t + p.h / R; t = p.t1; pairs.push(p) }
  }
  for (const r of recs) {
    let off = r.y
    for (const p of pairs.filter((p) => p.r === r).sort((p, q) => actOrder[p.a.id] - actOrder[q.a.id])) {
      if (p.zero) { const q = P(p.t0, 1); thread(q[0], q[1], r.x, r.cy, C[p.a.who], true) }
      else ribbonTo(r.x, off, off + p.h, P(p.t0, 1), P(p.t1, 1), N(p.t0, 1), C[p.a.who], -1)
      off += p.h
    }
  }
  // circle and ring
  el('circle', { cx, cy, r: R - 14, fill: '#0b0b0b' })
  for (const a of acts) for (const side of [-1, 1]) {
    const p0 = P(a.t0, side), p1 = P(a.t1, side)
    const r0 = R - 7
    const q0 = [cx + (p0[0] - cx) * r0 / R, cy + (p0[1] - cy) * r0 / R], q1 = [cx + (p1[0] - cx) * r0 / R, cy + (p1[1] - cy) * r0 / R]
    el('path', { d: `M${q0[0]},${q0[1]} A${r0},${r0} 0 0 ${side < 0 ? 0 : 1} ${q1[0]},${q1[1]}`, stroke: C[a.who], 'stroke-width': 12, fill: 'none' })
  }
  txt(cx, cy - 172, 'Slightly Parallel', { size: 26, weight: 800, fill: '#fff', anchor: 'middle' })
  for (const a of acts) {
    const ym = cy - Math.sin((a.t0 + a.t1) / 2) * R
    const yy = Math.max(cy - 105, Math.min(cy + 175, ym))
    txt(cx, yy - 10, a.label, { size: 19, weight: 800, fill: '#fff', anchor: 'middle' })
    txt(cx, yy + 12, a.sub, { size: 13, fill: '#c9c8c2', anchor: 'middle' })
  }
  // left labels
  for (const g of groups) {
    const gx = colX(g.y0, -1)
    txt(gx + BW, g.y0 - 26, g.title, { mono: true, size: 12.5, weight: 600, ls: 1.2, anchor: 'end' })
    txt(gx + BW, g.y0 - 10, g.sub(S), { size: 13, fill: INK2, anchor: 'end' })
    for (const s of g.items) {
      el('rect', { x: s.x, y: s.y, width: BW, height: Math.max(s.h, 1.6), fill: C[g.who] })
      if (s.brk) zigzag(s.x, s.y + s.h / 2, BW)
      const isCmd = s.label.startsWith('#')
      const tn = txt(s.x - 8, s.cy, fmt(s.n), { mono: true, size: 13, weight: 500, anchor: 'end', fill: s.n ? INK : MUTED })
      txt(s.x - 16 - Math.max(width(tn), 22), s.cy, s.label, { mono: isCmd, size: isCmd ? 13.5 : 14, weight: isCmd ? 600 : 500, anchor: 'end' })
    }
  }
  // records
  let rightmost = 0
  lastCl = null
  for (const r of recs) {
    el('rect', { x: r.x, y: r.y, width: BW, height: Math.max(r.h, 1.6), fill: REC })
    if (r.brk) zigzag(r.x, r.y + r.h / 2, BW)
    r.end = labelRecord(r, r.x + BW + 10, r.cy)
    rightmost = Math.max(rightmost, r.end)
  }
  const head = (x, s, anchor) => txt(x, 10, s, { mono: true, size: 11.5, fill: MUTED, ls: 1.2, anchor })
  head(0, 'ЧТО ПРИХОДИТ · ЗА 30 ДНЕЙ')
  head(colX(30, 1), 'ЗАПИСИ')
  linksRail(S, rec, recs, rightmost, head)
}

// ---------------------------------------------------------------- metro: records as stations
const BOXES = [
  { cl: 'tasks', row: 0, x: 0, w: 640, cols: 3, order: ['tasks', 'done', 'notes', null, 'evidence', 'commits'] },
  { cl: 'cores', row: 0, x: 656, w: 200, cols: 1 },
  { cl: 'work', row: 0, x: 872, w: 540, cols: 3 },
  { cl: 'kept', row: 1, x: 0, w: 1040, cols: 5 },
  { cl: 'marks', row: 1, x: 1056, w: 356, cols: 2 },
  { cl: 'prog', row: 2, x: 0, w: 1412, cols: 5 },
]
function metro(S) {
  const W = 1412
  const { C, rec } = prep(S)
  const recs = S.records.map((r) => rec[r.id])
  const rad = (u) => 7 + Math.sqrt(u) * 2.3
  const LH = 17
  // feeds of each station, largest first
  for (const r of recs) {
    r.feeds = [...r.ins].sort((p, q) => q.n - p.n)
    r.R = rad(r.inU)
  }
  let rowTop = 30, rowBottom = 30, curRow = 0
  const placed = []
  for (const b of BOXES) {
    let items = recs.filter((r) => r.cluster === b.cl)
    if (!items.length) continue
    if (b.order) items = [...b.order.map((id) => (id ? items.find((r) => r.id === id) : null)), ...items.filter((r) => !b.order.includes(r.id))]
    if (b.row !== curRow) { curRow = b.row; rowTop = rowBottom + 16 }
    const y0 = rowTop
    const cw = b.w / b.cols
    let y = y0 + 44
    for (let i = 0; i < items.length; i += b.cols) {
      const row = items.slice(i, i + b.cols)
      const real = row.filter(Boolean)
      const rmax = Math.max(...real.map((r) => r.R))
      const fmax = Math.max(...real.map((r) => r.feeds.length))
      row.forEach((r, j) => { if (r) { r.cx = b.x + cw * j + cw / 2; r.cy = y + rmax + 6 } })
      y += 2 * rmax + 6 + 14 + 26 + fmax * LH + 18
    }
    b.y0 = y0; b.h = y - y0
    placed.push(b)
    rowBottom = Math.max(rowBottom, y)
  }
  const H = Math.max(...placed.map((b) => b.y0 + b.h)) + 6
  SVG.setAttribute('width', W); SVG.setAttribute('height', H); SVG.setAttribute('viewBox', `0 0 ${W} ${H}`)
  // equalize the heights of the boxes in a row
  for (const row of [0, 1, 2].map((k) => placed.filter((b) => b.row === k))) {
    if (!row.length) continue
    const top = Math.min(...row.map((b) => b.y0)), bot = Math.max(...row.map((b) => b.y0 + b.h))
    for (const b of row) { b.y0 = top; b.h = bot - top }
  }
  for (const b of placed) {
    el('rect', { x: b.x, y: b.y0, width: b.w, height: b.h, rx: 14, fill: '#f1f1ee' })
    txt(b.x + 16, b.y0 + 22, CLUSTERS[b.cl].toUpperCase(), { mono: true, size: 12, weight: 600, fill: INK2, ls: 1.2 })
  }
  // links: a group under the stations, filled once the text is placed
  const linkG = el('g', {})
  const ls = S.links.filter((l) => rec[l.a] && rec[l.b])
  const lab = []
  // stations
  for (const r of recs) {
    // ring: who started, in order operator, agent, program
    const byWho = { o: 0, a: 0, s: 0 }
    for (const f of r.feeds) byWho[f.who] += f.u
    const tot = r.inU || 1
    let ang = -Math.PI / 2
    const RR = r.R + 6
    for (const w of ['o', 'a', 's']) {
      if (!byWho[w]) continue
      const a1 = ang + 2 * Math.PI * byWho[w] / tot - (byWho[w] < tot ? 0.06 : 0)
      if (byWho[w] >= tot) el('circle', { cx: r.cx, cy: r.cy, r: RR, fill: 'none', stroke: C[w], 'stroke-width': 7 })
      else el('path', { d: `M${r.cx + RR * Math.cos(ang)},${r.cy + RR * Math.sin(ang)} A${RR},${RR} 0 ${a1 - ang > Math.PI ? 1 : 0} 1 ${r.cx + RR * Math.cos(a1)},${r.cy + RR * Math.sin(a1)}`, fill: 'none', stroke: C[w], 'stroke-width': 7 })
      ang = a1 + 0.06
    }
    el('circle', { cx: r.cx, cy: r.cy, r: r.R, fill: REC, stroke: SURF, 'stroke-width': 2 })
    if (r.brk) txt(r.cx, r.cy, '≫', { size: 13, fill: '#fff', anchor: 'middle', weight: 700 })
    let y = r.cy + r.R + 6 + 20
    const t1 = txt(r.cx, y, r.label, { size: 14.5, weight: 700, anchor: 'middle', halo: true })
    y += 19
    const sub = (r.id === 'reply' ? '' : fmt(r.n)) + (r.page ? (r.id === 'reply' ? '' : '  ·  ') + r.page : '')
    txt(r.cx, y, sub, { mono: r.id !== 'reply', size: 12.5, weight: 500, fill: INK2, anchor: 'middle', halo: true })
    // feeds, one line each: a colour chip, the stream, its count
    y += 6
    for (const f of r.feeds) {
      y += LH
      const g = el('g', {})
      const isCmd = f.short.startsWith('#')
      const tl = txt(0, y, f.short, { mono: isCmd, size: isCmd ? 12 : 12.5, weight: isCmd ? 600 : 500, fill: INK, halo: true }, g)
      const tn = txt(0, y, fmt(f.n), { mono: true, size: 12, fill: f.n ? INK2 : MUTED, halo: true }, g)
      const wl = width(tl), wn = width(tn)
      const total = 12 + wl + 6 + wn
      const x0 = r.cx - total / 2
      el('rect', { x: x0, y: y - 4, width: 8, height: 8, rx: 2, fill: C[f.who] }, g)
      tl.setAttribute('x', x0 + 12); tn.setAttribute('x', x0 + 12 + wl + 6)
    }
  }
  // link labels on top
  const boxes = [...SVG.querySelectorAll('text')].map((t) => t.getBBox())
  const circ = recs.map((r) => ({ r, x: r.cx - r.R - 10, y: r.cy - r.R - 10, width: 2 * r.R + 20, height: 2 * r.R + 20 }))
  const inside = (b, x, y) => x > b.x && x < b.x + b.width && y > b.y && y < b.y + b.height
  for (const l of ls) {
    const a = rec[l.a], b = rec[l.b]
    const dx = b.cx - a.cx, dy = b.cy - a.cy, len = Math.hypot(dx, dy)
    let best = null
    for (const k of [0.12, -0.12, 0.25, -0.25, 0.4, -0.4]) {
      const mx = (a.cx + b.cx) / 2 - dy * k, my = (a.cy + b.cy) / 2 + dx * k
      let cost = Math.abs(k) * 2
      for (let t = 0.05; t < 0.96; t += 0.03) {
        const x = (1 - t) ** 2 * a.cx + 2 * (1 - t) * t * mx + t * t * b.cx
        const y = (1 - t) ** 2 * a.cy + 2 * (1 - t) * t * my + t * t * b.cy
        cost += boxes.filter((q) => inside(q, x, y)).length + 3 * circ.filter((c) => c.r !== a && c.r !== b && inside(c, x, y)).length
      }
      if (!best || cost < best.cost) best = { cost, mx, my }
    }
    const { mx, my } = best
    const sw = l.n == null ? 2 : Math.max(2.5, Math.min(Math.sqrt(l.n) * 0.7, 14))
    el('path', { d: `M${a.cx},${a.cy} Q${mx},${my} ${b.cx},${b.cy}`, fill: 'none', stroke: REC, 'stroke-opacity': 0.5, 'stroke-width': sw, 'stroke-dasharray': l.n === 0 ? '5 4' : null, 'stroke-linecap': 'round' }, linkG)
    lab.push({ l, a, b, mx, my })
  }
  boxes.push(...circ)
  const hit = (q) => boxes.some((b) => q.x < b.x + b.width && q.x + q.width > b.x && q.y < b.y + b.height && q.y + q.height > b.y)
  for (const { l, a, b, mx, my } of lab) {
    const g = el('g', {})
    const tn = txt(0, -8, fmt(l.n), { mono: true, size: 13, weight: 700, anchor: 'middle', halo: true }, g)
    const tl = txt(0, 8, l.label, { size: 12.5, fill: INK2, anchor: 'middle', halo: true }, g)
    const w = Math.max(width(tn), width(tl)) + 8
    let best = null
    for (const t of [0.5, 0.4, 0.6, 0.3, 0.7, 0.25, 0.75, 0.2, 0.8]) {
      const x = (1 - t) ** 2 * a.cx + 2 * (1 - t) * t * mx + t * t * b.cx
      const y = (1 - t) ** 2 * a.cy + 2 * (1 - t) * t * my + t * t * b.cy
      for (const dy of [0, -24, 24, -44, 44]) {
        const q = { x: x - w / 2, y: y + dy - 18, width: w, height: 36 }
        if (!hit(q)) { best = { x, y: y + dy, q }; break }
      }
      if (best) break
    }
    if (!best) { const x = (a.cx + b.cx) / 4 + mx / 2, y = (a.cy + b.cy) / 4 + my / 2; best = { x, y, q: { x: x - w / 2, y: y - 18, width: w, height: 36 } } }
    boxes.push(best.q)
    g.setAttribute('transform', `translate(${best.x},${best.y})`)
  }
  txt(W, 10, 'КОЛЬЦО — КТО НАЧАЛ · ЛИНИЯ — СВЯЗЬ МЕЖДУ ЗАПИСЯМИ', { mono: true, size: 11.5, fill: MUTED, ls: 1.2, anchor: 'end' })
  txt(0, 10, 'ЗАПИСИ ЗА 30 ДНЕЙ И ЧТО В НИХ ВХОДИТ', { mono: true, size: 11.5, fill: MUTED, ls: 1.2 })
}
