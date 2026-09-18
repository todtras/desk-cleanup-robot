/* =====================================================================
   editorial-deck / theme.js
   "Light editorial + dark section band" — pptxgenjs 덱 디자인 시스템

   이 파일을 빌드 폴더(node_modules 옆)로 복사해서 쓴다.
     const T = require("./theme.js");
     const p = T.createDeck({ title: "...", author: "...", footer: "..." });

   색·폰트만 아래 토큰에서 바꾸면 전체 덱 톤이 한 번에 바뀐다.
   ===================================================================== */
const pptxgen = require("pptxgenjs");

/* ---------------------------- 디자인 토큰 ----------------------------
   악센트는 "한 가지"만 쓴다. 색을 늘리는 순간 어떤 색이 중요한지
   독자가 알 수 없게 되고, 그게 "촌스럽다"는 인상의 가장 흔한 원인이다.
   ALERT는 결함·실패·경고를 말하는 자리에만 쓴다(덱 전체에서 1~3회). */
const C = {
  PAPER: "FAFAF9",      // 본문 바탕 — 순백(FFFFFF)보다 눈이 편하고 카드가 떠 보인다
  INK: "12141A",        // 제목·강조. 순검정(000000)은 화면에서 탁해 보인다
  INK_MID: "545A67",    // 본문
  INK_SOFT: "8A909E",   // 캡션·푸터
  LINE: "E3E3DD",       // 헤어라인
  SOFT: "F1F1EC",       // 카드 면 (바탕보다 아주 살짝 어둡게)
  WHITE: "FFFFFF",      // 바탕 위에 떠 있어야 하는 카드
  ACCENT: "2540F2",     // 단 하나의 악센트
  ACCENT_SOFT: "E8EBFE",// 악센트 면
  ACCENT_INK: "4A4FA8", // 악센트 면 위의 본문
  ACCENT_DARK: "7D8AF5",// 다크 면 위의 악센트 (그냥 ACCENT는 다크에서 안 읽힌다)
  ALERT: "E0402A",      // 결함·실패 지점 전용
  ALERT_SOFT: "FCEDEA",
  ALERT_DARK: "FF7A5C", // 다크 면 위의 경고색
  D_LINE: "2E323C",     // 다크 면 헤어라인
  D_TEXT: "C9CDD6",     // 다크 면 본문
  D_MUTED: "6F7686",    // 다크 면 약한 글자
  D_LABEL: "8D93A3",
};

/* 폰트 — Pretendard는 웨이트별로 별도 패밀리 이름을 가진다.
   bold:true 로는 Black/Light를 못 만들기 때문에 패밀리 이름을 직접 쓴다. */
const F = {
  BASE: "Pretendard",            // Regular + bold:true → Bold
  BLACK: "Pretendard Black",     // 큰 숫자·표지 타이틀
  BOLD: "Pretendard Bold",
  SEMI: "Pretendard SemiBold",   // 라벨·eyebrow
  MEDIUM: "Pretendard Medium",
  LIGHT: "Pretendard Light",     // 캡션·다크 면 부연
  MONO: "Consolas",
};

/* 그리드 — 16:9(13.333 × 7.5 인치) 기준.
   본문은 BODY_Y ~ 6.72 사이에만 놓는다. 이 규칙 하나로 슬라이드마다
   콘텐츠 상·하단이 정렬되어 넘길 때 화면이 덜컹거리지 않는다. */
const G = {
  W: 13.333,
  H: 7.5,
  M: 0.72,            // 좌우 여백
  get CW() { return this.W - this.M * 2; },  // 11.893
  BODY_Y: 2.12,       // 콘텐츠 시작선
  BODY_BOTTOM: 6.72,  // 콘텐츠 끝선
  FOOT_Y: 6.96,       // 푸터 헤어라인
  BAND_H: 1.76,       // 섹션 밴드 높이
  RADIUS: 0.12,       // 카드 모서리
};

