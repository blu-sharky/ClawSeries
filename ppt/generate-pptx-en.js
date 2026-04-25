const pptxgen = require('pptxgenjs');

const pptx = new pptxgen();
pptx.defineLayout({ name: 'WIDE', width: 13.333, height: 7.5 });
pptx.margin = 0;
pptx.slideWidth = 13.333;
pptx.slideHeight = 7.5;
pptx.version = '1.0.0';
pptx.subject = 'ClawSeries hackathon pitch (EN)';
pptx.company = 'ClawSeries';
pptx.author = 'ClawSeries';
pptx.lang = 'zh-CN';
const FONT_LATIN = 'Inter';
const FONT_CJK = 'PingFang SC';
const CJK_RE = /[\u3400-\u9FFF\uF900-\uFAFF]/;

pptx.theme = { headFontFace: FONT_LATIN, bodyFontFace: FONT_CJK, lang: 'zh-CN' };
pptx.layout = 'WIDE';

const ICON_PATHS = {
  warning: 'ppt/icons/warning-white.png',
  public: 'ppt/icons/public-white.png',
  travel_explore: 'ppt/icons/travel_explore-white.png',
  close: 'ppt/icons/close-white.png',
  check: 'ppt/icons/check-white.png',
  bolt: 'ppt/icons/bolt-white.png',
  movie: 'ppt/icons/movie-white.png',
  translate: 'ppt/icons/translate-white.png',
  settings: 'ppt/icons/settings-white.png',
};

const C = {
  bg: '1F2228',
  bg2: '191C22',
  fg: 'FFFFFF',
  muted: 'B9BBC3',
  faint: '7C7F8B',
  border: '4A4D56',
  surface: '2A2D34',
  surface2: '30343D',
  accent: '6366F1',
  lilac: 'A78BFA',
  sky: '60A5FA',
  cyan: '22D3EE',
  teal: '2DD4BF',
  emerald: '34D399',
  amber: 'FBBF24',
  rose: 'FB7185'
};

const W = 13.333;
const H = 7.5;

function addBg(slide, num) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: H, fill: { color: C.bg }, line: { color: C.bg, transparency: 100 } });
  for (let x = 0; x <= W; x += 0.64) {
    slide.addShape(pptx.ShapeType.line, { x, y: 0, w: 0, h: H, line: { color: 'FFFFFF', transparency: 94, width: 0.35 } });
  }
  for (let y = 0; y <= H; y += 0.64) {
    slide.addShape(pptx.ShapeType.line, { x: 0, y, w: W, h: 0, line: { color: 'FFFFFF', transparency: 94, width: 0.35 } });
  }
  slide.addShape(pptx.ShapeType.rect, { x: 10.95, y: -0.03, w: 2.38, h: 0.50, fill: { color: C.accent, transparency: 68 }, line: { color: C.accent, transparency: 100 } });
  slide.addShape(pptx.ShapeType.rect, { x: -0.12, y: 7.03, w: 1.62, h: 0.045, fill: { color: C.accent }, line: { color: C.accent, transparency: 100 } });
  slide.addShape(pptx.ShapeType.arc, { x: -0.72, y: 5.48, w: 2.45, h: 2.45, line: { color: C.cyan, transparency: 100 }, fill: { color: C.cyan, transparency: 92 } });
  slide.addText(num, { x: 11.72, y: 7.02, w: 0.95, h: 0.18, margin: 0, fontFace: 'Inter', fontSize: 7.5, color: C.faint, align: 'right' });
}

function resolveFont(s, opts = {}) {
  if (opts.fontFace) return opts.fontFace;
  return CJK_RE.test(String(s)) ? FONT_CJK : FONT_LATIN;
}

function text(slide, s, x, y, w, h, opts = {}) {
  slide.addText(s, {
    x, y, w, h,
    margin: opts.margin ?? 0,
    fit: 'shrink',
    fontFace: resolveFont(s, opts),
    fontSize: opts.size || 18,
    color: opts.color || C.fg,
    bold: opts.bold || false,
    valign: opts.valign || 'top',
    align: opts.align || 'left',
    charSpacing: opts.charSpacing || 0,
    breakLine: opts.breakLine,
    paraSpaceAfterPt: opts.paraSpaceAfterPt || 0,
  });
}

function kicker(slide, s, x, y, w = 8) {
  text(slide, s, x, y, w, 0.22, { size: 8.5, color: C.muted, charSpacing: 2 });
}

