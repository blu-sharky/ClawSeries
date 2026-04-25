const pptxgen = require('pptxgenjs');

const pptx = new pptxgen();
pptx.defineLayout({ name: 'WIDE', width: 13.333, height: 7.5 });
pptx.margin = 0;
pptx.slideWidth = 13.333;
pptx.slideHeight = 7.5;
pptx.version = '1.0.0';
pptx.subject = 'ClawSeries hackathon pitch';
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
  text(s, '出海不是翻译，是工业化交付', 2.85, 3.70, 7.65, 0.42, { size: 21, color: C.fg, align: 'center' });
  text(s, '用零人 AI 制片工厂，把中国短剧的内容优势转化为全球化发行能力。', 2.60, 4.20, 8.12, 0.34, { size: 13.3, color: C.muted, align: 'center' });
  statCard(s, 2.65, 5.22, 2.7, 0.98, '94.93%', '全球短剧应用收入占比', C.lilac);
  statCard(s, 5.58, 5.22, 2.7, 0.98, '$23.29B', '2025E 海外内购收入', C.sky);
  statCard(s, 8.51, 5.22, 2.7, 0.98, '100%', '核心本地化目标：重配音自动化', C.cyan);
  note(s, '开场强调：ClawSeries 不是又一个 AI 短剧工具，而是面向出海的自动化制片与本地化工厂。');
}

{
  const s = pptx.addSlide(); addBg(s, '02 / 08');
  sectionHead(s, '01', 'WHY NOW', '短剧出海已经不是试水，而是主战场', '中国短剧的供给能力，正在遇到全球移动影视消费的结构性迁移。');
  statCard(s, 0.78, 2.62, 2.86, 2.20, '373.9亿', '2023 中国短剧市场规模，已经超过国内电影票房总额 50%。', C.lilac, { valueSize: 29 });
  statCard(s, 3.84, 2.62, 2.86, 2.20, '3.7亿次', '2025 Q1 全球下载量，同比增长 6.2 倍，流量仍在扩张。', C.sky, { valueSize: 29 });
  statCard(s, 6.90, 2.62, 2.86, 2.20, '$100B', '2029 全球短剧长期潜力预测，出海空间远大于单一国内市场。', C.cyan, { valueSize: 31 });
  statCard(s, 9.96, 2.62, 2.86, 2.20, '+133%', '2025E 全球累计内购收入同比增长，付费模型已经被验证。', C.amber, { valueSize: 31 });
  s.addShape(pptx.ShapeType.rect, { x: 1.15, y: 5.55, w: 11.0, h: 0.62, fill: { color: C.accent, transparency: 84 }, line: { color: C.border, width: 0.75 } });
  text(s, '结论：下半场的核心竞争，不是“会不会拍”，而是“能不能全球化规模交付”。', 1.35, 5.73, 10.6, 0.26, { size: 14, color: C.fg, align: 'center' });
  note(s, '短剧出海进入主战场。中国公司已经证明内容和运营优势，下一步是规模交付。');
}

{
  const s = pptx.addSlide(); addBg(s, '03 / 08');
  sectionHead(s, '02', 'STRUCTURAL PAIN', '利润被平台和投流吞噬，制作方只剩一条路', '当 ROI 生存线只有 1.1–1.2，生产成本不降，出海就无法规模化。');
  card(s, 0.95, 2.55, 5.10, 3.60, '结构性利润压缩', '平台抽成比例可高达 94%\n投流成本普遍占总票房 80%+\n多数项目生死线：ROI 1.1–1.2\n80% 项目面临亏损压力', C.rose, 'RISK', 'warning');
  s.addShape(pptx.ShapeType.rect, { x: 6.55, y: 2.55, w: 5.75, h: 3.60, fill: { color: C.surface, transparency: 3 }, line: { color: C.border, width: 0.75 } });
  text(s, '票房 100 的分配压力', 6.85, 2.86, 4.5, 0.32, { size: 17, color: C.fg });
  const rows = [['平台 / 渠道', 94, '94'], ['制作方剩余', 6, '6'], ['投流黑洞', 80, '80%+']];
  rows.forEach((r, i) => {
    const y = 3.45 + i * 0.62;
    text(s, r[0], 6.85, y, 1.3, 0.2, { size: 8.5, color: C.muted });
    s.addShape(pptx.ShapeType.rect, { x: 8.35, y: y + 0.05, w: 2.65, h: 0.09, fill: { color: 'FFFFFF', transparency: 90 }, line: { color: 'FFFFFF', transparency: 100 } });
    s.addShape(pptx.ShapeType.rect, { x: 8.35, y: y + 0.05, w: 2.65 * r[1] / 100, h: 0.09, fill: { color: C.rose }, line: { color: C.rose, transparency: 100 } });
    text(s, r[2], 11.2, y, 0.55, 0.18, { size: 9, color: C.fg });
  });
  text(s, 'AI 不是锦上添花，而是“剩下 6%”里的利润保卫战。', 6.85, 5.48, 5.0, 0.34, { size: 13.5, color: C.muted, align: 'center' });
  note(s, '利润结构决定了 AI 必须做成本改造，而不是单纯做创意辅助。');
}