/* 한글에 라틴용 자간을 주면 "설 계 원 칙"처럼 낱자가 흩어진다.
   한글은 글자 자체가 이미 정사각 공간을 쓰기 때문에 추가 자간이 필요 없다. */
const HANGUL = /[㄰-㆏가-힣]/;
const track = (text, latin) => (HANGUL.test(String(text)) ? 0 : latin);

/* 문자열이 차지할 폭(인치) 추정.
   한글은 정사각(1.0), 라틴·숫자는 그 절반쯤(0.5), 공백은 0.3 단위로 세고
   Pretendard 실측 계수 0.0122 in/pt 를 곱한다. 렌더 대조로 보정한 값이라
   ±5% 안에서 맞는다. 제목이 두 줄로 흘러넘치는 사고를 빌드에서 잡는 용도. */
function estWidth(text, size) {
  let u = 0;
  for (const ch of String(text)) {
    if (ch === "\n") break;                       // 첫 줄만 센다
    if (ch === " ") u += 0.3;
    else if (HANGUL.test(ch)) u += 1;
    else if (/[　-〿—–]/.test(ch)) u += 1;  // 전각기호·대시
    else u += 0.5;
  }
  return u * 0.0122 * size;
}

const T = (o = {}) => ({ isTextBox: true, margin: 0, ...o });

/* ------------------------- 빌드 타임 지오메트리 검사 -------------------------
   pptxgenjs는 음수 높이를 그대로 XML로 써버리고, 그 파일은 PowerPoint에서
   아예 열리지 않는다(에러 메시지도 원인을 안 알려준다). 계산식으로 좌표를
   잡는 이상 이 사고는 반드시 나므로, 빌드 단계에서 막는다. */
const ISSUES = [];  // 치명적 — 빌드 중단
const WARNS = [];   // 디자인 결함 — 빌드는 되지만 렌더에서 반드시 확인할 것

function createDeck(opts = {}) {
  const p = new pptxgen();
  p.layout = "LAYOUT_WIDE";
  if (opts.author) p.author = opts.author;
  if (opts.title) p.title = opts.title;
  p.__footer = opts.footer || opts.title || "";
  p.__slides = [];

  const addSlide = p.addSlide.bind(p);
  let no = 0;
  p.addSlide = function () {
    const s = addSlide();
    const tag = `slide ${String(no++).padStart(2, "0")}`;
    s.__tag = tag;
    s.__els = [];
    p.__slides.push(s);
    ["addText", "addShape", "addImage", "addChart"].forEach((m) => {
      const orig = s[m].bind(s);
      s[m] = function (...args) {
        const o = args[args.length - 1] || {};
        const n = (v) => typeof v === "number" && isFinite(v);
        if (n(o.w) && o.w < 0) ISSUES.push(`${tag} ${m}: w=${o.w.toFixed(3)}`);
        if (n(o.h) && o.h < 0) ISSUES.push(`${tag} ${m}: h=${o.h.toFixed(3)} (음수 높이 → 파일이 안 열림)`);
        if (n(o.w) && n(o.h) && o.w === 0 && o.h === 0) ISSUES.push(`${tag} ${m}: 0×0`);
        if (n(o.x) && n(o.w) && o.x + o.w > G.W + 0.02) ISSUES.push(`${tag} ${m}: 오른쪽 ${(o.x + o.w).toFixed(2)}" > ${G.W}"`);
        if (n(o.y) && n(o.h) && o.y + o.h > G.H + 0.02) ISSUES.push(`${tag} ${m}: 아래쪽 ${(o.y + o.h).toFixed(2)}" > ${G.H}"`);
        if (n(o.x) && o.x < -0.02) ISSUES.push(`${tag} ${m}: x=${o.x.toFixed(2)}`);
        if (n(o.y) && o.y < -0.02) ISSUES.push(`${tag} ${m}: y=${o.y.toFixed(2)}`);
        if (n(o.y) && n(o.h)) s.__els.push({ m, y: o.y, bottom: o.y + o.h, footer: !!s.__inFooter });
        return orig(...args);
      };
    });
    return s;
  };
  return p;
}

