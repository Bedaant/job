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
const COMPS = figma.createAutoLayout('HORIZONTAL'); COMPS.name = 'Components · A + B'; COMPS.fills = []; COMPS.itemSpacing = 40; COMPS.counterAxisAlignItems = 'MIN';
let X = maxX + 200; const OUT = { pages: [], fonts: null };
function page(name, x, bg) {
  x = X; X += 1560;
  const p = figma.createAutoLayout('VERTICAL'); p.name = name; p.fills = [sp(bg)]; p.resize(1440, 100); p.layoutSizingHorizontal = 'FIXED'; p.layoutSizingVertical = 'HUG';
  p.x = x; p.y = 0; p.clipsContent = true; return p;
}

// ===== Concept A: Redline (Swiss / International Typographic Style) =====
{
FAM = ['Inter Tight', 'Inter'];
const INK = '#0A0A0A', RED = '#FF3B00', MUT = '#5E5E5E', RULE = '#E3E3E3', BG = '#FFFFFF', SOFT = '#F5F5F3';
const P = page('A · Redline — Swiss editorial', maxX + 200, BG); OUT.pages.push(P.id);
const btnA = await comp('A/Button', 'HORIZONTAL', { bg: INK, p: [16, 22, 16, 22], g: 10 }, async c => { await T(c, 'Upload your resume', { n: 'label', s: 16, w: 600, c: '#FFFFFF' }); icon(c, 'arrow-right', 18, '#FFFFFF'); });
const btnA2 = await comp('A/Button secondary', 'HORIZONTAL', { p: [15, 22, 15, 22], g: 10, st: INK }, async c => { await T(c, 'See a real example', { n: 'label', s: 16, w: 600, c: INK }); });
// nav
const nav = AL(P, 'HORIZONTAL', { n: 'Nav', p: [22, 64], ai: 'CENTER', g: 48, st: RULE, sides: [0, 0, 1, 0] }); nav.layoutSizingHorizontal = 'FILL';
const logo = AL(nav, 'HORIZONTAL', { n: 'Logo', g: 8, ai: 'CENTER' }); box(logo, 14, 14, RED); await T(logo, 'ApplyScout', { s: 19, w: 700, ls: -3 });
const links = AL(nav, 'HORIZONTAL', { n: 'Links', g: 32, grow: true });
for (const l of ['Product', 'Method', 'Pricing', 'For colleges']) await T(links, l, { s: 15, w: 500, c: MUT });
await T(nav, 'Log in', { s: 15, w: 500 }); inst(btnA, nav, { label: 'Upload resume' });
// hero
const hero = AL(P, 'HORIZONTAL', { n: 'Hero', p: [88, 64, 72, 64], g: 64 }); hero.layoutSizingHorizontal = 'FILL';
const hl1 = AL(hero, 'VERTICAL', { n: 'Hero copy', g: 28, w: 720 });
const lab = AL(hl1, 'HORIZONTAL', { g: 12, ai: 'CENTER' }); await T(lab, '01', { s: 13, w: 600, c: RED }); box(lab, 40, 1, INK); await T(lab, 'Job applications, verified line by line', { s: 13, w: 500, c: MUT, ls: 2 });
const h1 = await T(hl1, 'Every line\ntrue.', { s: 148, w: 700, lh: 88, ls: -6, width: 720 }); await hl(h1, 'true.', RED);
await T(hl1, 'ApplyScout finds jobs that fit you, rewrites your resume for each one using only facts you have confirmed, and sends nothing until you say so.', { s: 21, lh: 145, c: '#2B2B2B', width: 560 });
const ctas = AL(hl1, 'HORIZONTAL', { g: 12 }); inst(btnA, ctas, {}); inst(btnA2, ctas, {});
await T(hl1, '10 free applications · No card · Pay in ₹ with UPI', { s: 13, c: MUT });
// resume with redline marks
const docW = AL(hero, 'VERTICAL', { n: 'Redlined resume', g: 0, grow: true, p: [0, 0, 0, 0] });
const doc = AL(docW, 'VERTICAL', { n: 'Document', bg: BG, st: INK, p: [28, 32], g: 18, fill: true });
const dh = AL(doc, 'HORIZONTAL', { g: 8, ai: 'CENTER', fill: true }); const dht = AL(dh, 'VERTICAL', { g: 2, grow: true });
await T(dht, 'Priya Sharma', { s: 20, w: 700, ls: -2 }); await T(dht, 'Tailored for Razorpay · Product Analyst', { s: 13, c: MUT });
const fit = AL(dh, 'HORIZONTAL', { p: [6, 10], bg: INK, g: 6, ai: 'CENTER' }); await T(fit, 'FIT 92', { s: 12, w: 700, c: '#FFFFFF', ls: 4 });
box(doc, 10, 1, INK).layoutSizingHorizontal = 'FILL';
await T(doc, 'EXPERIENCE — ONECARD, 2023–NOW', { s: 11, w: 600, c: MUT, ls: 8 });
const lines = [['Built SQL dashboards tracking checkout drop-off across 3 payment flows.', 'F2 F7', 0], ['Ran 4 A/B tests on onboarding copy; one lifted activation by 9%.', 'F4', 0], ['Led a team of 6 analysts.', '', 1], ['Owned weekly reporting for the payments leadership review.', 'F7', 0]];
for (const [txt, f, bad] of lines) {
  const r = AL(doc, 'HORIZONTAL', { g: 14, ai: 'MIN', fill: true });
  const l = await T(r, txt, { s: 15, lh: 145, c: bad ? '#9A9A9A' : INK, strike: !!bad, fill: false, width: 330 });
  const note = AL(r, 'VERTICAL', { g: 2, grow: true, p: [3, 0, 0, 12], st: bad ? RED : RULE, sides: [0, 0, 0, 2] });
  if (bad) { await T(note, 'No source', { s: 12, w: 700, c: RED }); await T(note, 'Removed before sending', { s: 12, c: RED }); }
  else { await T(note, f, { s: 12, w: 700, c: RED, ls: 4 }); await T(note, 'Backed by your facts', { s: 12, c: MUT }); }
}
const dfoot = AL(doc, 'HORIZONTAL', { g: 8, ai: 'CENTER', fill: true, p: [14, 0, 0, 0], st: RULE, sides: [1, 0, 0, 0] });
icon(dfoot, 'shield-check', 16, INK); await T(dfoot, '3 of 3 lines backed · 1 removed', { s: 13, w: 600, grow: true });
const ap = AL(dfoot, 'HORIZONTAL', { bg: RED, p: [9, 14], g: 8, ai: 'CENTER' }); await T(ap, 'Approve & send', { s: 13, w: 700, c: '#FFFFFF' });
// facts strip
const stats = AL(P, 'HORIZONTAL', { n: 'Facts strip', p: [0, 64], g: 0 }); stats.layoutSizingHorizontal = 'FILL';
for (const [n, d] of [['6', 'job sources searched every hour'], ['1', 'approval from you before every send'], ['0', 'invented lines. Unbacked claims are removed'], ['₹0', 'to start. Pro is ₹299 a month']]) {
  const c = AL(stats, 'VERTICAL', { g: 10, p: [28, 24, 32, 0], grow: true, st: INK, sides: [2, 0, 0, 0] });
  await T(c, n, { s: 64, w: 700, ls: -5 }); await T(c, d, { s: 15, c: MUT, lh: 140, width: 240 });
}
// method
const m = AL(P, 'VERTICAL', { n: 'Method', p: [120, 64, 96, 64], g: 56 }); m.layoutSizingHorizontal = 'FILL';
const mh = AL(m, 'HORIZONTAL', { g: 64, fill: true, ai: 'MAX' }); const mhl = AL(mh, 'VERTICAL', { g: 16, w: 620 });
const lab2 = AL(mhl, 'HORIZONTAL', { g: 12, ai: 'CENTER' }); await T(lab2, '02', { s: 13, w: 600, c: RED }); box(lab2, 40, 1, INK); await T(lab2, 'The method', { s: 13, w: 500, c: MUT, ls: 2 });
await T(mhl, 'Fewer applications.\nEach one defensible.', { s: 56, w: 700, ls: -4, lh: 100, width: 620 });
await T(mh, 'Mass auto-apply tools send hundreds of padded resumes and hope. Recruiters notice. ApplyScout sends fewer, better applications — and you can defend every line in the interview.', { s: 18, lh: 150, c: '#2B2B2B', width: 520 });
const steps = AL(m, 'HORIZONTAL', { g: 0, fill: true });
for (const [n, h, d] of [['A', 'Find', 'Roles from Greenhouse, Lever, Workday, Ashby and company career pages, ranked by real fit.'], ['B', 'Tailor', 'Your resume rewritten for each job. Every line footnoted to a fact you confirmed.'], ['C', 'Approve', 'You see the exact file and message. Nothing leaves without your tap.'], ['D', 'Track', 'A receipt for every send. Replies and follow-ups in one list.']]) {
  const s = AL(steps, 'VERTICAL', { g: 14, p: [24, 28, 0, 0], grow: true, st: RULE, sides: [1, 0, 0, 0] });
  await T(s, n, { s: 15, w: 700, c: RED }); await T(s, h, { s: 26, w: 700, ls: -3 }); await T(s, d, { s: 15, lh: 150, c: MUT, width: 260 });
}
// statement band
const band = AL(P, 'VERTICAL', { n: 'Statement', bg: INK, p: [120, 64], g: 32 }); band.layoutSizingHorizontal = 'FILL';
const s1 = await T(band, 'Most AI tools write what sounds good.\nWe write what is true.', { s: 76, w: 700, ls: -5, lh: 98, c: '#FFFFFF', width: 1200 }); await hl(s1, 'true.', RED);
const bctas = AL(band, 'HORIZONTAL', { g: 24, ai: 'CENTER' }); const wb = AL(bctas, 'HORIZONTAL', { bg: '#FFFFFF', p: [16, 22], g: 10, ai: 'CENTER' }); await T(wb, 'Upload your resume', { s: 16, w: 600 }); icon(wb, 'arrow-right', 18, INK);
await T(bctas, 'No fees. No fake experience. Cancel in one tap.', { s: 15, c: '#A3A3A3' });
const ft = AL(P, 'HORIZONTAL', { n: 'Footer', p: [32, 64], g: 24, ai: 'CENTER' }); ft.layoutSizingHorizontal = 'FILL';
await T(ft, '© 2026 ApplyScout · Made in Bengaluru', { s: 13, c: MUT }); const sp1 = AL(ft, 'HORIZONTAL', { grow: true });
for (const l of ['Privacy', 'Security', 'Report a scam', 'Contact']) await T(ft, l, { s: 13, c: MUT });
}