{
  const s = pptx.addSlide(); addBg(s, '04 / 08');
  sectionHead(s, '03', 'GLOBAL MAP', '不同区域，不同变现逻辑；共同痛点是本地化', '北美/欧洲贡献高 ARPU，东南亚/拉美贡献流量与 IAA 增长。');
  card(s, 0.85, 2.56, 5.65, 3.25, '北美 / 欧洲', '30–60 岁城市女性为主，偏好霸总、狼人、复仇等强情绪母题。\n\n$80 月度 ARPU 可达\n$2B 2024 年底北美年收入预估', C.sky, 'ARPU', 'public');
  card(s, 6.83, 2.56, 5.65, 3.25, '东南亚 / 拉美', '流量高地，免费看剧 + 广告解锁正在适配当地消费能力。\n\n+60% 下载量单季度涨幅\n24.7% IAA 下载占比跃升', C.teal, 'IAA', 'travel_explore');
  ['EN', 'JP', 'ES', 'KR', 'FR', 'DE', 'PT', 'HI', 'CN', 'TH'].forEach((lang, i) => pill(s, lang, 2.28 + i * 0.86, 6.24, 0.54, [C.lilac, C.sky, C.cyan, C.teal, C.amber][i % 5]));
  note(s, '两个区域逻辑不同，但共同瓶颈都是本地化：声音、语气、文化语境和投放素材。');
}

{
  const s = pptx.addSlide(); addBg(s, '05 / 08');
  sectionHead(s, '04', 'BOTTLENECK', '“翻译剧”占 9:1，但机械生硬正在吃掉转化率', '出海成本的真正黑洞，是 100% 重配音与部分本地化重拍。');
  card(s, 0.95, 2.64, 4.95, 2.95, '传统翻译剧', '字幕翻译、海外声优、人工审听、反复返工。哭腔变成平淡念白，怒吼变成朗读。\n\n单剧北美成本：$250K–$300K', C.rose, 'OLD', 'close');
  text(s, '→', 6.18, 3.82, 0.7, 0.55, { size: 34, color: C.accent, align: 'center' });
  card(s, 7.05, 2.64, 4.95, 2.95, 'AI 深度本地化', '声纹克隆保留角色声线，情绪一致性转换，自动生成多语言投放物料。\n\n目标：成本下降 70%+，周期从周到天', C.emerald, 'AI', 'bolt');
  s.addShape(pptx.ShapeType.rect, { x: 2.0, y: 6.02, w: 9.35, h: 0.55, fill: { color: C.accent, transparency: 84 }, line: { color: C.border, width: 0.75 } });
  text(s, '出海不是语言替换，而是把文化折扣压到最低。', 2.2, 6.19, 8.95, 0.22, { size: 14, color: C.fg, align: 'center' });
  note(s, '翻译剧占多数，但机械声音会伤害转化率。关键是把声纹、情绪、口型和投放素材都自动化。');
}

