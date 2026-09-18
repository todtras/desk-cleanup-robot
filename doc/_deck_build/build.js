const T = require("./theme.js");
const { C, F, G } = T;
const path = require("path");
const A = path.join(__dirname, "assets");

/** 다크 슬라이드 배경 사진 + 어둡게 까는 오버레이.
    사진은 분위기용이므로 글자가 항상 이기도록 충분히 눌러둔다. */
function bgPhoto(s, file, transparency = 42) {
  s.addImage({ path: path.join(A, file), x: 0, y: 0, w: G.W, h: G.H });
  s.addShape("rect", {
    x: 0, y: 0, w: G.W, h: G.H,
    fill: { color: C.INK, transparency }, line: { type: "none" },
  });
}

const p = T.createDeck({
  title: "AI 기반 데스크 오브젝트 인식·분류 정리 로봇",
  author: "인턴십 프로젝트 팀",
  footer: "데스크 오브젝트 정리 로봇 · 인턴십 프로젝트 기획",
});
let n = 0;

/* ========================= 01 표지 ========================= */
{
  n++;
  const s = T.slide(p, "dark");
  bgPhoto(s, "cover.jpg", 42);
  s.addText("INTERNSHIP PROJECT PROPOSAL", T.T({
    x: G.M, y: 0.82, w: 8, h: 0.3,
    fontFace: F.SEMI, fontSize: 10.5, color: C.D_MUTED, charSpacing: 2.4,
  }));

  s.addText([
    { text: "AI 기반 데스크 오브젝트", options: { color: C.WHITE } },
  ], T.T({
    x: G.M, y: 2.42, w: 11.9, h: 0.9,
    fontFace: F.BLACK, fontSize: 54, charSpacing: -2.2,
  }));
  s.addText([
    { text: "인식·분류", options: { color: C.ACCENT_DARK } },
    { text: " 정리 로봇", options: { color: C.WHITE } },
  ], T.T({
    x: G.M, y: 3.38, w: 11.9, h: 0.9,
    fontFace: F.BLACK, fontSize: 54, charSpacing: -2.2,
  }));

  s.addText(
    "카메라로 책상 위 물건을 인식·분류하고, 로봇팔이 지정된 수거함으로 옮겨 담는 시스템",
    T.T({
      x: G.M, y: 4.62, w: 10.5, h: 0.44,
      fontFace: F.LIGHT, fontSize: 14.5, color: C.D_TEXT,
    })
  );

  T.rule(s, G.M, 6.18, G.CW, C.D_LINE);
  s.addText("3인 팀 (팀장 1 · 팀원 2)  ·  80시간 / 10주  ·  A4000 1장", T.T({
    x: G.M, y: 6.38, w: 7.5, h: 0.3,
    fontFace: F.MEDIUM, fontSize: 11, color: C.D_TEXT,
  }));
  s.addText("OBJECT DETECTION · REINFORCEMENT LEARNING · ROBOT ARM", T.T({
    x: G.W - G.M - 6.5, y: 6.38, w: 6.5, h: 0.3, align: "right",
    fontFace: F.SEMI, fontSize: 9.5, color: C.ACCENT_DARK, charSpacing: 1.2,
  }));
}