/** 푸터가 있는 슬라이드에서 본문 요소가 푸터 선을 넘어가는지 검사.
    슬라이드 경계 안이라 위 검사는 통과하지만, 렌더해보면 글자가 푸터와 겹쳐 있다. */
function auditFooterBand(p) {
  p.__slides.forEach((s) => {
    if (!s.__hasFooter) return;
    s.__els
      .filter((e) => !e.footer && e.bottom > G.FOOT_Y - 0.04)
      .forEach((e) => {
        WARNS.push(`${s.__tag} ${e.m}: 아래쪽 ${e.bottom.toFixed(2)}"가 푸터 선(${G.FOOT_Y}")을 넘음`);
      });
  });
}

/** 검사 통과 시에만 파일을 쓴다. 치명적 오류면 종료코드 1. */
function finish(p, outPath) {
  auditFooterBand(p);
  if (ISSUES.length) {
    console.error(`지오메트리 오류 ${ISSUES.length}건 — 빌드 중단`);
    ISSUES.forEach((i) => console.error("  · " + i));
    process.exit(1);
  }
  if (WARNS.length) {
    console.warn(`경고 ${WARNS.length}건 — 파일은 만들었지만 렌더에서 반드시 확인할 것`);
    WARNS.forEach((w) => console.warn("  ! " + w));
  }
  return p.writeFile({ fileName: outPath }).then(() => {
    console.log("OK →", outPath);
  });
}

/* ------------------------------ 슬라이드 ------------------------------ */
/** tone: "paper"(기본) | "dark" */
function slide(p, tone = "paper") {
  const s = p.addSlide();
  s.background = { color: tone === "dark" ? C.INK : C.PAPER };
  s.__dark = tone === "dark";
  return s;
}

function rule(s, x, y, w, color, width = 0.75) {
  s.addShape("line", { x, y, w, h: 0, line: { color: color || (s.__dark ? C.D_LINE : C.LINE), width } });
}

/** 카드. 테두리를 긋지 않고 면 색으로만 구분한다 — 선이 늘어날수록 덱이 서류처럼 보인다. */
function panel(s, x, y, w, h, o = {}) {
  s.addShape("roundRect", {
    x, y, w, h,
    rectRadius: o.radius ?? G.RADIUS,
    fill: { color: o.fill ?? C.SOFT },
    line: o.line ? { color: o.line, width: 0.75 } : { type: "none" },
  });
}

/** 카드·구역 안의 작은 라벨 */
function label(s, text, x, y, w, color) {
  s.addText(String(text).toUpperCase(), T({
    x, y, w, h: 0.26,
    fontFace: F.SEMI, fontSize: 10,
    color: color || (s.__dark ? C.ACCENT_DARK : C.ACCENT),
    charSpacing: track(text, 1.4),
  }));
}

/** 01, 02 … 인덱스 숫자 (원형 배지 대신 타이포로 — 배지는 쉽게 유치해진다) */
function idx(s, x, y, w, txt, size = 11, color) {
  s.addText(txt, T({
    x, y, w, h: 0.34, fontFace: F.BLACK, fontSize: size, color: color || C.ACCENT, charSpacing: 0.2,
  }));
}

/* ------------------------------- 헤더 -------------------------------- */
/** 일반 슬라이드 헤더: eyebrow + 큰 제목 + 우상단 섹션 표식 */
function head(s, { eyebrow, title, section, size = 30, titleW }) {
  if (section) {
    s.addText(section, T({
      x: G.W - G.M - 5, y: 0.56, w: 5, h: 0.26, align: "right",
      fontFace: F.MEDIUM, fontSize: 9.5, color: C.INK_SOFT, charSpacing: track(section, 0.6),
    }));
  }
  if (eyebrow) {
    s.addText(eyebrow, T({
      x: G.M, y: 0.56, w: G.CW - 5.2, h: 0.26,
      fontFace: F.SEMI, fontSize: 10.5, color: C.ACCENT, charSpacing: track(eyebrow, 1.8),
    }));
  }
  const tw = titleW ?? G.CW;
  checkTitle(s, title, size, tw, "head");
  s.addText(title, T({
    x: G.M, y: 0.95, w: tw, h: 0.92,
    fontFace: F.BASE, fontSize: size, bold: true, color: C.INK,
    charSpacing: -0.4, lineSpacingMultiple: 1.1,
  }));
}