// ===== Concept B: Command (Raycast/Linear-grade dark, keyboard-first) =====
{
FAM = ['Geist', 'Inter'];
const MONO = ['Geist Mono', 'JetBrains Mono', 'Roboto Mono', 'Inter'];
const BG = '#09090A', S1 = '#121214', S2 = '#18181B', LN = '#26262B', TX = '#F4F4F5', MU = '#A1A1AA', DIM = '#71717A', LIME = '#D7FF3A', OK = '#3DDC97', ERR = '#FF6B6B';
const P = page('B · Command — keyboard-first dark', 0, BG); OUT.pages.push(P.id);
const btnB = await comp('B/Button primary', 'HORIZONTAL', { bg: LIME, p: [13, 18, 13, 18], g: 10, r: 10 }, async c => { await T(c, 'Upload your resume', { n: 'label', s: 15, w: 600, c: '#0A0A0A' }); const k = AL(c, 'HORIZONTAL', { p: [2, 6], r: 5, st: '#0A0A0A', ai: 'CENTER' }); await T(k, '↵', { s: 11, w: 600, c: '#0A0A0A' }); });
const btnB2 = await comp('B/Button ghost', 'HORIZONTAL', { bg: S2, p: [13, 18, 13, 18], g: 10, r: 10, st: LN }, async c => { await T(c, 'Watch the 60-sec demo', { n: 'label', s: 15, w: 500, c: TX }); });
const rowB = await comp('B/Result row', 'HORIZONTAL', { p: [10, 14, 10, 14], g: 12, r: 8, w: 680 }, async c => {
  const lg = AL(c, 'HORIZONTAL', { w: 26, h: 26, r: 6, bg: '#2D6CDF', jc: 'CENTER', ai: 'CENTER' }); lg.name = 'logo'; await T(lg, 'R', { n: 'letter', s: 12, w: 700, c: '#FFFFFF' });
  const t = AL(c, 'VERTICAL', { g: 1, grow: true }); await T(t, 'Product Analyst', { n: 'title', s: 14, w: 500, c: TX }); await T(t, 'Razorpay · Bengaluru · ₹14–18 LPA', { n: 'meta', s: 12, c: DIM });
  await T(c, '6/8 skills', { n: 'skills', s: 12, c: MU, f: MONO }); const f = AL(c, 'HORIZONTAL', { p: [3, 8], r: 6, bg: '#1F2A12' }); await T(f, '92', { n: 'fit', s: 12, w: 600, c: LIME, f: MONO });
});
const nav = AL(P, 'HORIZONTAL', { n: 'Nav', p: [18, 48], ai: 'CENTER', g: 40, st: LN, sides: [0, 0, 1, 0] }); nav.layoutSizingHorizontal = 'FILL';
const lg = AL(nav, 'HORIZONTAL', { g: 10, ai: 'CENTER' }); const mk = AL(lg, 'HORIZONTAL', { w: 24, h: 24, r: 7, bg: LIME, jc: 'CENTER', ai: 'CENTER' }); icon(mk, 'arrow-right', 14, '#0A0A0A', 2.5); await T(lg, 'ApplyScout', { s: 16, w: 600, c: TX });
const ln = AL(nav, 'HORIZONTAL', { g: 28, grow: true }); for (const l of ['Product', 'Shortcuts', 'Security', 'Pricing', 'Changelog']) await T(ln, l, { s: 14, c: MU });
await T(nav, 'Log in', { s: 14, c: MU }); inst(btnB, nav, { label: 'Get started' });
const hero = AL(P, 'VERTICAL', { n: 'Hero', p: [96, 48, 0, 48], g: 22, ai: 'CENTER' }); hero.layoutSizingHorizontal = 'FILL';
const pill = AL(hero, 'HORIZONTAL', { p: [6, 12, 6, 8], g: 8, r: 99, st: LN, bg: S1, ai: 'CENTER' }); const nw = AL(pill, 'HORIZONTAL', { p: [2, 8], r: 99, bg: LIME }); await T(nw, 'New', { s: 11, w: 700, c: '#0A0A0A' }); await T(pill, 'Approve applications from WhatsApp-style chat', { s: 13, c: MU });
await T(hero, 'Your job search,\non command.', { s: 84, w: 600, ls: -5, lh: 96, c: TX, align: 'CENTER', width: 1000 });
await T(hero, 'Type what you want. Maggie finds the roles, tailors a truthful resume for each, and queues them for your approval.', { s: 19, lh: 150, c: MU, align: 'CENTER', width: 640 });
const cta = AL(hero, 'HORIZONTAL', { g: 10 }); inst(btnB, cta, {}); inst(btnB2, cta, {});
// command palette
const stage = AL(hero, 'VERTICAL', { n: 'Command palette', p: [56, 0, 0, 0], ai: 'CENTER' });
const pal = AL(stage, 'VERTICAL', { w: 760, r: 16, bg: S1, st: LN, clip: true, shadow: 0.6 });
const inp = AL(pal, 'HORIZONTAL', { p: [18, 20], g: 12, ai: 'CENTER', fill: true, st: LN, sides: [0, 0, 1, 0] }); icon(inp, 'search', 18, MU);
const q = await T(inp, 'product analyst roles in Bengaluru that fit me', { s: 17, c: TX, grow: true }); box(inp, 2, 20, LIME);
const esc = AL(inp, 'HORIZONTAL', { p: [3, 7], r: 6, st: LN }); await T(esc, 'esc', { s: 11, c: DIM, f: MONO });
const body = AL(pal, 'VERTICAL', { p: [10, 10], g: 2, fill: true });
await T(body, 'MATCHES · 24', { s: 11, w: 600, c: DIM, ls: 6, f: MONO });
const rows = [['R', '#2D6CDF', 'Product Analyst', 'Razorpay · Bengaluru · ₹14–18 LPA', '6/8 skills', '92'], ['S', '#E8590C', 'Associate Product Manager', 'Swiggy · Bengaluru · Hybrid', '5/7 skills', '88'], ['Z', '#7048E8', 'Business Analyst', 'Zerodha · Bengaluru · On-site', '7/9 skills', '84']];
let first = true;
for (const [L, col, t, mtx, sk, f] of rows) { const i = inst(rowB, body, { letter: L, title: t, meta: mtx, skills: sk, fit: f }, { fill: true }); i.findOne(n => n.name === 'logo').fills = [sp(col)]; if (first) { i.fills = [sp(S2)]; first = false; } }
await T(body, 'ACTIONS', { s: 11, w: 600, c: DIM, ls: 6, f: MONO });
for (const [ic, t, k, c] of [['sparkles', 'Tailor resume for Razorpay — truth-checked', '↵', TX], ['send', 'Approve 2 ready applications', 'Ctrl ↵', TX], ['receipt-text', 'Show receipts from this week', 'Ctrl R', TX]]) {
  const r = AL(body, 'HORIZONTAL', { p: [10, 14], g: 12, r: 8, ai: 'CENTER', fill: true }); icon(r, ic, 16, MU); await T(r, t, { s: 14, c, grow: true }); const kk = AL(r, 'HORIZONTAL', { p: [3, 7], r: 6, st: LN }); await T(kk, k, { s: 11, c: MU, f: MONO });
}
const pf = AL(pal, 'HORIZONTAL', { p: [12, 20], g: 18, ai: 'CENTER', fill: true, bg: '#0E0E10', st: LN, sides: [1, 0, 0, 0] });
await T(pf, '↑↓ navigate', { s: 12, c: DIM, f: MONO }); await T(pf, '↵ open', { s: 12, c: DIM, f: MONO }); await T(pf, 'e edit', { s: 12, c: DIM, f: MONO }); const g1 = AL(pf, 'HORIZONTAL', { grow: true });
icon(pf, 'shield-check', 14, OK); await T(pf, 'Nothing is sent without you', { s: 12, c: OK });
// bento
const sec = AL(P, 'VERTICAL', { n: 'Features', p: [120, 48, 48, 48], g: 40 }); sec.layoutSizingHorizontal = 'FILL';
await T(sec, 'Fast for you. Honest to recruiters.', { s: 48, w: 600, ls: -4, c: TX, width: 900 });
const grid = AL(sec, 'HORIZONTAL', { g: 16, fill: true });
const cell = async (title, desc) => { const c = AL(grid, 'VERTICAL', { p: 28, g: 10, r: 16, bg: S1, st: LN, grow: true, h: 360 }); await T(c, title, { s: 20, w: 600, c: TX, ls: -2 }); await T(c, desc, { s: 15, c: MU, lh: 150, fill: true }); const sp2 = AL(c, 'VERTICAL', { grow: true }); sp2.layoutGrow = 1; return c; };
const c1 = await cell('Every line checked', 'Each tailored line links to a fact you confirmed. No fact, no line.');
for (const [ok, t] of [[1, 'Built SQL dashboards…  F2'], [1, 'Ran 4 A/B tests…  F4'], [0, 'Led a team of 6 — removed']]) { const r = AL(c1, 'HORIZONTAL', { p: [10, 12], g: 10, r: 8, bg: ok ? '#0F1F18' : '#2A1214', ai: 'CENTER', fill: true }); icon(r, ok ? 'check' : 'x', 14, ok ? OK : ERR); await T(r, t, { s: 13, c: ok ? TX : ERR, f: ok ? FAM : FAM, strike: !ok }); }
const c2 = await cell('Shortcuts for everything', 'Power through 20 applications in two minutes. Or tap on your phone.');
const kb = AL(c2, 'HORIZONTAL', { g: 8, wrap: true, fill: true }); kb.counterAxisSpacing = 8;
for (const k of ['J', 'K', '↵', 'E', 'A', 'Ctrl K', '/', '?']) { const kk = AL(kb, 'HORIZONTAL', { w: 52, h: 52, r: 10, bg: S2, st: LN, jc: 'CENTER', ai: 'CENTER' }); await T(kk, k, { s: 16, w: 500, c: TX, f: MONO }); }
const c3 = await cell('Receipts, not vibes', 'Proof of what went where, when, and which file was sent.');
const rc = AL(c3, 'VERTICAL', { p: 14, g: 8, r: 10, bg: '#0E0E10', st: LN, fill: true });
for (const [k, v] of [['id', 'AS-24817'], ['to', 'Swiggy · careers@'], ['sent', '10 Oct, 09:42'], ['check', '14/14 lines backed']]) { const r = AL(rc, 'HORIZONTAL', { g: 12, fill: true }); await T(r, k, { s: 12, c: DIM, f: MONO, width: 52 }); await T(r, v, { s: 12, c: k === 'check' ? OK : TX, f: MONO }); }
// CTA
const fin = AL(P, 'VERTICAL', { n: 'CTA', p: [104, 48, 112, 48], g: 24, ai: 'CENTER' }); fin.layoutSizingHorizontal = 'FILL';
await T(fin, 'Press Enter to start.', { s: 72, w: 600, ls: -5, c: TX, align: 'CENTER', width: 900 });
await T(fin, '10 free applications · no card · ₹ pricing with UPI', { s: 14, c: DIM, f: MONO, align: 'CENTER', width: 600 });
inst(btnB, fin, {});
}

COMPS.x = OUT.pages.length ? (await figma.getNodeByIdAsync(OUT.pages[0])).x : 0; COMPS.y = -700;
const shots = [];
for (const id of OUT.pages) { const n = await figma.getNodeByIdAsync(id); shots.push({ id, name: n.name, w: n.width, h: Math.round(n.height), texts: n.findAllWithCriteria({types:['TEXT']}).length, inst: n.findAllWithCriteria({types:['INSTANCE']}).length }); }
for (const id of OUT.pages) { const n = await figma.getNodeByIdAsync(id); await n.screenshot({ scale: 0.35 }); }
return { pages: shots, compsId: COMPS.id, comps: COMPS.children.map(c => c.id + ' ' + c.name), fonts: [...usedFonts] };