/* ========================= 02 목차 ========================= */
{
  n++;
  const s = T.slide(p, "dark");
  s.addText("CONTENTS", T.T({
    x: G.M, y: 0.82, w: 6, h: 0.3,
    fontFace: F.SEMI, fontSize: 10.5, color: C.D_MUTED, charSpacing: 2.4,
  }));
  s.addText("목차", T.T({
    x: G.M, y: 1.28, w: 6, h: 0.7,
    fontFace: F.BLACK, fontSize: 34, color: C.WHITE, charSpacing: -1.2,
  }));
  s.addText("배경에서 계획까지 다섯 단계", T.T({
    x: G.W - G.M - 6, y: 1.62, w: 6, h: 0.34, align: "right",
    fontFace: F.LIGHT, fontSize: 11.5, color: C.D_TEXT,
  }));

  const toc = [
    ["01", "배경", "주제 선정 배경과 목적"],
    ["02", "목표", "프로젝트 목표 4가지와 동작 흐름 6단계"],
    ["03", "기술", "예상 기술 스택과 두 가지 핵심 과제"],
    ["04", "환경", "개발 환경 · 수행 방식 · 팀 구성"],
    ["05", "계획", "일정 · 기대 효과 · 리스크"],
  ];
  const y0 = 2.62, rowH = 0.82;
  toc.forEach((t, i) => {
    const y = y0 + i * rowH;
    T.rule(s, G.M, y, G.CW, C.D_LINE);
    s.addText(t[0], T.T({
      x: G.M, y: y + 0.2, w: 1.3, h: 0.44, valign: "middle",
      fontFace: F.BLACK, fontSize: 20, color: C.ACCENT_DARK, charSpacing: -0.4,
    }));
    s.addText(t[1], T.T({
      x: G.M + 1.3, y: y + 0.2, w: 4.6, h: 0.44, valign: "middle",
      fontFace: F.BASE, fontSize: 19, bold: true, color: C.WHITE, charSpacing: -0.4,
    }));
    s.addText(t[2], T.T({
      x: G.W - G.M - 7, y: y + 0.2, w: 7, h: 0.44, valign: "middle", align: "right",
      fontFace: F.LIGHT, fontSize: 12, color: C.D_TEXT,
    }));
  });
  T.rule(s, G.M, y0 + toc.length * rowH, G.CW, C.D_LINE);
}

/* ==================== 03 배경 (섹션 01) ==================== */
{
  n++;
  const s = T.slide(p);
  T.bandHead(s, {
    num: "01", section: "배경", eyebrow: "BACKGROUND",
    title: "단순 제어가 아닌 인식·판단 중심",
  });

  T.rows(s, {
    x: G.M, y: G.BODY_Y, w: 6.5, rowH: 1.1, labelW: 1.6,
    items: [
      ["프로젝트 성격", "피지컬 AI 기업 인턴십 프로젝트"],
      ["요구 사항", "단순 제어가 아닌 AI 인식·판단 역량이 드러나는 주제"],
      ["컨셉", "로봇팔 + 카메라 조합의 “보고 이해해서 처리한다”"],
      ["접근", "고정된 규칙이 아닌 학습 기반 인식을 중심에 둠"],
    ],
  });

  const cx = 7.75, cw = G.W - G.M - cx;
  T.panel(s, cx, G.BODY_Y, cw, 4.56, { fill: C.INK });
  s.__dark = true;
  T.label(s, "한 줄 소개", cx + 0.44, G.BODY_Y + 0.34, 4, C.ACCENT_DARK);
  s.addText(
    "카메라로 책상 위 물건(필기구, 컵 등)을 인식·분류하고, 로봇팔이 지정된 수거함으로 옮겨 담는 시스템",
    T.T({
      x: cx + 0.44, y: G.BODY_Y + 0.74, w: cw - 0.88, h: 1.72,
      fontFace: F.BASE, fontSize: 17, bold: true, color: C.WHITE,
      charSpacing: -0.5, lineSpacingMultiple: 1.3,
    })
  );
  T.rule(s, cx + 0.44, G.BODY_Y + 2.6, cw - 0.88, C.D_LINE);
  const meta = [
    ["프로젝트명", "AI 기반 데스크 오브젝트\n인식·분류 정리 로봇 (가안)"],
    ["개발 방식", "AI 코딩 에이전트를 활용한\n바이브코딩 중심 개발"],
  ];
  meta.forEach((m, i) => {
    const my = G.BODY_Y + 2.82 + i * 0.86;
    s.addText(m[0], T.T({
      x: cx + 0.44, y: my, w: 1.5, h: 0.3,
      fontFace: F.SEMI, fontSize: 10, color: C.D_LABEL,
    }));
    s.addText(m[1], T.T({
      x: cx + 0.44, y: my + 0.26, w: cw - 0.88, h: 0.56,
      fontFace: F.BASE, fontSize: 11.5, color: C.D_TEXT, lineSpacingMultiple: 1.25,
    }));
  });
  s.__dark = false;
  T.foot(s, p, n);
}