/* 제목은 한 줄이어야 한다. 두 줄이 되면 아래 콘텐츠와 간격이 무너지고,
   bandHead에서는 아예 다크 밴드 밖으로 흘러넘친다.
   줄이 넘칠 것 같으면 문장을 자르지 말고 size를 낮추는 쪽이 낫다. */
function checkTitle(s, title, size, boxW, where) {
  const est = estWidth(title, size);
  // 추정이 실측보다 1%쯤 짧게 나오는 경향이 있어 여유를 두고 0.95에서 경고한다.
  if (est > boxW * 0.95) {
    const fit = Math.floor(size * (boxW * 0.92) / est);
    WARNS.push(
      `${s.__tag} ${where}: 제목이 한 줄에 안 들어갈 것 같다 ` +
      `(추정 ${est.toFixed(2)}" > 상자 ${boxW.toFixed(2)}") — size를 ${fit} 정도로 낮추거나 제목을 줄일 것`
    );
  }
}

/** 섹션이 시작되는 슬라이드: 상단 풀블리드 다크 밴드.
    섹션 표지를 별도 슬라이드로 넣으면 장수가 늘어나는데, 장수 제한이 있는
    문서(공모전·심사)에서는 이 방식이 리듬은 주면서 장수는 그대로다. */
function bandHead(s, { num, section, eyebrow, title, size = 28 }) {
  s.addShape("rect", { x: 0, y: 0, w: G.W, h: G.BAND_H, fill: { color: C.INK }, line: { type: "none" } });
  s.addText(num, T({
    x: G.M, y: 0.42, w: 1.2, h: 0.95, valign: "middle",
    fontFace: F.BLACK, fontSize: 40, color: C.ACCENT, charSpacing: -1.6,
  }));
  s.addShape("rect", { x: G.M + 1.38, y: 0.5, w: 0.014, h: 0.8, fill: { color: "343A47" }, line: { type: "none" } });

  const tx = G.M + 1.72;
  const kicker = eyebrow ? `${section}  ·  ${eyebrow}` : section;
  s.addText(kicker, T({
    x: tx, y: 0.5, w: G.W - G.M - tx, h: 0.28,
    fontFace: F.SEMI, fontSize: 10.5, color: C.D_LABEL, charSpacing: track(kicker, 1.6),
  }));
  const tw = G.W - G.M - tx;
  checkTitle(s, title, size, tw, "bandHead");
  s.addText(title, T({
    x: tx, y: 0.8, w: tw, h: 0.62,
    fontFace: F.BASE, fontSize: size, bold: true, color: C.WHITE, charSpacing: -0.5,
  }));
}

function foot(s, p, n) {
  s.__hasFooter = true;
  s.__inFooter = true;   // 푸터 자신의 요소는 푸터 선 검사에서 제외
  rule(s, G.M, G.FOOT_Y, G.CW);
  s.addText(p.__footer, T({
    x: G.M, y: G.FOOT_Y + 0.1, w: 8, h: 0.26,
    fontFace: F.LIGHT, fontSize: 8.5, color: C.INK_SOFT, charSpacing: 0.3,
  }));
  s.addText(String(n).padStart(2, "0"), T({
    x: G.W - G.M - 1, y: G.FOOT_Y + 0.1, w: 1, h: 0.26, align: "right",
    fontFace: F.SEMI, fontSize: 8.5, color: C.INK_SOFT, charSpacing: 0.6,
  }));
  s.__inFooter = false;
}

