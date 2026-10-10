const ICONS = {"check": "<path d=\"M20 6 9 17l-5-5\" />", "x": "<path d=\"M18 6 6 18\" /> <path d=\"m6 6 12 12\" />", "arrow-right": "<path d=\"M5 12h14\" /> <path d=\"m12 5 7 7-7 7\" />", "upload": "<path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\" /> <polyline points=\"17 8 12 3 7 8\" /> <line x1=\"12\" x2=\"12\" y1=\"3\" y2=\"15\" />", "shield-check": "<path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\" /> <path d=\"m9 12 2 2 4-4\" />", "search": "<circle cx=\"11\" cy=\"11\" r=\"8\" /> <path d=\"m21 21-4.3-4.3\" />", "send": "<path d=\"M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z\" /> <path d=\"m21.854 2.147-10.94 10.939\" />", "sparkles": "<path d=\"M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z\" /> <path d=\"M20 3v4\" /> <path d=\"M22 5h-4\" /> <path d=\"M4 17v2\" /> <path d=\"M5 18H3\" />", "globe": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20\" /> <path d=\"M2 12h20\" />", "command": "<path d=\"M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3\" />", "corner-down-left": "<polyline points=\"9 10 4 15 9 20\" /> <path d=\"M20 4v7a4 4 0 0 1-4 4H4\" />", "receipt-text": "<path d=\"M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z\" /> <path d=\"M14 8H8\" /> <path d=\"M16 12H8\" /> <path d=\"M13 16H8\" />", "lock": "<rect width=\"18\" height=\"11\" x=\"3\" y=\"11\" rx=\"2\" ry=\"2\" /> <path d=\"M7 11V7a5 5 0 0 1 10 0v4\" />", "smartphone": "<rect width=\"14\" height=\"20\" x=\"5\" y=\"2\" rx=\"2\" ry=\"2\" /> <path d=\"M12 18h.01\" />", "graduation-cap": "<path d=\"M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z\" /> <path d=\"M22 10v6\" /> <path d=\"M6 12.5V16a6 3 0 0 0 12 0v-3.5\" />", "briefcase-business": "<path d=\"M12 12h.01\" /> <path d=\"M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2\" /> <path d=\"M22 13a18.15 18.15 0 0 1-20 0\" /> <rect width=\"20\" height=\"14\" x=\"2\" y=\"6\" rx=\"2\" />", "shuffle": "<path d=\"M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22\" /> <path d=\"m18 2 4 4-4 4\" /> <path d=\"M2 6h1.9c1.5 0 2.9.9 3.6 2.2\" /> <path d=\"M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8\" /> <path d=\"m18 14 4 4-4 4\" />", "triangle-alert": "<path d=\"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3\" /> <path d=\"M12 9v4\" /> <path d=\"M12 17h.01\" />", "indian-rupee": "<path d=\"M6 3h12\" /> <path d=\"M6 8h12\" /> <path d=\"m6 13 8.5 8\" /> <path d=\"M6 13h3\" /> <path d=\"M9 13c6.667 0 6.667-10 0-10\" />", "languages": "<path d=\"m5 8 6 6\" /> <path d=\"m4 14 6-6 2-3\" /> <path d=\"M2 5h12\" /> <path d=\"M7 2h1\" /> <path d=\"m22 22-5-10-5 10\" /> <path d=\"M14 18h6\" />", "map-pin": "<path d=\"M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0\" /> <circle cx=\"12\" cy=\"10\" r=\"3\" />", "circle-check": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"m9 12 2 2 4-4\" />"};
const all = await figma.listAvailableFontsAsync();
const FM = {}; for (const f of all) { (FM[f.fontName.family] ||= new Set()).add(f.fontName.style); }
const SN = { 400: ['Regular'], 500: ['Medium'], 600: ['SemiBold', 'Semi Bold'], 700: ['Bold'], 800: ['ExtraBold', 'Extra Bold', 'Bold'] };
const loaded = new Set(); const usedFonts = new Set();
async function fnt(fams, w) {
  for (const fam of fams) { const s = FM[fam]; if (!s) continue;
    for (const st of SN[w]) if (s.has(st)) { const fn = { family: fam, style: st }; const k = fam + '|' + st;
      if (!loaded.has(k)) { await figma.loadFontAsync(fn); loaded.add(k); } usedFonts.add(k); return fn; } }
  const map = { 400: 'Regular', 500: 'Medium', 600: 'Semi Bold', 700: 'Bold', 800: 'Extra Bold' };
  const fn = { family: 'Inter', style: map[w] }; const k = 'Inter|' + fn.style;
  if (!loaded.has(k)) { await figma.loadFontAsync(fn); loaded.add(k); } usedFonts.add(k); return fn;
}
function hex(h) { h = h.replace('#', ''); return { r: parseInt(h.slice(0, 2), 16) / 255, g: parseInt(h.slice(2, 4), 16) / 255, b: parseInt(h.slice(4, 6), 16) / 255 }; }
function sp(h, o) { const p = { type: 'SOLID', color: hex(h) }; if (o != null) p.opacity = o; return p; }
let FAM = ['Inter'];
async function T(parent, str, o = {}) {
  let fams = o.f || FAM; if (/[₹↵⌘↑↓]/.test(str) && !fams[0].startsWith('Inter')) fams = ['Inter'];
  const t = figma.createText(); t.fontName = await fnt(fams, o.w || 400); t.characters = str;
  t.fontSize = o.s || 16; t.fills = [sp(o.c || '#111111')];
  t.lineHeight = o.lh ? { unit: 'PERCENT', value: o.lh } : { unit: 'AUTO' };
  if (o.ls != null) t.letterSpacing = { unit: 'PERCENT', value: o.ls };
  if (o.align) t.textAlignHorizontal = o.align;
  if (o.strike) t.textDecoration = 'STRIKETHROUGH';
  if (o.n) t.name = o.n;
  parent.appendChild(t);
  if (o.width) { t.resize(o.width, t.height); t.textAutoResize = 'HEIGHT'; }
  else if (o.fill) { t.textAutoResize = 'HEIGHT'; t.layoutSizingHorizontal = 'FILL'; }
  else if (o.grow) { t.textAutoResize = 'HEIGHT'; t.layoutGrow = 1; }
  return t;
}
async function hl(t, word, color, w) {
  const i = t.characters.indexOf(word); if (i < 0) return;
  t.setRangeFills(i, i + word.length, [sp(color)]);
  if (w) { const cur = t.fontName; t.setRangeFontName(i, i + word.length, await fnt([cur.family], w)); }
}
function AL(parent, dir, o = {}) {
  const f = figma.createAutoLayout(dir); f.name = o.n || (dir === 'VERTICAL' ? 'Stack' : 'Row');
  f.fills = o.bg ? [sp(o.bg, o.bgo)] : [];
  if (o.p != null) { const [t, r, b, l] = Array.isArray(o.p) ? (o.p.length === 2 ? [o.p[0], o.p[1], o.p[0], o.p[1]] : o.p) : [o.p, o.p, o.p, o.p];
    f.paddingTop = t; f.paddingRight = r; f.paddingBottom = b; f.paddingLeft = l; }
  f.itemSpacing = o.g || 0; if (o.r) f.cornerRadius = o.r;
  if (o.st) { f.strokes = [sp(o.st)]; f.strokeWeight = o.sw || 1; f.strokeAlign = 'INSIDE';
    if (o.sides) { f.strokeTopWeight = o.sides[0]; f.strokeRightWeight = o.sides[1]; f.strokeBottomWeight = o.sides[2]; f.strokeLeftWeight = o.sides[3]; } }
  if (o.ai) f.counterAxisAlignItems = o.ai; if (o.jc) f.primaryAxisAlignItems = o.jc;
  if (o.wrap) f.layoutWrap = 'WRAP';
  if (parent) parent.appendChild(f);
  if (o.w || o.h) { f.resize(o.w || f.width, o.h || f.height); f.layoutSizingHorizontal = o.w ? 'FIXED' : 'HUG'; f.layoutSizingVertical = o.h ? 'FIXED' : 'HUG'; }
  if (o.fill && parent) f.layoutSizingHorizontal = 'FILL';
  if (o.grow && parent) f.layoutGrow = 1;
  if (o.vfill && parent) f.layoutSizingVertical = 'FILL';
  if (o.clip != null) f.clipsContent = o.clip;
  if (o.shadow) f.effects = [{ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: o.shadow }, offset: { x: 0, y: 24 }, radius: 60, spread: -12, visible: true, blendMode: 'NORMAL' }];
  return f;
}
function icon(parent, name, size, color, sw) {
  const svg = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw || 2}" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">${ICONS[name]}</svg>`;
  const n = figma.createNodeFromSvg(svg); n.name = 'icon/' + name; n.resize(size, size); parent.appendChild(n); return n;
}
function box(parent, w, h, color, r, o) { const x = figma.createRectangle(); x.resize(w, h); x.fills = [sp(color, o)]; if (r) x.cornerRadius = r; parent.appendChild(x); return x; }
// Local component factory: build once, place instances, override text layers by name.
async function comp(name, dir, o, build) {
  const c = figma.createComponent(); c.name = name; c.layoutMode = dir; c.primaryAxisSizingMode = 'AUTO'; c.counterAxisSizingMode = 'AUTO';
  c.fills = o.bg ? [sp(o.bg)] : []; const [t, r, b, l] = o.p || [0, 0, 0, 0]; c.paddingTop = t; c.paddingRight = r; c.paddingBottom = b; c.paddingLeft = l;
  c.itemSpacing = o.g || 0; if (o.r) c.cornerRadius = o.r; c.counterAxisAlignItems = o.ai || 'CENTER';
  if (o.st) { c.strokes = [sp(o.st)]; c.strokeWeight = 1; c.strokeAlign = 'INSIDE'; if (o.sides) { c.strokeTopWeight = o.sides[0]; c.strokeRightWeight = o.sides[1]; c.strokeBottomWeight = o.sides[2]; c.strokeLeftWeight = o.sides[3]; } }
  COMPS.appendChild(c); await build(c);
  if (o.w) { c.resize(o.w, c.height); c.primaryAxisSizingMode = dir === 'HORIZONTAL' ? 'FIXED' : 'AUTO'; c.counterAxisSizingMode = dir === 'HORIZONTAL' ? 'AUTO' : 'FIXED'; }
  return c;
}
function inst(c, parent, texts, o = {}) {
  const i = c.createInstance(); parent.appendChild(i);
  for (const [k, v] of Object.entries(texts || {})) { const n = i.findOne(x => x.name === k && x.type === 'TEXT'); if (n) n.characters = v; }
  if (o.fill) i.layoutSizingHorizontal = 'FILL';
  return i;
}
let maxX = 0; for (const ch of figma.currentPage.children) maxX = Math.max(maxX, ch.x + ch.width);
const COMPS = figma.createAutoLayout('HORIZONTAL'); COMPS.name = 'Components · C + D'; COMPS.fills = []; COMPS.itemSpacing = 40; COMPS.counterAxisAlignItems = 'MIN';
let X = maxX + 200; const OUT = { pages: [], fonts: null };
function page(name, x, bg) {
  x = X; X += 1560;
  const p = figma.createAutoLayout('VERTICAL'); p.name = name; p.fills = [sp(bg)]; p.resize(1440, 100); p.layoutSizingHorizontal = 'FIXED'; p.layoutSizingVertical = 'HUG';
  p.x = x; p.y = 0; p.clipsContent = true; return p;
}

// ===== Fixes for A and B =====
{
  await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });
  const A = await figma.getNodeByIdAsync('1:3');
  for (const t of A.findAllWithCriteria({ types: ['TEXT'] })) if (t.characters === 'Backed by your facts' || t.characters === 'Removed before sending') { t.textAutoResize = 'HEIGHT'; t.layoutSizingHorizontal = 'FILL'; }
  const B = await figma.getNodeByIdAsync('1:135');
  for (const t of B.findAllWithCriteria({ types: ['TEXT'] })) if (t.characters === 'Ctrl K' && t.parent && t.parent.type === 'FRAME') { const p = t.parent; p.layoutSizingHorizontal = 'HUG'; p.paddingLeft = 14; p.paddingRight = 14; }
  OUT.fixed = ['1:3', '1:135'];
}
// ===== Concept C: Warm — mass-market, phone-first, rounded, Indian warmth =====
{
FAM = ['Bricolage Grotesque', 'Plus Jakarta Sans', 'Inter'];
const BODY = ['Plus Jakarta Sans', 'Inter'];
const FOREST = '#0E3B2C', LIME = '#C8F169', CREAM = '#FFF8EE', INK = '#10241C', MU = '#55665E', PEACH = '#FFD8BF', WHITE = '#FFFFFF', LINE = '#E7E2D8', OK = '#1B7F4B', ERR = '#C2410C';
const P = page('C · Warm — phone-first, mass market', 0, WHITE); OUT.pages.push(P.id);
const btnC = await comp('C/Button lime', 'HORIZONTAL', { bg: LIME, p: [18, 26, 18, 26], g: 10, r: 99 }, async c => { icon(c, 'upload', 18, FOREST); await T(c, 'Upload your resume', { n: 'label', s: 17, w: 700, c: FOREST, f: BODY }); });
const chipC = await comp('C/Trust chip', 'HORIZONTAL', { bg: CREAM, p: [12, 18, 12, 14], g: 10, r: 99, st: LINE }, async c => { icon(c, 'check', 16, OK, 2.5); await T(c, 'No fees. Ever.', { n: 'label', s: 15, w: 600, c: INK, f: BODY }); });
const nav = AL(P, 'HORIZONTAL', { n: 'Nav', p: [24, 56], ai: 'CENTER', g: 36 }); nav.layoutSizingHorizontal = 'FILL';
const lg = AL(nav, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); const mk = AL(lg, 'HORIZONTAL', { w: 34, h: 34, r: 11, bg: FOREST, jc: 'CENTER', ai: 'CENTER' }); icon(mk, 'arrow-right', 18, LIME, 2.5); await T(lg, 'ApplyScout', { s: 21, w: 700, c: INK, ls: -2 });
const ln = AL(nav, 'HORIZONTAL', { g: 30, grow: true }); for (const l of ['How it works', 'For students', 'Pricing', 'Help']) await T(ln, l, { s: 15, w: 500, c: MU, f: BODY });
const lang = AL(nav, 'HORIZONTAL', { p: [8, 14], r: 99, st: LINE, g: 6, ai: 'CENTER' }); icon(lang, 'languages', 15, INK); await T(lang, 'English', { s: 14, w: 500, c: INK, f: BODY });
const navb = AL(nav, 'HORIZONTAL', { p: [12, 20], r: 99, bg: FOREST }); await T(navb, 'Get started free', { s: 14, w: 700, c: WHITE, f: BODY });
// hero panel
const wrap = AL(P, 'VERTICAL', { n: 'Hero wrap', p: [8, 24, 0, 24] }); wrap.layoutSizingHorizontal = 'FILL';
const hero = AL(wrap, 'HORIZONTAL', { n: 'Hero', bg: FOREST, r: 40, p: [80, 72, 0, 72], g: 40, fill: true, clip: true });
const hc = AL(hero, 'VERTICAL', { g: 26, w: 600, p: [0, 0, 80, 0] });
const tag = AL(hc, 'HORIZONTAL', { p: [8, 14], r: 99, bg: '#1A4D3B', g: 8, ai: 'CENTER' }); box(tag, 8, 8, LIME, 4); await T(tag, 'Made for freshers and early careers in India', { s: 14, w: 500, c: '#D9E7DF', f: BODY });
const h1 = await T(hc, 'Get hired for who you really are.', { s: 80, w: 800, c: WHITE, lh: 98, ls: -4, width: 600 }); await hl(h1, 'really', LIME);
await T(hc, 'Maggie finds jobs that fit, writes a resume for each one from your real experience, and asks before sending anything. In English or Hindi.', { s: 20, lh: 150, c: '#CFE0D7', f: BODY, width: 520 });
const hb = AL(hc, 'HORIZONTAL', { g: 16, ai: 'CENTER' }); inst(btnC, hb, {}); await T(hb, 'Free for 10 applications', { s: 15, w: 500, c: '#CFE0D7', f: BODY });
// phones
const phones = AL(hero, 'HORIZONTAL', { g: 24, ai: 'MAX', grow: true, p: [10, 0, 0, 0] });
const phone = (h) => { const ph = AL(phones, 'VERTICAL', { w: 300, h, r: 44, bg: '#0B0F0D', p: [12, 12, 0, 12] }); const sc = AL(ph, 'VERTICAL', { r: 34, bg: CREAM, p: [26, 18, 18, 18], g: 12, fill: true, vfill: true, clip: true }); sc.topRightRadius = 34; sc.bottomLeftRadius = 0; sc.bottomRightRadius = 0; return sc; };
const s1 = phone(560);
await T(s1, 'Good morning, Priya', { s: 13, c: MU, f: BODY }); await T(s1, '3 jobs are ready for you', { s: 22, w: 700, c: INK, lh: 115, width: 260 });
for (const [L, col, t, m2, st] of [['R', '#2D6CDF', 'Product Analyst', 'Razorpay · 92% fit', 'Ready'], ['S', '#E8590C', 'Associate PM', 'Swiggy · 88% fit', 'Ready'], ['Z', '#7048E8', 'Business Analyst', 'Zerodha · 84% fit', '1 question']]) {
  const r = AL(s1, 'HORIZONTAL', { p: 12, g: 10, r: 18, bg: WHITE, ai: 'CENTER', fill: true, st: LINE });
  const c = AL(r, 'HORIZONTAL', { w: 36, h: 36, r: 12, bg: col, jc: 'CENTER', ai: 'CENTER' }); await T(c, L, { s: 15, w: 700, c: WHITE });
  const tx = AL(r, 'VERTICAL', { g: 1, grow: true }); await T(tx, t, { s: 14, w: 700, c: INK, f: BODY }); await T(tx, m2, { s: 12, c: MU, f: BODY });
  const b = AL(r, 'HORIZONTAL', { p: [4, 9], r: 99, bg: st === 'Ready' ? '#E3F4EA' : PEACH }); await T(b, st, { s: 11, w: 700, c: st === 'Ready' ? OK : ERR, f: BODY });
}
const s2 = phone(500);
await T(s2, 'Razorpay · Product Analyst', { s: 12, w: 600, c: MU, f: BODY }); await T(s2, 'Check before sending', { s: 22, w: 700, c: INK, width: 260 });
for (const [ok, t] of [[1, 'Built SQL dashboards for 3 payment flows'], [1, 'Ran 4 A/B tests, +9% activation'], [0, 'Led a team of 6 — not true, removed']]) { const r = AL(s2, 'HORIZONTAL', { p: 12, g: 10, r: 16, bg: ok ? '#E3F4EA' : '#FDE8DC', ai: 'CENTER', fill: true }); icon(r, ok ? 'check' : 'x', 16, ok ? OK : ERR, 2.5); await T(r, t, { s: 13, w: 600, c: ok ? INK : ERR, f: BODY, grow: true }); }
const sb = AL(s2, 'HORIZONTAL', { p: [16, 0], r: 99, bg: FOREST, jc: 'CENTER', fill: true }); await T(sb, 'Approve & send', { s: 15, w: 700, c: LIME, f: BODY });
// trust chips
const trust = AL(P, 'HORIZONTAL', { n: 'Trust', p: [40, 56], g: 12, jc: 'CENTER', wrap: true }); trust.layoutSizingHorizontal = 'FILL';
for (const t of ['No fees. Ever.', 'Sent from your own Gmail', 'Nothing sent without your OK', 'Pay with UPI', 'Cancel in one tap', 'Scam jobs blocked']) inst(chipC, trust, { label: t });
// who it's for
const who = AL(P, 'VERTICAL', { n: 'Who', p: [72, 56, 40, 56], g: 36 }); who.layoutSizingHorizontal = 'FILL';
await T(who, 'Wherever you are in your career,\nwe start from what you have done.', { s: 48, w: 800, c: INK, ls: -3, lh: 105, width: 900 });
const cards = AL(who, 'HORIZONTAL', { g: 20, fill: true });
for (const [ic, col, h, d, eg] of [['graduation-cap', LIME, 'Freshers', 'Turns projects, internships and college work into facts recruiters can check.', 'B.Tech 2026 · first job'], ['briefcase-business', PEACH, '1–6 years', 'Finds the next step up and tailors around results you really delivered.', 'Analyst → Product Analyst'], ['shuffle', '#D9E8FF', 'Switching', 'Shows which skills transfer, and is honest about what is missing.', 'Ops → Product']]) {
  const c = AL(cards, 'VERTICAL', { p: 28, g: 12, r: 28, bg: CREAM, grow: true });
  const i = AL(c, 'HORIZONTAL', { w: 52, h: 52, r: 16, bg: col, jc: 'CENTER', ai: 'CENTER' }); icon(i, ic, 24, FOREST);
  await T(c, h, { s: 26, w: 800, c: INK, ls: -2 }); await T(c, d, { s: 16, lh: 150, c: MU, f: BODY, fill: true });
  const e = AL(c, 'HORIZONTAL', { p: [6, 12], r: 99, bg: WHITE }); await T(e, eg, { s: 13, w: 600, c: INK, f: BODY });
}
// pricing
const pr = AL(P, 'VERTICAL', { n: 'Pricing', p: [80, 56, 40, 56], g: 32 }); pr.layoutSizingHorizontal = 'FILL';
await T(pr, 'Less than one coffee a week.', { s: 48, w: 800, c: INK, ls: -3, width: 900 });
const pcs = AL(pr, 'HORIZONTAL', { g: 20, fill: true });
for (const [n, p2, per, items, hi] of [['Free', '₹0', '', ['10 applications', 'Truth-checked resumes', 'Receipts'], 0], ['Pro', '₹299', '/month', ['20 applications a day', 'Send from your Gmail', 'Hindi + English'], 1], ['Max', '₹799', '/month', ['50 a day', 'Referral finder', 'Priority support'], 0]]) {
  const c = AL(pcs, 'VERTICAL', { p: 32, g: 14, r: 28, bg: hi ? FOREST : WHITE, st: hi ? null : LINE, grow: true });
  await T(c, n, { s: 18, w: 700, c: hi ? LIME : INK, f: BODY });
  const pp = AL(c, 'HORIZONTAL', { g: 6, ai: 'MAX' }); await T(pp, p2, { s: 56, w: 800, c: hi ? WHITE : INK, ls: -3, f: ['Inter'] }); if (per) await T(pp, per, { s: 16, c: hi ? '#CFE0D7' : MU, f: BODY });
  for (const it of items) { const r = AL(c, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); icon(r, 'check', 16, hi ? LIME : OK, 2.5); await T(r, it, { s: 15, c: hi ? WHITE : INK, f: BODY }); }
}
await T(pr, 'Prices include GST. Example prices for this design.', { s: 13, c: MU, f: BODY });
const end = AL(P, 'VERTICAL', { n: 'CTA', p: [24, 24, 24, 24] }); end.layoutSizingHorizontal = 'FILL';
const eb = AL(end, 'VERTICAL', { bg: LIME, r: 40, p: [72, 72], g: 24, ai: 'CENTER', fill: true });
await T(eb, 'Your next job starts with one upload.', { s: 56, w: 800, c: FOREST, ls: -3, align: 'CENTER', width: 900 });
const ebb = AL(eb, 'HORIZONTAL', { p: [18, 28], r: 99, bg: FOREST, g: 10, ai: 'CENTER' }); icon(ebb, 'upload', 18, LIME); await T(ebb, 'Upload your resume', { s: 17, w: 700, c: LIME, f: BODY });
}
// ===== Concept D: Global — one product, many markets and languages =====
{
FAM = ['Noto Sans', 'Inter'];
const DEV = ['Noto Sans Devanagari'], ARB = ['Noto Sans Arabic'];
const hasDev = !!FM['Noto Sans Devanagari'], hasArb = !!FM['Noto Sans Arabic'];
const INK = '#0B1220', MU = '#596273', LINE = '#E4E7EC', BG = '#FFFFFF', SOFT = '#F6F7F9', SAFF = '#FF7A1A', OK = '#12805C', ERR = '#C8332B';
const P = page('D · Global — multi-market, multi-language', 0, BG); OUT.pages.push(P.id);
const btnD = await comp('D/Button', 'HORIZONTAL', { bg: INK, p: [16, 24, 16, 24], g: 10, r: 12 }, async c => { await T(c, 'Upload your resume', { n: 'label', s: 16, w: 600, c: '#FFFFFF' }); icon(c, 'arrow-right', 18, '#FFFFFF'); });
const mkt = await comp('D/Market card', 'VERTICAL', { bg: BG, p: [28, 28, 28, 28], g: 12, r: 20, st: LINE, ai: 'MIN', w: 400 }, async c => {
  const top = AL(c, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); icon(top, 'map-pin', 18, SAFF); await T(top, 'India', { n: 'market', s: 22, w: 700, c: INK });
  await T(c, '₹299 / month', { n: 'price', s: 36, w: 700, c: INK, f: ['Inter'] });
  await T(c, 'Roles from Bengaluru, Pune, Hyderabad, Gurugram and remote', { n: 'roles', s: 15, c: MU, lh: 150, fill: true });
  const pay = AL(c, 'HORIZONTAL', { p: [6, 12], r: 99, bg: SOFT }); await T(pay, 'UPI · English + Hindi', { n: 'pay', s: 13, w: 600, c: INK });
});
const nav = AL(P, 'HORIZONTAL', { n: 'Nav', p: [20, 64], ai: 'CENTER', g: 40, st: LINE, sides: [0, 0, 1, 0] }); nav.layoutSizingHorizontal = 'FILL';
const lg = AL(nav, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); const mk = AL(lg, 'HORIZONTAL', { w: 28, h: 28, r: 8, bg: INK, jc: 'CENTER', ai: 'CENTER' }); box(mk, 8, 8, SAFF, 4); await T(lg, 'ApplyScout', { s: 18, w: 700, c: INK });
const ln = AL(nav, 'HORIZONTAL', { g: 28, grow: true }); for (const l of ['Product', 'Markets', 'Trust', 'Pricing']) await T(ln, l, { s: 15, c: MU });
const sw = AL(nav, 'HORIZONTAL', { p: [4, 4], r: 10, bg: SOFT, g: 2 });
for (const [l, on, f] of [['EN', 1, FAM], [hasDev ? 'हिं' : 'HI', 0, hasDev ? DEV : FAM], [hasArb ? 'ع' : 'AR', 0, hasArb ? ARB : FAM]]) { const b = AL(sw, 'HORIZONTAL', { p: [6, 12], r: 7, bg: on ? BG : null, st: on ? LINE : null }); await T(b, l, { s: 13, w: 600, c: on ? INK : MU, f }); }
const cur = AL(nav, 'HORIZONTAL', { p: [8, 12], r: 10, st: LINE, g: 6, ai: 'CENTER' }); icon(cur, 'globe', 15, INK); await T(cur, 'India · ₹', { s: 13, w: 600, c: INK, f: ['Inter'] });
inst(btnD, nav, { label: 'Get started' });
const hero = AL(P, 'VERTICAL', { n: 'Hero', p: [96, 64, 56, 64], g: 24 }); hero.layoutSizingHorizontal = 'FILL';
const ey = AL(hero, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); box(ey, 24, 2, SAFF); await T(ey, 'INDIA  ·  UAE  ·  SINGAPORE', { s: 13, w: 700, c: MU, ls: 12 });
await T(hero, 'Truthful job applications,\nin your market and your language.', { s: 72, w: 700, c: INK, ls: -4, lh: 102, width: 1200 });
const trans = AL(hero, 'HORIZONTAL', { g: 40, ai: 'CENTER', p: [8, 0] });
await T(trans, 'Every line true.', { s: 28, w: 600, c: INK });
if (hasDev) { box(trans, 1, 28, LINE); await T(trans, 'हर लाइन सच।', { s: 28, w: 600, c: INK, f: DEV }); }
if (hasArb) { box(trans, 1, 28, LINE); const ar = await T(trans, 'كل سطر صادق.', { s: 28, w: 600, c: INK, f: ARB }); }
const hrow = AL(hero, 'HORIZONTAL', { g: 16, ai: 'CENTER', p: [12, 0, 0, 0] }); inst(btnD, hrow, {}); await T(hrow, 'Free to start in every market · No card', { s: 15, c: MU });
// product band
const band = AL(P, 'HORIZONTAL', { n: 'Product band', bg: SOFT, p: [56, 64], g: 40 }); band.layoutSizingHorizontal = 'FILL';
const card = AL(band, 'VERTICAL', { bg: BG, r: 20, st: LINE, p: 28, g: 14, w: 640, shadow: 0.08 });
const chead = AL(card, 'HORIZONTAL', { g: 10, ai: 'CENTER', fill: true }); await T(chead, 'Resume for Careem · Product Analyst · Dubai', { s: 15, w: 600, c: INK, grow: true }); const fp = AL(chead, 'HORIZONTAL', { p: [4, 10], r: 99, bg: '#FFF1E6' }); await T(fp, '89% fit', { s: 12, w: 700, c: '#B4500C' });
for (const [ok, t, f] of [[1, 'Built SQL dashboards tracking checkout drop-off across 3 payment flows.', 'F2'], [1, 'Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.', 'F4'], [0, 'Fluent in Arabic.', '']]) {
  const r = AL(card, 'HORIZONTAL', { g: 12, ai: 'MIN', fill: true, p: [10, 0], st: LINE, sides: [1, 0, 0, 0] }); icon(r, ok ? 'check' : 'x', 18, ok ? OK : ERR, 2.5);
  await T(r, t, { s: 15, c: ok ? INK : '#98A2B3', strike: !ok, lh: 145, grow: true });
  const tg = AL(r, 'HORIZONTAL', { p: [3, 8], r: 6, bg: ok ? '#E7F5EF' : '#FDECEA' }); await T(tg, ok ? f : 'Not in your facts', { s: 11, w: 700, c: ok ? OK : ERR });
}
const bc = AL(band, 'VERTICAL', { g: 18, grow: true, p: [16, 0] });
await T(bc, 'The same honest standard, everywhere you apply.', { s: 34, w: 700, c: INK, ls: -2, lh: 115, fill: true });
for (const [ic, t] of [['languages', 'Resumes in English, with Hindi and Arabic interfaces'], ['shield-check', 'A claim that is not in your facts never ships, in any language'], ['receipt-text', 'Receipts and local pricing with GST or VAT included']]) { const r = AL(bc, 'HORIZONTAL', { g: 12, ai: 'CENTER', fill: true }); const i = AL(r, 'HORIZONTAL', { w: 36, h: 36, r: 10, bg: BG, st: LINE, jc: 'CENTER', ai: 'CENTER' }); icon(i, ic, 18, INK); await T(r, t, { s: 16, c: INK, grow: true }); }
// markets
const ms = AL(P, 'VERTICAL', { n: 'Markets', p: [96, 64, 40, 64], g: 32 }); ms.layoutSizingHorizontal = 'FILL';
await T(ms, 'Built in India. Ready for the Gulf and Southeast Asia.', { s: 44, w: 700, c: INK, ls: -3, width: 1000 });
const mr = AL(ms, 'HORIZONTAL', { g: 20, fill: true });
for (const [m3, p3, r3, pay] of [['India', '₹299 / month', 'Bengaluru, Pune, Hyderabad, Gurugram and remote', 'UPI · English + Hindi'], ['United Arab Emirates', 'AED 39 / month', 'Dubai and Abu Dhabi, including visa-sponsored roles', 'Card · English + Arabic'], ['Singapore', 'SGD 15 / month', 'Singapore and remote roles across Southeast Asia', 'PayNow · English']]) {
  const i = inst(mkt, mr, { market: m3, price: p3, roles: r3, pay }); i.layoutGrow = 1;
}
await T(ms, 'Example prices for this design. Gulf and SEA launch later; India first.', { s: 13, c: MU });
const fin = AL(P, 'VERTICAL', { n: 'CTA', bg: INK, p: [96, 64], g: 24 }); fin.layoutSizingHorizontal = 'FILL';
const f1 = await T(fin, 'One resume. Every market. Every line true.', { s: 56, w: 700, c: '#FFFFFF', ls: -3, width: 1100 }); await hl(f1, 'Every line true.', SAFF);
const fb = AL(fin, 'HORIZONTAL', { bg: '#FFFFFF', p: [16, 24], r: 12, g: 10, ai: 'CENTER' }); await T(fb, 'Upload your resume', { s: 16, w: 600, c: INK }); icon(fb, 'arrow-right', 18, INK);
OUT.dev = hasDev; OUT.arb = hasArb;
}

COMPS.x = (await figma.getNodeByIdAsync(OUT.pages[0])).x; COMPS.y = -700;
const info = [];
for (const id of OUT.pages) { const n = await figma.getNodeByIdAsync(id); info.push({ id, name: n.name, h: Math.round(n.height), texts: n.findAllWithCriteria({types:['TEXT']}).length, inst: n.findAllWithCriteria({types:['INSTANCE']}).length }); }
for (const id of OUT.pages) { const n = await figma.getNodeByIdAsync(id); await n.screenshot({ scale: 0.35 }); }
return { pages: info, fixed: OUT.fixed, dev: OUT.dev, arb: OUT.arb, comps: COMPS.children.map(c => c.id + ' ' + c.name), fonts: [...usedFonts] };