/* ==================== 04 목표 (섹션 02) ==================== */
{
  n++;
  const s = T.slide(p);
  T.bandHead(s, {
    num: "02", section: "목표", eyebrow: "GOALS",
    title: "프로젝트 목표",
  });

  T.rows(s, {
    y: G.BODY_Y, rowH: 0.95, labelW: 1.9, numbered: true, size: 13.5,
    items: [
      ["탐지 · 분류", "책상 위 임의의 물건을 카메라로 탐지하고 카테고리를 분류한다"],
      ["파지 · 투입", "분류 결과에 따라 로봇팔이 물건을 파지하여 지정된 수거함에 넣는다"],
      ["실패 보정", "파지 실패를 강화학습 기반으로 보정하여 반복 시도 성공률을 개선한다"],
      ["오픈 어휘", "사전에 정의되지 않은 물건에도 어느 정도 대응 가능한 인식 구조를 목표로 한다"],
    ],
  });

  T.noteBar(s, {
    y: 6.08, h: 0.62,
    label: "난이도 설계",
    text: "3·4번은 단순 고정 클래스 분류보다 난이도와 AI 비중을 높이기 위한 목표",
  });
  T.foot(s, p, n);
}

/* ==================== 05 동작 흐름 6단계 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "SCOPE", section: "02 목표",
    title: "동작 흐름 6단계",
  });

  const cards = [
    ["객체 탐지", "책상 위 물체의 위치·바운딩박스 검출"],
    ["객체 분류 · 인식", "필기구 / 컵 / 기타 카테고리 판별. 가능하면 open-vocabulary로 미등록 물체까지"],
    ["좌표 변환", "카메라 좌표 → 로봇팔 좌표계 변환 · 캘리브레이션"],
    ["파지", "분류 결과 기반 파지 자세 계산 및 실행"],
    ["분류함 이동", "카테고리별 지정 수거함으로 이동 후 릴리즈"],
    ["파지 실패 보정", "성공·실패 판정 후 강화학습 정책으로\n자세·접근 방향을 보정해 재시도"],
  ];
  const gx = 0.19, gy = 0.2;
  const cw = (G.CW - gx * 2) / 3, ch = 2.2;
  cards.forEach((c, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = G.M + col * (cw + gx), y = G.BODY_Y + row * (ch + gy);
    T.panel(s, x, y, cw, ch, { fill: C.WHITE });
    T.idx(s, x + 0.36, y + 0.28, 1, String(i + 1).padStart(2, "0"), 11, C.INK_SOFT);
    s.addShape("rect", {
      x: x + 0.36, y: y + 0.68, w: 0.3, h: 0.022,
      fill: { color: C.ACCENT }, line: { type: "none" },
    });
    s.addText(c[0], T.T({
      x: x + 0.36, y: y + 0.86, w: cw - 0.72, h: 0.4,
      fontFace: F.BASE, fontSize: 15, bold: true, color: C.INK, charSpacing: -0.3,
    }));
    s.addText(c[1], T.T({
      x: x + 0.36, y: y + 1.3, w: cw - 0.72, h: 0.85,
      fontFace: F.BASE, fontSize: 11.5, color: C.INK_MID, lineSpacingMultiple: 1.4,
    }));
  });
  T.foot(s, p, n);
}

/* ==================== 06 기술 스택 (섹션 03) ==================== */
{
  n++;
  const s = T.slide(p);
  T.bandHead(s, {
    num: "03", section: "기술", eyebrow: "TECH STACK",
    title: "예상 기술 스택 키워드",
  });

  const cols = [
    ["인식", ["Object Detection (YOLO 계열)", "Open-Vocabulary Detection", "VLM (Grounding DINO, CLIP)"]],
    ["제어", ["좌표 캘리브레이션", "Eye-in-hand / Eye-to-hand", "역기구학 기반 파지 자세 계산"]],
    ["강화학습", ["파지 실패 보정 정책 학습", "시뮬레이터 선학습 → 실물 전이", "Isaac Sim / PyBullet"]],
    ["기타", ["OCR (물체 표면 텍스트)", "ROS / 제어 프레임워크", "로봇팔 사양에 따라 결정"]],
  ];
  const cw = 2.83, gap = 0.19;
  cols.forEach((c, i) => {
    const x = G.M + i * (cw + gap);
    T.panel(s, x, G.BODY_Y, cw, 3.1, { fill: C.WHITE });
    T.idx(s, x + 0.34, G.BODY_Y + 0.34, 1.2, String(i + 1).padStart(2, "0"), 13);
    s.addShape("rect", {
      x: x + 0.34, y: G.BODY_Y + 0.74, w: 0.34, h: 0.022,
      fill: { color: C.ACCENT }, line: { type: "none" },
    });
    s.addText(c[0], T.T({
      x: x + 0.34, y: G.BODY_Y + 0.92, w: cw - 0.68, h: 0.44,
      fontFace: F.BASE, fontSize: 15.5, bold: true, color: C.INK, charSpacing: -0.3,
    }));
    s.addText(c[1].join("\n"), T.T({
      x: x + 0.34, y: G.BODY_Y + 1.38, w: cw - 0.68, h: 1.5,
      fontFace: F.BASE, fontSize: 11.5, color: C.INK_MID, lineSpacingMultiple: 1.5,
    }));
  });

  T.noteBar(s, {
    y: 5.72, h: 0.62,
    label: "개발 도구",
    text: "AI 코딩 에이전트(Claude Code 등)를 활용한 바이브코딩 — 구현 코드 작성을 에이전트에 위임",
  });
  T.foot(s, p, n);
}