/* ----------------------------- 콘텐츠 블록 ----------------------------- */
/** 악센트 대시 리스트. 불릿 점 대신 색 있는 대시 — 훨씬 덜 사무적이다. */
function list(s, items, o = {}) {
  const size = o.fontSize ?? 13;
  const paras = [];
  items.forEach((it, i) => {
    const last = i === items.length - 1;
    paras.push({ text: "— ", options: { color: o.dash ?? (s.__dark ? C.ACCENT_DARK : C.ACCENT), fontFace: F.SEMI, fontSize: size, bold: true } });
    paras.push({
      text: it,
      options: {
        color: o.color ?? (s.__dark ? C.D_TEXT : C.INK_MID), fontFace: F.BASE, fontSize: size,
        breakLine: !last, paraSpaceAfter: o.gap ?? 12,
      },
    });
  });
  s.addText(paras, T({
    x: o.x ?? G.M, y: o.y ?? G.BODY_Y, w: o.w ?? 6.6, h: o.h ?? 4.4,
    valign: o.valign ?? "top", lineSpacingMultiple: o.lh ?? 1.35,
  }));
}

/** 큰 숫자 + 설명 카드.
    숫자 블록 높이를 고정해두는 게 핵심 — 비율(h * 0.56 같은 것)로 잡으면
    카드 높이가 바뀔 때마다 숫자와 설명이 겹친다. */
function stat(s, x, y, w, h, big, small, o = {}) {
  const pad = o.pad ?? 0.34;
  panel(s, x, y, w, h, { fill: o.fill ?? C.SOFT });
  s.addText(big, T({
    x: x + pad, y: y + 0.16, w: w - pad * 2, h: 0.76, align: o.align ?? "left", valign: "bottom",
    fontFace: F.BLACK, fontSize: o.bigSize ?? 32, color: o.bigColor ?? C.INK, charSpacing: -1.2,
  }));
  s.addText(small, T({
    x: x + pad, y: y + 1.0, w: w - pad * 2, h: Math.max(h - 1.14, 0.3), align: o.align ?? "left", valign: "top",
    fontFace: F.BASE, fontSize: o.smallSize ?? 11, color: o.smallColor ?? C.INK_MID, lineSpacingMultiple: 1.3,
  }));
}

/** 라벨 + 내용 헤어라인 행 목록. 표를 그리지 않고 정보를 정렬하는 가장 깔끔한 방법.
    items: [[label, text], ...]   반환값: 목록이 끝나는 y좌표 */
function rows(s, o) {
  const { items } = o;
  const x = o.x ?? G.M, w = o.w ?? G.CW, y0 = o.y ?? G.BODY_Y;
  const rowH = o.rowH ?? 0.66, labelW = o.labelW ?? 1.8;
  const numbered = o.numbered === true;
  items.forEach((it, i) => {
    const y = y0 + i * rowH;
    rule(s, x, y, w);
    let tx = x;
    if (numbered) {
      idx(s, x, y + rowH * 0.42, 0.6, String(i + 1).padStart(2, "0"), 11);
      tx = x + 0.72;
    }
    s.addText(it[0], T({
      x: tx, y: y + rowH * 0.18, w: labelW, h: rowH * 0.68, valign: "middle",
      fontFace: F.SEMI, fontSize: o.labelSize ?? 11,
      color: numbered ? C.INK : C.ACCENT, charSpacing: track(it[0], 0.6),
    }));
    s.addText(it[1], T({
      x: tx + labelW + 0.15, y: y + rowH * 0.18, w: w - (tx - x) - labelW - 0.15, h: rowH * 0.68, valign: "middle",
      fontFace: F.BASE, fontSize: o.size ?? 12.5, color: o.color ?? C.INK, charSpacing: -0.2,
    }));
  });
  const end = y0 + items.length * rowH;
  rule(s, x, end, w);
  return end;
}