function title(slide, s, x, y, w, h = 1.25) {
  text(slide, s, x, y, w, h, { size: 32, color: C.fg });
}

function sectionHead(slide, idx, kickerText, titleText, subtitle) {
  text(slide, idx, 0.62, 0.48, 0.55, 0.35, { size: 16, color: C.faint });
  kicker(slide, kickerText, 1.32, 0.48, 8.6);
  title(slide, titleText, 1.32, 0.86, 10.8, 0.92);
  text(slide, subtitle, 1.32, 1.88, 9.8, 0.33, { size: 12.5, color: C.muted });
}


function iconBadge(slide, x, y, accent, icon = '', tag = '') {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w: 0.96, h: 0.29, rectRadius: 0.05, fill: { color: accent, transparency: 70 }, line: { color: accent, transparency: 18, width: 0.7 } });
  slide.addShape(pptx.ShapeType.roundRect, { x: x + 0.04, y: y + 0.035, w: 0.22, h: 0.22, rectRadius: 0.04, fill: { color: accent, transparency: 10 }, line: { color: 'FFFFFF', transparency: 72, width: 0.35 } });
  if (icon && ICON_PATHS[icon]) {
    slide.addImage({ path: ICON_PATHS[icon], x: x + 0.072, y: y + 0.066, w: 0.15, h: 0.15 });
  }
  if (tag) text(slide, tag, x + 0.31, y + 0.082, 0.58, 0.12, { fontFace: FONT_LATIN, size: 6.8, color: C.fg, align: 'center', charSpacing: 0.5 });
}


function card(slide, x, y, w, h, heading, body, accent = C.cyan, tag = '', icon = '') {
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: C.surface, transparency: 4 }, line: { color: C.border, width: 0.75 }, shadow: { type: 'outer', color: '000000', blur: 1.2, offset: 1, angle: 45, opacity: 0.10 } });
  slide.addShape(pptx.ShapeType.rect, { x, y, w: 0.045, h, fill: { color: accent, transparency: 0 }, line: { color: accent, transparency: 100 } });
  if (tag || icon) iconBadge(slide, x + 0.18, y + 0.16, accent, icon, tag);
  const headY = tag || icon ? y + 0.62 : y + 0.32;
  text(slide, heading, x + 0.22, headY, w - 0.44, 0.34, { size: 15.5, color: C.fg });
  text(slide, body, x + 0.22, headY + 0.46, w - 0.44, h - ((tag || icon) ? 1.14 : 0.85), { size: 10.2, color: C.muted });
}

function statCard(slide, x, y, w, h, value, label, accent, opts = {}) {
  slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: C.surface, transparency: 3 }, line: { color: C.border, width: 0.75 } });
  slide.addShape(pptx.ShapeType.rect, { x: x + 0.18, y: y + 0.16, w: 0.48, h: 0.035, fill: { color: accent }, line: { color: accent, transparency: 100 } });
  if (h <= 1.05) {
    text(slide, label, x + 0.18, y + 0.20, w - 0.36, 0.22, { size: opts.labelSize || 7.8, color: C.muted });
    text(slide, value, x + 0.18, y + 0.52, w - 0.36, h - 0.62, { size: opts.valueSize || 27, color: accent });
  } else {
    text(slide, value, x + 0.20, y + 0.38, w - 0.4, 0.72, { size: opts.valueSize || 32, color: accent });
    text(slide, label, x + 0.22, y + 1.30, w - 0.44, h - 1.48, { size: opts.labelSize || 10.2, color: C.muted });
  }
}

function pill(slide, s, x, y, w, accent) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h: 0.32, rectRadius: 0.06, fill: { color: accent, transparency: 88 }, line: { color: accent, transparency: 40, width: 0.5 } });
  text(slide, s, x, y + 0.095, w, 0.12, { size: 7.2, color: accent, align: 'center', charSpacing: 0.7 });
}

function note(slide, s) {
  slide.addNotes(s);
}