/* ==================== 07 강화학습 파지 보정 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "KEY CHALLENGE 1", section: "03 기술",
    title: "파지 실패 보정 — 강화학습",
  });

  T.list(s, [
    "파지 성공·실패를 판정한 뒤, 강화학습 정책으로 자세와 접근 방향을 보정해 재시도",
    "시뮬레이터에서 선학습한 뒤 실물에 적용 (Isaac Sim / PyBullet)",
    "sim-to-real 격차는 실물 데이터 기반 미세조정으로 보완",
  ], { x: G.M, y: G.BODY_Y, w: 6.5, h: 2.02, fontSize: 13.5, gap: 14, valign: "middle" });

  T.stat(s, 7.75, G.BODY_Y, G.W - G.M - 7.75, 2.02, "16h",
    "6~7주차 배정 · 강화학습 기반 파지 보정 정책\n학습 및 실물 적용·튜닝",
    { bigSize: 34 });

  const qy = 4.46, qh = G.BODY_BOTTOM - qy;
  T.panel(s, G.M, qy, G.CW, qh, { fill: C.INK });
  s.__dark = true;
  T.label(s, "보정 루프", G.M + 0.46, qy + 0.26, 6, C.ACCENT_DARK);
  const steps = [
    ["STEP 01", "파지 실행", "분류 결과 기반 자세로 접근"],
    ["STEP 02", "성공·실패 판정", "판정 기준은 4주차에 정의"],
    ["STEP 03", "정책 보정", "자세·접근 방향을 강화학습으로 조정"],
    ["STEP 04", "재시도", "반복 시도 성공률 개선"],
  ];
  const qw = (G.CW - 0.92 - 0.3 * 3) / 4;
  steps.forEach((q, i) => {
    const x = G.M + 0.46 + i * (qw + 0.3);
    const last = i === steps.length - 1;
    s.addShape("rect", {
      x, y: qy + 0.74, w: qw, h: 0.022,
      fill: { color: last ? C.ACCENT : "343A47" }, line: { type: "none" },
    });
    s.addText(q[0], T.T({
      x, y: qy + 0.86, w: qw, h: 0.24,
      fontFace: F.SEMI, fontSize: 9.5, color: last ? C.ACCENT_DARK : C.D_MUTED, charSpacing: 1.2,
    }));
    s.addText(q[1], T.T({
      x, y: qy + 1.12, w: qw, h: 0.36,
      fontFace: F.BASE, fontSize: 15, bold: true, color: last ? C.WHITE : C.D_TEXT, charSpacing: -0.4,
    }));
    s.addText(q[2], T.T({
      x, y: qy + 1.5, w: qw, h: 0.6,
      fontFace: F.LIGHT, fontSize: 10.5, color: C.D_LABEL, lineSpacingMultiple: 1.3,
    }));
  });
  s.__dark = false;
  T.foot(s, p, n);
}

/* ==================== 08 Open-Vocabulary ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "KEY CHALLENGE 2", section: "03 기술",
    title: "Open-Vocabulary 인식 — 확장 과제",
  });

  const bw = 5.85, bh = 3.5;
  T.panel(s, G.M, G.BODY_Y, bw, bh, { fill: C.WHITE });
  T.label(s, "기본 범위", G.M + 0.45, G.BODY_Y + 0.4, 4, C.INK_SOFT);
  s.addText([
    { text: "사전에 정의된 카테고리\n", options: { color: C.INK_MID } },
    { text: "필기구 / 컵 / 기타", options: { color: C.INK } },
  ], T.T({
    x: G.M + 0.45, y: G.BODY_Y + 0.9, w: bw - 0.9, h: 1.5,
    fontFace: F.BASE, fontSize: 23, bold: true, charSpacing: -0.6, lineSpacingMultiple: 1.22,
  }));
  s.addText("고정 클래스 분류 — 학습한 물체만 처리", T.T({
    x: G.M + 0.45, y: G.BODY_Y + 2.62, w: bw - 0.9, h: 0.4,
    fontFace: F.LIGHT, fontSize: 11.5, color: C.INK_SOFT,
  }));

  const x2 = G.M + bw + 0.19;
  T.panel(s, x2, G.BODY_Y, bw, bh, { fill: C.INK });
  s.__dark = true;
  T.label(s, "확장 목표", x2 + 0.45, G.BODY_Y + 0.4, 4, C.ACCENT_DARK);
  s.addText([
    { text: "사전 정의되지 않은 물건까지\n", options: { color: C.D_TEXT } },
    { text: "VLM 기반 open-vocabulary", options: { color: C.WHITE } },
  ], T.T({
    x: x2 + 0.45, y: G.BODY_Y + 0.9, w: bw - 0.9, h: 1.5,
    fontFace: F.BASE, fontSize: 23, bold: true, charSpacing: -0.6, lineSpacingMultiple: 1.22,
  }));
  s.addText("미등록 물체에도 어느 정도 대응 가능한 구조", T.T({
    x: x2 + 0.45, y: G.BODY_Y + 2.62, w: bw - 0.9, h: 0.4,
    fontFace: F.LIGHT, fontSize: 11.5, color: C.D_MUTED,
  }));
  s.__dark = false;

  T.noteBar(s, {
    y: 5.9, h: 0.62, fill: C.SOFT,
    label: "우선순위",
    text: "80시간 내 강화학습까지 정규 단계로 수행해야 하므로 후순위 — 9주차 일정 여유에 따라 결정",
  });
  T.foot(s, p, n);
}

/* ==================== 09 개발 환경 (섹션 04) ==================== */
{
  n++;
  const s = T.slide(p);
  T.bandHead(s, {
    num: "04", section: "환경", eyebrow: "ENVIRONMENT",
    title: "개발 환경 — A4000 1장을 팀이 공유",
  });

  const sw = 2.83, sh = 1.62, gx = 0.19;
  [
    ["A4000", "GPU 1장 · 팀 공용"],
    ["80h", "총 개발 시간 · 주 1회 8시간"],
    ["10주", "개발 기간"],
    ["3인", "팀장 1명 + 팀원 2명"],
  ].forEach((st, i) => {
    T.stat(s, G.M + i * (sw + gx), G.BODY_Y, sw, sh, st[0], st[1], { bigSize: 32 });
  });

  T.rows(s, {
    y: G.BODY_Y + sh + 0.3, rowH: 0.66, labelW: 1.7,
    items: [
      ["GPU 운영", "인식 모델 학습과 강화학습이 A4000 1장을 공유 → 요일·시간대 분할, 학습 잡 큐 운영"],
      ["실험 규모", "이미지 해상도·스텝 수를 사전 조정하여 자원 경합 완화"],
      ["개발 방식", "AI 코딩 에이전트를 활용한 바이브코딩 중심 개발"],
      ["미확정", "로봇팔·카메라 사양 확정 후 제어 프레임워크(ROS 등) 결정"],
    ],
  });
  T.foot(s, p, n);
}