/** 상단에 굵은 선을 얹은 메타 컬럼들 (기간/팀/예산/담당 같은 개요 한 줄) */
function metaRow(s, o) {
  const { items } = o;
  const x0 = o.x ?? G.M, w = o.w ?? G.CW, y = o.y ?? G.BODY_Y, gap = o.gap ?? 0.19;
  const cw = (w - gap * (items.length - 1)) / items.length;
  items.forEach((m, i) => {
    const x = x0 + i * (cw + gap);
    rule(s, x, y, cw, C.ACCENT, 1.5);
    s.addText(m[0], T({
      x, y: y + 0.14, w: cw, h: 0.26,
      fontFace: F.SEMI, fontSize: 9.5, color: C.ACCENT, charSpacing: track(m[0], 1.2),
    }));
    s.addText(m[1], T({
      x, y: y + 0.44, w: cw, h: 0.62,
      fontFace: F.MEDIUM, fontSize: 12.5, color: C.INK, lineSpacingMultiple: 1.25, charSpacing: -0.2,
    }));
  });
  return y + 1.06;
}

/** 다크 코드 블록. lines: [{ text, tone }] — tone: "code" | "comment" | "hot" */
function codeBlock(s, o) {
  const { x, y, w, h, filename, lines } = o;
  s.addShape("roundRect", { x, y, w, h, rectRadius: G.RADIUS, fill: { color: C.INK }, line: { type: "none" } });
  let ty = y + 0.28;
  if (filename) {
    s.addText(filename, T({
      x: x + 0.45, y: y + 0.24, w: w - 0.9, h: 0.28, fontFace: F.MONO, fontSize: 10, color: C.D_MUTED,
    }));
    rule(s, x + 0.45, y + 0.64, w - 0.9, "2A2E38");
    ty = y + 0.8;
  }
  const tones = { code: C.D_LABEL, comment: C.D_MUTED, hot: C.ALERT_DARK };
  s.addText(lines.map((l, i) => ({
    text: l.text,
    options: {
      color: tones[l.tone || "code"],
      bold: l.tone === "hot",
      italic: l.tone === "comment",
      breakLine: i !== lines.length - 1,
    },
  })), T({
    x: x + 0.45, y: ty, w: w - 0.9, h: h - (ty - y) - 0.3,
    fontFace: F.MONO, fontSize: o.fontSize ?? 15, valign: "top", lineSpacingMultiple: 1.35,
  }));
}

/** 사진 여러 장을 가로로 배치 + 캡션.
    items: [{ path, ratio(가로/세로), caption }]
    폭이 maxW를 넘거나 아래가 maxBottom을 넘으면 높이를 자동으로 줄인다 —
    사진이 옆 카드를 덮거나 푸터를 타고 내려가는 사고를 막는다.
    반환값: 캡션까지 끝나는 y좌표 */
function photoStrip(s, o) {
  const { items } = o;
  const x0 = o.x ?? G.M, maxW = o.maxW ?? G.CW, y = o.y, gap = o.gap ?? 0.2;
  const maxBottom = o.maxBottom ?? G.BODY_BOTTOM;
  const capH = items.some((i) => i.caption) ? 0.33 : 0;
  let h = o.h;
  const sumRatio = items.reduce((a, it) => a + it.ratio, 0);
  const totalGap = gap * (items.length - 1);
  if (h * sumRatio + totalGap > maxW) h = (maxW - totalGap) / sumRatio;
  if (y + h + capH > maxBottom) h = Math.max(maxBottom - y - capH, 0.3);
  let x = x0;
  items.forEach((it) => {
    const w = h * it.ratio;
    s.addImage({ path: it.path, x, y, w, h });
    if (it.caption) {
      s.addText(it.caption, T({
        x, y: y + h + 0.07, w, h: 0.26, align: "center",
        fontFace: F.LIGHT, fontSize: 9.5, color: C.INK_SOFT,
      }));
    }
    x += w + gap;
  });
  return y + h + capH;
}