async function main() {

{
  const s = pptx.addSlide(); addBg(s, '01 / 08');
  kicker(s, 'HACKATHON / GLOBAL SHORT DRAMA INFRASTRUCTURE', 2.72, 0.92, 8.2);
  text(s, 'CLAW\nSERIES', 3.83, 1.27, 5.7, 2.18, { size: 64, color: C.fg, align: 'center' });
  text(s, 'Going global is not translation — it\'s industrial delivery', 2.85, 3.70, 7.65, 0.42, { size: 21, color: C.fg, align: 'center' });
  text(s, 'Turn China\'s short-drama content advantage into global distribution capability with a zero-human AI production factory.', 2.60, 4.20, 8.12, 0.34, { size: 13.3, color: C.muted, align: 'center' });
  statCard(s, 2.65, 5.22, 2.7, 0.98, '94.93%', 'Share of global short-drama app revenue', C.lilac);
  statCard(s, 5.58, 5.22, 2.7, 0.98, '$23.29B', '2025E overseas IAP revenue', C.sky);
  statCard(s, 8.51, 5.22, 2.7, 0.98, '100%', 'Core localization goal: full auto redubbing', C.cyan);
  note(s, 'Opening note: ClawSeries is not another AI short-drama tool. It is an automated production and localization factory built for global distribution.');
}

{
  const s = pptx.addSlide(); addBg(s, '02 / 08');
  sectionHead(s, '01', 'WHY NOW', 'Short-drama expansion is no longer a pilot — it is the main battlefield', 'China\'s short-drama supply capability is colliding with a structural shift in global mobile video consumption.');
  statCard(s, 0.78, 2.62, 2.86, 2.20, 'RMB 37.39B', 'China\'s 2023 short-drama market reached 37.39B RMB, already more than half of the domestic box office total.', C.lilac, { valueSize: 29 });
  statCard(s, 3.84, 2.62, 2.86, 2.20, '370M', 'Global downloads hit 370M in 2025 Q1, up 6.2x year over year, with traffic still accelerating.', C.sky, { valueSize: 29 });
  statCard(s, 6.90, 2.62, 2.86, 2.20, '$100B', 'By 2029, the global short-drama market could reach $100B, far beyond any single domestic market.', C.cyan, { valueSize: 31 });
  statCard(s, 9.96, 2.62, 2.86, 2.20, '+133%', '2025E cumulative global IAP revenue is up 133% year over year, proving the paid model at scale.', C.amber, { valueSize: 31 });
  s.addShape(pptx.ShapeType.rect, { x: 1.15, y: 5.55, w: 11.0, h: 0.62, fill: { color: C.accent, transparency: 84 }, line: { color: C.border, width: 0.75 } });
  text(s, 'Bottom line: the next-stage competition is not who can produce, but who can deliver globally at scale.', 1.35, 5.73, 10.6, 0.26, { size: 14, color: C.fg, align: 'center' });
  note(s, 'Short-drama globalization has entered the main battlefield. Chinese teams have proven their content and operating advantage; the next step is scalable delivery.');
}

{
  const s = pptx.addSlide(); addBg(s, '03 / 08');
  sectionHead(s, '02', 'STRUCTURAL PAIN', 'Platform fees and traffic spend eat the margin — producers have only one path left', 'When the ROI survival line is only 1.1–1.2, global expansion cannot scale unless production costs fall.');
  card(s, 0.95, 2.55, 5.10, 3.60, 'Structural margin compression', 'Platform take can reach 94%\nTraffic acquisition often consumes 80%+ of gross revenue\nMost projects survive only at ROI 1.1–1.2\n80% of projects face profit pressure', C.rose, 'RISK', 'warning');
  s.addShape(pptx.ShapeType.rect, { x: 6.55, y: 2.55, w: 5.75, h: 3.60, fill: { color: C.surface, transparency: 3 }, line: { color: C.border, width: 0.75 } });
  text(s, 'What happens to every 100 of revenue', 6.85, 2.86, 4.5, 0.32, { size: 17, color: C.fg });
  const rows = [['Platform / channel', 94, '94'], ['Producer remainder', 6, '6'], ['Traffic black hole', 80, '80%+']];
  rows.forEach((r, i) => {
    const y = 3.45 + i * 0.62;
    text(s, r[0], 6.85, y, 1.3, 0.2, { size: 8.5, color: C.muted });
    s.addShape(pptx.ShapeType.rect, { x: 8.35, y: y + 0.05, w: 2.65, h: 0.09, fill: { color: 'FFFFFF', transparency: 90 }, line: { color: 'FFFFFF', transparency: 100 } });
    s.addShape(pptx.ShapeType.rect, { x: 8.35, y: y + 0.05, w: 2.65 * r[1] / 100, h: 0.09, fill: { color: C.rose }, line: { color: C.rose, transparency: 100 } });
    text(s, r[2], 11.2, y, 0.55, 0.18, { size: 9, color: C.fg });
  });
  text(s, 'AI is not a nice-to-have — it is the only way to defend the last 6% of margin.', 6.85, 5.48, 5.0, 0.34, { size: 13.5, color: C.muted, align: 'center' });
  note(s, 'The margin structure means AI must transform cost, not merely assist creativity.');
}

{
  const s = pptx.addSlide(); addBg(s, '04 / 08');
  sectionHead(s, '03', 'GLOBAL MAP', 'Different regions, different monetization logics — one shared bottleneck: localization', 'North America and Europe bring high ARPU; Southeast Asia and Latin America bring traffic and IAA growth.');
  card(s, 0.85, 2.56, 5.65, 3.25, 'North America / Europe', 'Urban women aged 30–60 dominate, with strong appetite for CEO romance, werewolf, and revenge arcs.\n\nMonthly ARPU can reach $80\nNorth America is projected to exceed $2B in annual revenue by end-2024', C.sky, 'ARPU', 'public');
  card(s, 6.83, 2.56, 5.65, 3.25, 'Southeast Asia / Latin America', 'Traffic-heavy markets where free viewing plus ads better fits local purchasing power.\n\n+60% quarterly download growth\nIAA share has jumped to 24.7%', C.teal, 'IAA', 'travel_explore');
  ['EN', 'JP', 'ES', 'KR', 'FR', 'DE', 'PT', 'HI', 'CN', 'TH'].forEach((lang, i) => pill(s, lang, 2.28 + i * 0.86, 6.24, 0.54, [C.lilac, C.sky, C.cyan, C.teal, C.amber][i % 5]));
  note(s, 'The regional logic differs, but the shared bottleneck is localization: voice, tone, cultural context, and marketing assets.');
}

{
  const s = pptx.addSlide(); addBg(s, '05 / 08');
  sectionHead(s, '04', 'BOTTLENECK', '"Translated series" dominate 9:1, but mechanical dubbing is killing conversion', 'The real cost sink in globalization is full redubbing plus partial localized reshoots.');
  card(s, 0.95, 2.64, 4.95, 2.95, 'Traditional translated series', 'Subtitle translation, overseas voice actors, manual review, and repeated rework. Crying turns flat; rage becomes plain reading.\n\nNorth America cost per series: $250K–$300K', C.rose, 'OLD', 'close');
  text(s, '→', 6.18, 3.82, 0.7, 0.55, { size: 34, color: C.accent, align: 'center' });
  card(s, 7.05, 2.64, 4.95, 2.95, 'AI-native localization', 'Voice cloning preserves the character voice, emotion transfer keeps performance consistent, and multilingual launch assets are generated automatically.\n\nGoal: 70%+ cost reduction, cycle compressed from weeks to days', C.emerald, 'AI', 'bolt');
  s.addShape(pptx.ShapeType.rect, { x: 2.0, y: 6.02, w: 9.35, h: 0.55, fill: { color: C.accent, transparency: 84 }, line: { color: C.border, width: 0.75 } });
  text(s, 'Going global is not language replacement — it is minimizing cultural discount.', 2.2, 6.19, 8.95, 0.22, { size: 14, color: C.fg, align: 'center' });
  note(s, 'Most exported dramas are translated versions, but robotic voices damage conversion. The key is automating voiceprint, emotion, lip-sync, and launch assets together.');
}

{
  const s = pptx.addSlide(); addBg(s, '06 / 08');
  sectionHead(s, '05', 'SOLUTION', 'ClawSeries: a zero-human AI production factory built for global expansion', 'From script and storyboard to assets, video, and localization, everything runs through one automated pipeline.');
  const steps = [['Script','HOOK'], ['Shots','SHOT'], ['Assets','ASSET'], ['Video','VECTOR'], ['Dubbing','VOX'], ['Launch','GLOBAL']];
  steps.forEach((st, i) => {
    const x = 0.75 + i * 2.04;
    s.addShape(pptx.ShapeType.rect, { x, y: 2.74, w: 1.75, h: 1.48, fill: { color: C.surface, transparency: 3 }, line: { color: C.border, width: 0.75 } });
    s.addShape(pptx.ShapeType.rect, { x, y: 2.74, w: 1.75, h: 0.055, fill: { color: [C.lilac, C.sky, C.cyan, C.teal, C.amber, C.rose][i] }, line: { color: [C.lilac, C.sky, C.cyan, C.teal, C.amber, C.rose][i], transparency: 100 } });
    text(s, st[0], x + 0.15, 3.00, 1.45, 0.28, { size: 15, color: C.fg, align: 'center' });
    text(s, st[1], x + 0.15, 3.47, 1.45, 0.2, { size: 8.5, color: C.muted, align: 'center', charSpacing: 1.2 });
  });
  statCard(s, 1.10, 5.02, 2.55, 0.88, '10x', 'Creative throughput', C.cyan, { valueSize: 25 });
  statCard(s, 3.92, 5.02, 2.55, 0.88, '-90%', 'Promo asset cost', C.amber, { valueSize: 25 });
  statCard(s, 6.74, 5.02, 2.55, 0.88, '15 days → 3 days', 'Production cycle', C.teal, { valueSize: 24 });
  statCard(s, 9.56, 5.02, 2.55, 0.88, '50 eps', 'Parallel render target', C.lilac, { valueSize: 25 });
  note(s, 'ClawSeries is a full pipeline, not a point tool. Only a pipeline can change the cost structure.');
}

{
  const s = pptx.addSlide(); addBg(s, '07 / 08');
  sectionHead(s, '06', 'DEMO PROOF', 'Recent progress: turning the global-delivery chain into something observable and debuggable', 'The hackathon demo is not about generating one video — it is about monitoring, reproducing, and fixing the pipeline continuously.');
  card(s, 0.85, 2.50, 5.72, 1.45, 'Video Tab shot-level monitoring', 'Each shot gets its own card, with the first frame, prompt, logs, and status visible in one place.', C.cyan, 'UI', 'settings');
  card(s, 6.82, 2.50, 5.72, 1.45, 'VectorEngine automated video', 'After the first frame is uploaded, it is passed into the vector matrix, supporting both automated generation and manual per-shot reruns.', C.sky, 'VID', 'movie');
  card(s, 0.85, 4.26, 5.72, 1.45, 'VoxCPM reference-audio retention', 'Each dubbing segment keeps the original reference slice beside it for voice and emotion comparison.', C.amber, 'DUB', 'translate');
  card(s, 6.82, 4.26, 5.72, 1.45, 'Multilingual presentation and global narrative', 'The site and the deck now consistently emphasize global distribution rather than a domestic-only production tool.', C.teal, 'I18N', 'public');
  note(s, 'These updates prove we are building an operable, debuggable production system — not a one-off demo.');
}

{
  const s = pptx.addSlide(); addBg(s, '08 / 08');
  kicker(s, 'CLOSING THESIS', 1.0, 0.95, 9.0);
  text(s, 'The next stage of global short drama:\ntechnology is the foundation', 1.0, 1.42, 9.6, 1.55, { size: 42, color: C.fg });
  text(s, 'Whoever operationalizes localization first will turn China\'s IP content advantage into global growth advantage.', 1.0, 3.18, 9.6, 0.42, { size: 16, color: C.muted });
  card(s, 1.0, 4.25, 3.45, 1.45, '01 Capture global upside', '2025E overseas IAP revenue reaches $23.29B, while downloads are still expanding fast.', C.sky, '01', 'public');
  card(s, 4.75, 4.25, 3.45, 1.45, '02 Protect unit economics', 'Use automation to offset platform tax and the traffic-spend black hole.', C.amber, '02', 'warning');
  card(s, 8.5, 4.25, 3.45, 1.45, '03 Cross cultural discount', 'Use voiceprint, emotion transfer, and multilingual assets to complete deep localization.', C.teal, '03', 'translate');
  s.addShape(pptx.ShapeType.rect, { x: 1.0, y: 6.35, w: 10.95, h: 0.43, fill: { color: C.accent, transparency: 82 }, line: { color: C.border, width: 0.75 } });
  text(s, 'ClawSeries = Global Short Drama Autopilot', 1.2, 6.48, 10.55, 0.18, { size: 10.5, color: C.fg, align: 'center' });
  note(s, 'Closing note: a localization pipeline is the foundation of global short drama. ClawSeries aims to become the Global Short Drama Autopilot.');
}

  await pptx.writeFile({ fileName: 'ppt/ClawSeries-en.pptx' });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
