const pptxgen = require("pptxgenjs");

// ===== Design tokens (matching website/styles.css) =====
const BG      = "1F2228";
const FG      = "FFFFFF";
const DIM     = "B8BEC8";   // --text-secondary on dark
const DIMMER  = "808890";   // --text-tertiary on dark
const ACCENT  = "6366F1";   // --accent
const SURFACE = "282D35";   // card bg
const BORDER  = "3A3F48";   // card border

// Fonts — matching HTML deck (Inter + JetBrains Mono)
const SANS = "Inter";
const MONO = "JetBrains Mono";

// Factory functions — pptxgenjs mutates option objects
const mkShadow  = () => ({ type: "outer", color: "000000", blur: 6, offset: 2, angle: 135, opacity: 0.25 });
const mkCardFill = () => ({ color: SURFACE });
const mkCardLine = () => ({ color: BORDER, pt: 1 });

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "ClawSeries";
pres.title  = "ClawSeries — 路演 Deck";

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: BG };
  return s;
}

function slideNum(s, n) {
  s.addText(`0${n} / 08`, {
    x: 8.5, y: 0.25, w: 1.2, h: 0.25,
    fontSize: 10, fontFace: MONO, color: DIMMER, align: "right",
  });
}

function sectionHead(s, idx, title, subtitle, y) {
  y = y || 0.5;
  s.addText(idx, {
    x: 0.6, y, w: 0.6, h: 0.5,
    fontSize: 24, fontFace: MONO, color: DIMMER, margin: 0,
  });
  s.addText(title, {
    x: 1.3, y, w: 7, h: 0.5,
    fontSize: 28, fontFace: SANS, color: FG, bold: false, margin: 0,
  });
  if (subtitle) {
    s.addText(subtitle, {
      x: 1.3, y: y + 0.45, w: 7, h: 0.3,
      fontSize: 13, fontFace: SANS, color: DIM, margin: 0,
    });
  }
}

function card(s, x, y, w, h, icon, title, body) {
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill: mkCardFill(), line: mkCardLine(),
  });
  let ty = y + 0.12;
  if (icon) {
    s.addText(icon, { x: x + 0.15, y: ty, w: 0.5, h: 0.4, fontSize: 20, margin: 0 });
    ty += 0.38;
  }
  s.addText(title, {
    x: x + 0.15, y: ty, w: w - 0.3, h: 0.32,
    fontSize: 14, fontFace: SANS, color: FG, bold: false, margin: 0,
  });
  s.addText(body, {
    x: x + 0.15, y: ty + 0.32, w: w - 0.3, h: h - (ty - y) - 0.45,
    fontSize: 11, fontFace: SANS, color: DIM, valign: "top", margin: 0,
    lineSpacingMultiple: 1.3,
  });
}

// ============ 1. COVER ============
{
  const s = darkSlide();
  slideNum(s, 1);
  s.addText("ROADSHOW / ZERO-HUMAN AI STUDIO", {
    x: 0.5, y: 0.7, w: 9, h: 0.3,
    fontSize: 10, fontFace: MONO, color: DIMMER, align: "center",
    charSpacing: 2,
  });
  s.addText("CLAWSERIES", {
    x: 0.5, y: 1.2, w: 9, h: 1.1,
    fontSize: 60, fontFace: MONO, color: FG, align: "center",
    charSpacing: 8, bold: false,
  });
  s.addText("零人AI短剧公司", {
    x: 0.5, y: 2.25, w: 9, h: 0.45,
    fontSize: 20, fontFace: SANS, color: FG, align: "center",
  });
  s.addText("彻底打通 AI 短剧自动化生产的最后一公里", {
    x: 0.5, y: 2.7, w: 9, h: 0.35,
    fontSize: 12, fontFace: MONO, color: ACCENT, align: "center",
    charSpacing: 2,
  });
  // Metrics
  const ms = [
    ["自动化程度", "100% 无人类介入"],
    ["并发能力", "50集同步渲染"],
    ["效率提升", "1小时 = 数月工作"],
  ];
  ms.forEach(([label, val], i) => {
    const mx = 1.3 + i * 2.6;
    s.addShape(pres.shapes.RECTANGLE, {
      x: mx, y: 3.5, w: 2.3, h: 0.85,
      fill: mkCardFill(), line: mkCardLine(),
    });
    s.addText(label, {
      x: mx + 0.12, y: 3.55, w: 2.06, h: 0.25,
      fontSize: 9, fontFace: MONO, color: DIMMER, charSpacing: 1.5, margin: 0,
    });
    s.addText(val, {
      x: mx + 0.12, y: 3.82, w: 2.06, h: 0.35,
      fontSize: 13, fontFace: SANS, color: FG, margin: 0,
    });
  });
  s.addNotes("各位评委好。一句话介绍：零人 AI 短剧公司。100% 无人类介入、50 集同步渲染、1 小时完成数月工作。");
}