/** 아직 받지 못한 사진의 자리.
    사진을 기다리느라 덱 작업을 멈추지 말고, 자리를 잡아두고 나머지를 진행한다.
    화면에 "사진 필요"가 크게 보이고 빌드 때 경고가 뜨므로 실수로 이 상태로
    제출될 일은 없다. 사진이 오면 photoStrip / addImage 로 교체한다. */
function photoSlot(s, o) {
  const { x, y, w, h } = o;
  panel(s, x, y, w, h, { fill: C.SOFT });
  s.addText([
    { text: "사진 필요\n", options: { fontFace: F.SEMI, fontSize: 12, color: C.INK_SOFT } },
    { text: o.want || "", options: { fontFace: F.LIGHT, fontSize: 10.5, color: C.INK_SOFT } },
  ], T({
    x: x + 0.2, y, w: w - 0.4, h, align: "center", valign: "middle", lineSpacingMultiple: 1.4,
  }));
  WARNS.push(`${s.__tag} photoSlot: 사진 미수령 — ${o.want || "(설명 없음)"}`);
}

/** 한 문장을 크게 세우는 인용 블록 */
function pullQuote(s, o) {
  const { x, y, w, h } = o;
  panel(s, x, y, w, h, { fill: o.fill ?? C.ACCENT_SOFT });
  s.addText([
    o.pre ? { text: o.pre, options: { color: C.INK_MID, fontFace: F.BASE, fontSize: o.small ?? 15 } } : null,
    { text: o.strong, options: { color: o.strongColor ?? C.ACCENT, fontFace: F.BASE, bold: true, fontSize: o.big ?? 22 } },
    o.post ? { text: o.post, options: { color: C.INK_MID, fontFace: F.BASE, fontSize: o.small ?? 15 } } : null,
  ].filter(Boolean), T({
    x: x + 0.46, y, w: w - 0.92, h, valign: "middle", charSpacing: -0.3, lineSpacingMultiple: 1.3,
  }));
}

/** 하단 한 줄 요약 밴드 (라벨 + 문장) */
function noteBar(s, o) {
  const x = o.x ?? G.M, w = o.w ?? G.CW, y = o.y, h = o.h ?? 0.9;
  if (o.fill !== false) panel(s, x, y, w, h, { fill: o.fill ?? C.ACCENT_SOFT });
  s.addText([
    { text: o.label + "   ", options: { color: C.ACCENT, fontFace: F.SEMI, bold: true } },
    { text: o.text, options: { color: o.color ?? C.INK_MID, fontFace: F.BASE } },
  ], T({
    x: x + 0.42, y, w: w - 0.84, h, valign: "middle", fontSize: o.size ?? 12.5, lineSpacingMultiple: 1.3,
  }));
}

/** 막대차트 기본값. 데이터 라벨 소수점은 dataLabelFormatCode로 직접 지정해야
    0.73 이 1 로 반올림돼 표시되는 사고가 안 난다. */
function chartOpts(o = {}) {
  return {
    barDir: "col", showTitle: false, showValue: true, dataLabelPosition: "outEnd",
    dataLabelColor: C.INK, dataLabelFontSize: 13, dataLabelFontFace: F.SEMI,
    dataLabelFormatCode: o.format ?? "0",
    chartColors: [C.LINE, C.ACCENT],
    catAxisLabelColor: C.INK_MID, catAxisLabelFontFace: F.BASE, catAxisLabelFontSize: 11.5,
    valAxisHidden: true, showLegend: false,
    catGridLine: { style: "none" }, valGridLine: { style: "none" },
    barGapWidthPct: 140,
    ...o,
  };
}

module.exports = {
  C, F, G, T, track, estWidth, ISSUES, WARNS,
  createDeck, finish, slide,
  head, bandHead, foot,
  panel, rule, label, idx,
  list, stat, rows, metaRow, codeBlock, photoStrip, photoSlot, pullQuote, noteBar, chartOpts,
};