/* ==================== 10 에이전트 활용 개발 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "METHOD", section: "04 환경",
    title: "AI 에이전트 활용 개발 방식",
  });

  const bw = 5.85, bh = 2.6;
  T.panel(s, G.M, G.BODY_Y, bw, bh, { fill: C.WHITE });
  T.label(s, "에이전트가 맡는 것", G.M + 0.45, G.BODY_Y + 0.38, 4, C.INK_SOFT);
  s.addText("구현 코드 작성", T.T({
    x: G.M + 0.45, y: G.BODY_Y + 0.86, w: bw - 0.9, h: 0.7,
    fontFace: F.BASE, fontSize: 23, bold: true, color: C.INK, charSpacing: -0.6,
  }));
  s.addText("모듈 단위 구현을 에이전트에 위임", T.T({
    x: G.M + 0.45, y: G.BODY_Y + 1.66, w: bw - 0.9, h: 0.6,
    fontFace: F.LIGHT, fontSize: 11.5, color: C.INK_SOFT, lineSpacingMultiple: 1.3,
  }));

  const x2 = G.M + bw + 0.19;
  T.panel(s, x2, G.BODY_Y, bw, bh, { fill: C.INK });
  s.__dark = true;
  T.label(s, "팀이 맡는 것", x2 + 0.45, G.BODY_Y + 0.38, 4, C.ACCENT_DARK);
  s.addText("인터페이스 설계 · 검증 · 실물 튜닝", T.T({
    x: x2 + 0.45, y: G.BODY_Y + 0.86, w: bw - 0.9, h: 0.7,
    fontFace: F.BASE, fontSize: 21, bold: true, color: C.WHITE, charSpacing: -0.6,
  }));
  s.addText("사람의 시간을 판단이 필요한 곳에 집중", T.T({
    x: x2 + 0.45, y: G.BODY_Y + 1.66, w: bw - 0.9, h: 0.6,
    fontFace: F.LIGHT, fontSize: 11.5, color: C.D_MUTED, lineSpacingMultiple: 1.3,
  }));
  s.__dark = false;

  T.rows(s, {
    y: 4.9, rowH: 0.58, labelW: 1.7,
    items: [
      ["규약 우선", "착수 시점에 모듈 간 입출력 규약(탐지 결과 포맷, 좌표계, 파지 명령 스키마)을 문서로 고정"],
      ["검증 후 병합", "에이전트가 생성한 코드는 테스트 코드와 실물·시뮬레이션 검증을 거쳐 병합"],
      ["시간 재배분", "구현 시간 단축분을 실물 테스트와 강화학습 실험 시간으로 재배분"],
    ],
  });
  T.foot(s, p, n);
}

/* ==================== 11 팀 구성 및 협업 방식 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "TEAM", section: "04 환경",
    title: "팀 구성 및 협업 방식",
  });

  const gx = 0.19;
  const cw = (G.CW - gx * 2) / 3, ch = 2.1;
  [
    ["팀장", "대면", "로봇팔 제어, 좌표 캘리브레이션, 파지 실행, 통합 디버깅, 실물 테스트"],
    ["팀원 A", "비대면", "객체 탐지·분류 모델 개발 및 학습"],
    ["팀원 B", "비대면", "시뮬레이션 구축, 파지 보정 강화학습, 성능 평가"],
  ].forEach((c, i) => {
    const x = G.M + i * (cw + gx);
    T.panel(s, x, G.BODY_Y, cw, ch, { fill: C.WHITE });
    s.addText(c[0], T.T({
      x: x + 0.4, y: G.BODY_Y + 0.34, w: cw - 0.8, h: 0.44,
      fontFace: F.BASE, fontSize: 17, bold: true, color: C.INK, charSpacing: -0.4,
    }));
    s.addText(c[1], T.T({
      x: x + 0.4, y: G.BODY_Y + 0.82, w: cw - 0.8, h: 0.28,
      fontFace: F.SEMI, fontSize: 10, color: C.ACCENT,
    }));
    s.addText(c[2], T.T({
      x: x + 0.4, y: G.BODY_Y + 1.18, w: cw - 0.8, h: 0.8,
      fontFace: F.BASE, fontSize: 11.5, color: C.INK_MID, lineSpacingMultiple: 1.4,
    }));
  });

  T.rows(s, {
    y: G.BODY_Y + ch + 0.32, rowH: 0.62, labelW: 1.7,
    items: [
      ["인터페이스", "입출력 포맷을 초기에 합의하여 비대면 팀원도 각자 모듈을 독립 개발"],
      ["코드 리뷰", "주차별로 팀원이 직접 코드를 리뷰하는 시간 확보"],
      ["GPU 분배", "인식 모델 학습과 강화학습의 학습 시간대를 사전 분배"],
    ],
  });
  T.foot(s, p, n);
}

/* ==================== 12 일정 (섹션 05) ==================== */
{
  n++;
  const s = T.slide(p);
  T.bandHead(s, {
    num: "05", section: "계획", eyebrow: "SCHEDULE",
    title: "일정 — 10주 · 80시간",
  });

  T.rows(s, {
    y: G.BODY_Y, rowH: 0.5, labelW: 1.5, labelSize: 10.5, size: 12,
    items: [
      ["1주 · 8h", "주제 확정, 환경 세팅, 인터페이스 규약 정의, 에이전트 개발 환경 구축, 데이터 수집 시작"],
      ["2주 · 8h", "객체 탐지·분류 베이스라인 구축, 카메라-로봇팔 캘리브레이션"],
      ["3주 · 8h", "인식 성능 개선, 인식 결과 → 로봇 좌표 변환 파이프라인 연동"],
      ["4주 · 8h", "파지 로직 구현 및 1차 실물 테스트, 파지 성공·실패 판정 기준 정의"],
      ["5주 · 8h", "시뮬레이션 환경 구축, 파지 실패 케이스 데이터 수집"],
      ["6~7주 · 16h", "강화학습 기반 파지 보정 정책 학습 및 실물 적용·튜닝"],
      ["8주 · 8h", "전체 파이프라인 통합 테스트, 실패 케이스 보완"],
      ["9주 · 8h", "성능 지표 측정, 시연 시나리오 정리, 여유 시 open-vocabulary 확장"],
      ["10주 · 8h", "발표자료 준비, 최종 리허설"],
    ],
  });
  T.foot(s, p, n);
}