// ============ 2. 行业痛点 ============
{
  const s = darkSlide();
  slideNum(s, 2);
  sectionHead(s, "01", "2026年的制片悖论", "数万家 AI 短剧公司，没有一家真正实现全自动化");
  const cs = [
    ["⚡", "数万家「AI公司」的诞生", "「人工+AI」工作流本身就是完全可以被 AI 彻底取代的。人类只是搬运工。"],
    ["🎬", "成熟的模型，原始的流水线", "大模型数秒生成电影级镜头，但连成短剧仍是「人工作坊」模式。"],
    ["💀", "致命的「人类沟通成本」", "导演反复解释意图；制片肉眼筛片；剪辑师手工逐帧对齐。"],
    ["🔗", "人类 = 最慢的「路由器」", "审片疲劳和无休止的返工确认，吞噬利润和创意。"],
  ];
  cs.forEach(([icon, t, b], i) => {
    const cx = 0.5 + (i % 2) * 4.6;
    const cy = 1.45 + Math.floor(i / 2) * 1.75;
    card(s, cx, cy, 4.3, 1.55, icon, t, b);
  });
  s.addNotes("行业背景：模型已成熟，但人类是流水线上最慢的路由器。数万家公司本质是搬运工。");
}

// ============ 3. 使命 ============
{
  const s = darkSlide();
  slideNum(s, 3);
  sectionHead(s, "02", "我们的使命", "用毫秒级的 Agent 内部通信，取代漫长的人类沟通会议");
  // Mission box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 1.6, w: 7.6, h: 1.0,
    fill: { color: "252840" }, line: { color: "3D4070", pt: 1 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.2, y: 1.6, w: 7.6, h: 1.0,
    fill: { color: ACCENT, transparency: 92 },
  });
  s.addText([
    { text: "ClawSeries 不研发底层视频大模型，", options: { breakLine: true, bold: true } },
    { text: "我们做全新的「自动化制片工厂」。", options: { bold: true } },
  ], {
    x: 1.4, y: 1.65, w: 7.2, h: 0.9,
    fontSize: 18, fontFace: SANS, color: FG,
    align: "center", valign: "middle", lineSpacingMultiple: 1.5,
  });
  s.addText([
    { text: "将传统 AI 短剧公司中耗时耗力的五个核心岗位，", options: { breakLine: true } },
    { text: "完全替换为自主协作的智能体（Agents）。", options: { breakLine: true } },
    { text: "让「一句话生成百集短剧」从商业概念变成工业级交付。" },
  ], {
    x: 1.5, y: 2.85, w: 7, h: 1.0,
    fontSize: 14, fontFace: SANS, color: DIM,
    align: "center", lineSpacingMultiple: 1.5,
  });
  s.addNotes("我们不做模型，做工厂。五个人类岗位替换成五个 Agent，毫秒级通信，零损耗。");
}