{
  const s = pptx.addSlide(); addBg(s, '06 / 08');
  sectionHead(s, '05', 'SOLUTION', 'ClawSeries：面向出海的零人 AI 制片工厂', '从剧本、分镜、资产、视频到译制，统一在一个自动化流水线里完成。');
  const steps = [['剧本','HOOK'], ['分镜','SHOT'], ['资产','ASSET'], ['视频','VECTOR'], ['译制','VOX'], ['分发','GLOBAL']];
  steps.forEach((st, i) => {
    const x = 0.75 + i * 2.04;
    s.addShape(pptx.ShapeType.rect, { x, y: 2.74, w: 1.75, h: 1.48, fill: { color: C.surface, transparency: 3 }, line: { color: C.border, width: 0.75 } });
    s.addShape(pptx.ShapeType.rect, { x, y: 2.74, w: 1.75, h: 0.055, fill: { color: [C.lilac, C.sky, C.cyan, C.teal, C.amber, C.rose][i] }, line: { color: [C.lilac, C.sky, C.cyan, C.teal, C.amber, C.rose][i], transparency: 100 } });
    text(s, st[0], x + 0.15, 3.00, 1.45, 0.28, { size: 15, color: C.fg, align: 'center' });
    text(s, st[1], x + 0.15, 3.47, 1.45, 0.2, { size: 8.5, color: C.muted, align: 'center', charSpacing: 1.2 });
  });
  statCard(s, 1.10, 5.02, 2.55, 0.88, '10x', '创作提速', C.cyan, { valueSize: 25 });
  statCard(s, 3.92, 5.02, 2.55, 0.88, '-90%', '宣传物料成本', C.amber, { valueSize: 25 });
  statCard(s, 6.74, 5.02, 2.55, 0.88, '15→3天', '制作周期压缩', C.teal, { valueSize: 24 });
  statCard(s, 9.56, 5.02, 2.55, 0.88, '50集', '并行渲染目标', C.lilac, { valueSize: 25 });
  note(s, 'ClawSeries 是完整流水线，不是单点工具。流水线才能改变成本结构。');
}

{
  const s = pptx.addSlide(); addBg(s, '07 / 08');
  sectionHead(s, '06', 'DEMO PROOF', '最近的系统进展：把“出海链路”做成可观察、可调试', '黑客松展示重点：不是只生成一个视频，而是能持续监控、复现和修正流水线。');
  card(s, 0.85, 2.50, 5.72, 1.45, 'Video Tab 镜头级监控', '每个镜头一张近方形卡片，首帧、提示词、日志和状态统一可见。', C.cyan, 'UI', 'settings');
  card(s, 6.82, 2.50, 5.72, 1.45, 'VectorEngine 自动视频', '首帧上传图床后传入向量矩阵，支持自动生成和手动逐镜头重跑。', C.sky, 'VID', 'movie');
  card(s, 0.85, 4.26, 5.72, 1.45, 'VoxCPM 参考音频保留', '每段译制的原声参考切片保存在旁边，方便对比音色与情绪。', C.amber, 'DUB', 'translate');
  card(s, 6.82, 4.26, 5.72, 1.45, '多语言展示与出海叙事', '官网与 deck 统一强调全球发行，而不是单纯国内生产工具。', C.teal, 'I18N', 'public');
  note(s, '这些进展证明我们在做可运营、可调试的生产系统，而不是一次性 demo。');
}

{
  const s = pptx.addSlide(); addBg(s, '08 / 08');
  kicker(s, 'CLOSING THESIS', 1.0, 0.95, 9.0);
  text(s, '短剧出海的下半场：\n技术即基石', 1.0, 1.42, 9.6, 1.55, { size: 42, color: C.fg });
  text(s, '谁先把本地化做成流水线，谁就能把中国 IP 的内容优势变成全球增长优势。', 1.0, 3.18, 9.6, 0.42, { size: 16, color: C.muted });
  card(s, 1.0, 4.25, 3.45, 1.45, '01 抓住全球增量', '2025E 海外内购收入 $23.29B，下载仍在高速扩散。', C.sky, '01', 'public');
  card(s, 4.75, 4.25, 3.45, 1.45, '02 守住利润底线', '用自动化抵消平台税与投流黑洞。', C.amber, '02', 'warning');
  card(s, 8.5, 4.25, 3.45, 1.45, '03 跨越文化折扣', '用声纹、情绪和多语言物料完成深度本地化。', C.teal, '03', 'translate');
  s.addShape(pptx.ShapeType.rect, { x: 1.0, y: 6.35, w: 10.95, h: 0.43, fill: { color: C.accent, transparency: 82 }, line: { color: C.border, width: 0.75 } });
  text(s, 'ClawSeries = Global Short Drama Autopilot', 1.2, 6.48, 10.55, 0.18, { size: 10.5, color: C.fg, align: 'center' });
  note(s, '最后强调：本地化流水线是短剧出海的底座。ClawSeries 想成为 Global Short Drama Autopilot。');
}

  await pptx.writeFile({ fileName: 'ppt/ClawSeries.pptx' });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