/* ==================== 13 기대 효과 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "EXPECTED OUTCOME", section: "05 계획",
    title: "기대 효과",
  });

  const gx = 0.19;
  const cw = (G.CW - gx * 2) / 3, ch = 3.4;
  [
    ["엔드투엔드 경험", "인식(AI)과 제어(로봇팔)를\n결합한 엔드투엔드\n파이프라인 구축 경험"],
    ["제품에 가까운 문제", "고정 클래스가 아닌 유연한 인식 구조로\n실제 피지컬 AI 제품에 가까운\n문제 해결 경험"],
    ["후속 연구 방향", "실패 케이스 분석을 통해\n강화학습·데이터 보강 등\n후속 연구 방향 도출"],
  ].forEach((c, i) => {
    const x = G.M + i * (cw + gx);
    T.panel(s, x, G.BODY_Y, cw, ch, { fill: C.WHITE });
    T.idx(s, x + 0.4, G.BODY_Y + 0.38, 1.2, String(i + 1).padStart(2, "0"), 13);
    s.addShape("rect", {
      x: x + 0.4, y: G.BODY_Y + 0.78, w: 0.34, h: 0.022,
      fill: { color: C.ACCENT }, line: { type: "none" },
    });
    s.addText(c[0], T.T({
      x: x + 0.4, y: G.BODY_Y + 0.96, w: cw - 0.8, h: 0.46,
      fontFace: F.BASE, fontSize: 16.5, bold: true, color: C.INK, charSpacing: -0.4,
    }));
    s.addText(c[1], T.T({
      x: x + 0.4, y: G.BODY_Y + 1.44, w: cw - 0.8, h: 1.7,
      fontFace: F.BASE, fontSize: 12.5, color: C.INK_MID, lineSpacingMultiple: 1.45,
    }));
  });
  T.foot(s, p, n);
}

/* ==================== 14 리스크 ==================== */
{
  n++;
  const s = T.slide(p);
  T.head(s, {
    eyebrow: "RISK", section: "05 계획",
    title: "리스크 및 대응",
  });

  T.rows(s, {
    y: G.BODY_Y, rowH: 0.72, labelW: 2.3, labelSize: 11, size: 12.5,
    items: [
      ["일정 압박", "80시간 내 강화학습까지 수행 → open-vocabulary는 후순위, 일정 여유에 따라 결정"],
      ["GPU 자원 경합", "A4000 1장 공유 → 학습 시간대 분배, 실험 규모(해상도·스텝 수) 사전 조정"],
      ["sim-to-real 격차", "시뮬레이션 정책이 실물에서 그대로 동작하지 않음 → 6~7주차에 실물 미세조정 시간 확보"],
      ["원격 개발 제약", "원격 팀원의 실물 로봇 접근 곤란 → 시뮬레이션·수집 데이터 기반 개발, 초기 인터페이스 합의"],
      ["캘리브레이션 정확도", "파지 성공률에 큰 영향 → 초반에 충분한 시간 배정"],
      ["코드 이해도 저하", "바이브코딩 특성 → 모듈 경계와 테스트를 명확히 하고 주차별 코드 리뷰 확보"],
    ],
  });
  T.foot(s, p, n);
}