// ============ 4. 五大 Agent ============
{
  const s = darkSlide();
  slideNum(s, 4);
  sectionHead(s, "03", "五大自主智能体架构", "Pentagram of Agents");
  const agents = [
    ["🎯 01", "项目总监", "全局状态管理与流程控制", "接收一句话指令，自动拆解数十集制片任务，实时监控进度。"],
    ["🎬 02", "总导演", "剧本与戏剧张力控制", "构建连贯世界观，自动设置每集悬念，确保剧情逻辑自洽。"],
    ["👁️ 03", "视觉总监", "视觉资产与一致性锚定", "永久锁定角色脸部、服装与场景资产，确保始终如一。"],
    ["💡 04", "提示词架构师", "跨模型语义翻译", "将文学分镜转化为引擎最优 Prompt 矩阵，避免画面崩坏。"],
    ["⚡ 05", "自动化剪辑师", "音画压制与情感封装", "删除多余片段，拼接分镜，添加 BGM 并对齐压制字幕。"],
  ];
  agents.forEach(([num, name, func, desc], i) => {
    const ay = 1.4 + i * 0.76;
    // Row bg
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: ay, w: 9, h: 0.66,
      fill: mkCardFill(), line: mkCardLine(),
    });
    s.addText(num, {
      x: 0.6, y: ay + 0.05, w: 0.8, h: 0.56,
      fontSize: 16, fontFace: MONO, color: ACCENT, valign: "middle", margin: 0,
    });
    s.addText(name, {
      x: 1.5, y: ay + 0.02, w: 1.8, h: 0.32,
      fontSize: 14, fontFace: SANS, color: FG, margin: 0,
    });
    s.addText(func, {
      x: 1.5, y: ay + 0.34, w: 2.5, h: 0.25,
      fontSize: 9, fontFace: MONO, color: DIMMER, charSpacing: 0.8, margin: 0,
    });
    s.addText(desc, {
      x: 4.2, y: ay + 0.05, w: 5.1, h: 0.56,
      fontSize: 11, fontFace: SANS, color: DIM, valign: "middle", margin: 0,
    });
  });
  s.addNotes("五个 Agent：项目总监、总导演、视觉总监、提示词架构师、自动化剪辑师。各司其职，毫秒级协作。");
}

// ============ 5. 技术哲学 ============
{
  const s = darkSlide();
  slideNum(s, 5);
  sectionHead(s, "04", "核心技术哲学", "Engineering Philosophy");
  const ps = [
    ["⚡", "零沟通损耗", "五个 Agent 共享全局上下文，\n导演意图 100% 无损传递给剪辑师。"],
    ["🔧", "全自动质检自愈", "发现素材逻辑错误，\nQC Agent 瞬间驳回并触发重练。"],
    ["🚀", "极致并发", "突破人类精力极限，\n50 集短剧同时并行渲染与剪辑。"],
  ];
  ps.forEach(([icon, title, desc], i) => {
    const px = 0.5 + i * 3.15;
    s.addShape(pres.shapes.RECTANGLE, {
      x: px, y: 1.5, w: 2.85, h: 2.8,
      fill: mkCardFill(), line: mkCardLine(),
    });
    s.addText(icon, {
      x: px, y: 1.7, w: 2.85, h: 0.55,
      fontSize: 32, align: "center", margin: 0,
    });
    s.addText(title, {
      x: px + 0.15, y: 2.3, w: 2.55, h: 0.4,
      fontSize: 16, fontFace: SANS, color: FG, align: "center", margin: 0,
    });
    s.addText(desc, {
      x: px + 0.15, y: 2.75, w: 2.55, h: 1.3,
      fontSize: 12, fontFace: SANS, color: DIM,
      align: "center", valign: "top", lineSpacingMultiple: 1.4, margin: 0,
    });
  });
  s.addNotes("三个原则：零损耗（共享上下文）、自愈（自动质检重练）、极致并发（50集同时跑）。");
}