/* ==================== 15 마무리 ==================== */
{
  n++;
  const s = T.slide(p, "dark");
  bgPhoto(s, "closing.jpg", 45);
  s.addText("THANK YOU", T.T({
    x: G.M, y: 0.82, w: 6, h: 0.3,
    fontFace: F.SEMI, fontSize: 10.5, color: C.D_MUTED, charSpacing: 2.4,
  }));

  s.addText("감사합니다", T.T({
    x: G.M, y: 2.86, w: 11.9, h: 0.92,
    fontFace: F.BLACK, fontSize: 48, color: C.WHITE, charSpacing: -1.8,
  }));
  s.addText("AI 기반 데스크 오브젝트 인식·분류 정리 로봇", T.T({
    x: G.M, y: 4.06, w: 10, h: 0.44,
    fontFace: F.LIGHT, fontSize: 15, color: C.D_TEXT,
  }));

  T.rule(s, G.M, 6.18, G.CW, C.D_LINE);
  s.addText("3인 팀 (팀장 1 · 팀원 2)  ·  80시간 / 10주  ·  A4000 1장", T.T({
    x: G.M, y: 6.38, w: 8, h: 0.3,
    fontFace: F.MEDIUM, fontSize: 11, color: C.D_TEXT,
  }));
}

T.finish(p, process.argv[2] || "./deck.pptx");