// ============ 6. 全球分发 ============
{
  const s = darkSlide();
  slideNum(s, 6);
  sectionHead(s, "05", "全球分发", "IP跨国迁移 + 深度本地化");
  const ms = [
    ["🌎", "北美 / 欧洲", "ARPU $80/月，市场 $2B+\n霸总、狼人、复仇等强情绪母题"],
    ["🌏", "东南亚 / 拉美", "下载量 +60% QoQ\nIAA 占比 4.7% → 24.7%"],
    ["💀", "传统出海痛点", "「翻译剧」机械生硬\n海外声优贵且丢失戏剧张力"],
    ["⚡", "ClawSeries 方案", "AI 声纹克隆 + 表情同步\n文化折扣最小化"],
  ];
  ms.forEach(([icon, t, b], i) => {
    const cx = 0.5 + (i % 2) * 4.6;
    const cy = 1.45 + Math.floor(i / 2) * 1.65;
    card(s, cx, cy, 4.3, 1.45, icon, t, b);
  });
  s.addText("🇺🇸 EN   🇯🇵 JP   🇪🇸 ES   🇰🇷 KR   🇫🇷 FR   🇩🇪 DE   🇧🇷 PT   🇮🇳 HI   🇹🇭 TH", {
    x: 0.5, y: 4.85, w: 9, h: 0.3,
    fontSize: 11, fontFace: MONO, color: DIMMER, align: "center",
  });
  s.addNotes("北美 ARPU $80/月，市场 $2B。东南亚下载量季度涨 60%。我们用 AI 声纹克隆解决翻译剧痛点。");
}

// ============ 7. 商业形态 ============
{
  const s = darkSlide();
  slideNum(s, 7);
  sectionHead(s, "06", "商业形态重构", "Business Evolution");
  s.addShape(pres.shapes.RECTANGLE, {
    x: 1.0, y: 1.6, w: 8, h: 1.0,
    fill: { color: "252840" }, line: { color: "3D4070", pt: 1 },
  });
  s.addText("在 ClawSeries 的架构下，「短剧公司」不再是一个需要租赁场地、招聘数十名员工的实体组织，而是一套部署在云端的自动化代码。", {
    x: 1.2, y: 1.65, w: 7.6, h: 0.9,
    fontSize: 14, fontFace: SANS, color: DIM,
    align: "center", valign: "middle", lineSpacingMultiple: 1.5,
  });
  s.addText("一句话", {
    x: 0.5, y: 3.0, w: 9, h: 0.8,
    fontSize: 54, fontFace: MONO, color: ACCENT, align: "center",
  });
  s.addText("= 过去一个团队数个月的制片工作", {
    x: 0.5, y: 3.75, w: 9, h: 0.45,
    fontSize: 18, fontFace: SANS, color: DIM, align: "center",
  });
  s.addNotes("短剧公司变成云端代码。一句话输入，一小时出片。");
}

// ============ 8. CLOSING ============
{
  const s = darkSlide();
  slideNum(s, 8);
  s.addText([
    { text: "「", options: { color: ACCENT, fontSize: 36, fontFace: MONO } },
    { text: "用毫秒级的 Agent 内部通信，取代漫长的人类沟通会议", options: { color: FG, fontSize: 22, fontFace: MONO } },
    { text: "」", options: { color: ACCENT, fontSize: 36, fontFace: MONO } },
  ], {
    x: 1.0, y: 1.3, w: 8, h: 1.0,
    fontFace: MONO, align: "center", valign: "middle",
  });
  s.addText("— ClawSeries 核心技术哲学", {
    x: 1.0, y: 2.3, w: 8, h: 0.35,
    fontSize: 11, fontFace: MONO, color: DIMMER, align: "center",
    charSpacing: 2,
  });
  s.addText("Thanks.", {
    x: 0.5, y: 3.2, w: 9, h: 0.9,
    fontSize: 54, fontFace: SANS, color: FG, align: "center",
  });
  s.addText("CLAWSERIES — 零人AI短剧公司 — 2026", {
    x: 0.5, y: 4.4, w: 9, h: 0.35,
    fontSize: 11, fontFace: MONO, color: DIMMER, align: "center",
    charSpacing: 2,
  });
  s.addNotes("感谢各位评委。AI 短剧的最后一公里不是模型能力，而是自动化协作。欢迎提问。");
}

pres.writeFile({ fileName: __dirname + "/ClawSeries.pptx" })
  .then(() => console.log("ClawSeries.pptx created"))
  .catch(err => { console.error(err); process.exit(1); });
