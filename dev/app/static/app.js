/* 책상 정리 로봇 — 화면 공통 스크립트 (B 담당)
 *
 * 규칙
 *  - 서버와는 /api/... 와 /video/... 로만 이야기한다. cleaner.py 내부를 직접 기대하지 않는다
 *    (9주차에 FakeCleaner -> RealCleaner로 바뀌어도 화면은 그대로 돌아가야 함)
 *  - 물건 이름은 영어 키로 오니 화면에 보일 때만 한글로 바꾼다 (아래 OBJECTS/BINS)
 *  - 사용자는 로봇을 모르는 사람이다. "정책", "에피소드", "체크포인트" 같은 말은 쓰지 않는다
 */

/* cleaner.py의 OBJECTS / BINS와 같아야 한다. 서버가 바뀌면 여기도 같이 고친다 */
const OBJECTS = { tape: "테이프", bottle: "물병", pen: "펜", eraser: "지우개", paper: "종이" };
const BINS = { tape: "사무용품", bottle: "쓰레기", pen: "필기구", eraser: "필기구", paper: "쓰레기" };

/* 인식 박스 좌표의 기준 크기. ui_pack 영상이 640x480이라 그 좌표로 온다.
 * 9주차에 진짜 카메라 해상도가 다르면 박스가 어긋나므로, 그때는 서버가 status에
 * 화면 크기를 같이 주도록 A와 맞춰야 한다 (README_UI.md의 '서버에 부탁할 것' 참고) */
const FRAME_W = 640;
const FRAME_H = 480;

/* 상태별로 쓸 수 있는 버튼 — UI 개발 가이드 2-3 표를 그대로 옮긴 것.
 * 표에 없는 버튼은 꺼진다. 예: 비상정지(estop) 상태에서는 비상정지를 다시 누를 수 없고
 * 물건 놓기와 정리 시작만 된다 */
const STATES = {
  idle:     { label: "대기",     color: "--st-idle",     buttons: ["start", "estop"] },
  cleaning: { label: "정리 중",  color: "--st-cleaning", buttons: ["pause", "stop", "estop"] },
  paused:   { label: "일시정지", color: "--st-paused",   buttons: ["resume", "stop", "estop"] },
  done:     { label: "정리 끝",  color: "--st-done",     buttons: ["start", "estop"] },
  estop:    { label: "비상정지", color: "--st-danger",   buttons: ["start", "release"] },
  error:    { label: "오류",     color: "--st-danger",   buttons: ["estop"] },
};

const STEPS = {
  detecting: "살펴보는 중",
  picking: "집는 중",
  carrying: "옮기는 중",
  returning: "돌아가는 중",
};

const ALL_BUTTONS = ["start", "pause", "resume", "stop", "estop", "release"];

/* ---------- 서버와 이야기하기 ---------- */

/** fetch에 시간 제한을 걸어서, 서버가 죽었을 때 화면이 영원히 기다리지 않게 한다 */
async function api(path, options = {}, timeoutMs = 2500) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { ...options, signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

const postCommand = (name) => api("/api/" + name, { method: "POST" });

/* ---------- 확인 창 ---------- */

/** window.confirm 대신 쓰는 확인 창.
 *  휴대폰에서 기본 confirm은 작고 글씨를 못 바꿔서 직접 만들었다 */
function ask(title, text, okLabel = "확인") {
  const dlg = document.getElementById("ask");
  if (!dlg || !dlg.showModal) return Promise.resolve(window.confirm(`${title}\n\n${text}`));

  dlg.querySelector(".ask-title").textContent = title;
  dlg.querySelector(".ask-text").textContent = text;
  const okBtn = dlg.querySelector(".ask-ok");
  okBtn.textContent = okLabel;

  return new Promise((resolve) => {
    const done = (answer) => {
      okBtn.onclick = null;
      dlg.querySelector(".ask-cancel").onclick = null;
      dlg.onclose = null;
      dlg.close();
      resolve(answer);
    };
    okBtn.onclick = () => done(true);
    dlg.querySelector(".ask-cancel").onclick = () => done(false);
    dlg.onclose = () => resolve(false);   // esc 키로 닫은 경우
    dlg.showModal();
    dlg.querySelector(".ask-cancel").focus();
  });
}

/* ---------- 메인 화면 ---------- */

/* 서버 문구의 조사 표기를 읽기 쉽게 바꾼다. 서버가 주는 오류 내용은 그대로 보존한다. */
function readable(text) {
  return String(text || "").replace(/([가-힣]+)을\(를\)/g, (_, word) =>
    word + ((word.charCodeAt(word.length - 1) - 0xac00) % 28 ? "을" : "를"));
}

function startMain() {
  const el = (id) => document.getElementById(id);
  const cams = { head: el("cam-head"), wrist: el("cam-wrist") };
  const stream = { head: {}, wrist: {} };
  let connected = false;
  let lastStatus = null;
  let healthy = 0;
  let misses = 0;        // 상태 확인이 연속으로 실패한 횟수
  let refreshing = false;
  let commandVersion = 0;
  let request = null;
  let waiting = null;
  let notifications = [];
  let notificationKey = "";
  let showAll = false;

  function feedback(text = "", bad = false) {
    el("command-msg").textContent = text;
    el("command-msg").hidden = !text;
    el("command-msg").classList.toggle("bad", bad);
  }

  function cameraNote(cam, text) {
    el(`note-${cam}`).textContent = text;
    el(`note-${cam}`).hidden = !text;
    cams[cam].closest(".cam-frame").classList.toggle("stale", !!text);
    if (cam === "head" && text) el("overlay").replaceChildren();
  }

  function dropStream(cam, text) {
    cams[cam].removeAttribute("src");
    stream[cam] = {};
    cameraNote(cam, text);
  }

  function reloadStream(cam) {
    dropStream(cam, "영상을 불러오고 있어요.");
    stream[cam].started = Date.now();
    cams[cam].src = `/video/${cam}?t=${Date.now()}`;
  }

  for (const cam of Object.keys(cams)) {
    cams[cam].addEventListener("error", () => {
      if (!cams[cam].getAttribute("src")) return;
      dropStream(cam, "영상을 받을 수 없어요. 다시 연결하고 있어요.");
      stream[cam].retryAt = Date.now() + 2000;
    });
    cams[cam].addEventListener("load", () => {
      if (connected && cams[cam].getAttribute("src")) cameraNote(cam, "");
    });
  }

  function checkStreams() {
    if (!connected || document.hidden || healthy < 2) return;
    for (const cam of Object.keys(cams)) {
      const meta = stream[cam];
      if (!cams[cam].getAttribute("src")) {
        if (!meta.retryAt || Date.now() >= meta.retryAt) reloadStream(cam);
      } else if (cams[cam].naturalWidth > 0) {
        // MJPEG는 응답이 끝나지 않아 load가 늦는 브라우저도 있다.
        cameraNote(cam, "");
      } else if (Date.now() - meta.started > 8000) {
        dropStream(cam, "영상을 받을 수 없어요. 다시 연결하고 있어요.");
        stream[cam].retryAt = Date.now() + 2000;
      }
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      for (const cam of Object.keys(cams)) dropStream(cam, "화면을 다시 열면 영상을 연결해요.");
      el("ask").close();
    } else {
      healthy = 0;
      refresh();
    }
  });
  window.addEventListener("pagehide", () => {
    for (const cam of Object.keys(cams)) dropStream(cam, "영상을 연결하고 있어요.");
  });

  function applyButtons() {
    const allowed = lastStatus && STATES[lastStatus.state]?.buttons || [];
    for (const name of ALL_BUTTONS) {
      // 다른 요청을 보내는 동안에도 비상정지는 바로 보낼 수 있다.
      const busy = request && (name !== "estop" || request.name === "estop");
      el(name).disabled = !connected || !allowed.includes(name) || !!busy;
      if (name === "release") el(name).hidden = !connected || !allowed.includes(name);
    }
  }

  function drawBoxes(s) {
    const overlay = el("overlay");
    overlay.replaceChildren();
    if (!connected || document.hidden || s.state !== "cleaning" ||
        !["detecting", "picking"].includes(s.step) ||
        cams.head.closest(".cam-frame").classList.contains("stale")) return;
    for (const d of s.detected || []) {
      if (!Array.isArray(d.box) || d.box.length !== 4 || !d.box.every(Number.isFinite)) continue;
      const [x1, y1, x2, y2] = d.box;
      const box = document.createElement("div");
      box.className = "det";
      box.style.cssText = `left:${x1 / FRAME_W * 100}%;top:${y1 / FRAME_H * 100}%;width:${(x2 - x1) / FRAME_W * 100}%;height:${(y2 - y1) / FRAME_H * 100}%`;
      const label = document.createElement("span");
      label.textContent = (OBJECTS[d.object] || "물건") + (Number.isFinite(d.conf) ? ` ${Math.round(d.conf * 100)}%` : "");
      box.append(label);
      overlay.append(box);
    }
  }

  function notificationList(target, items) {
    const fragment = document.createDocumentFragment();
    for (const n of items) {
      const li = document.createElement("li");
      li.className = ["warn", "error"].includes(n.level) ? n.level : "info";
      const time = document.createElement("time");
      time.textContent = n.time || "";
      const text = document.createElement("span");
      const label = n.level === "error" ? "오류 · " : n.level === "warn" ? "주의 · " : "";
      text.textContent = label + readable(n.text);
      li.append(time, text);
      fragment.append(li);
    }
    const top = target.scrollTop;
    target.replaceChildren(fragment);
    target.scrollTop = top;
  }

  function renderNotifications() {
    const newest = [...notifications].reverse();
    notificationList(el("notis"), showAll ? newest : newest.slice(0, 8));
    const important = newest.filter(n => ["warn", "error"].includes(n.level));
    important.sort((a, b) => Number(b.level === "error") - Number(a.level === "error"));
    el("important-notis").hidden = !important.length;
    el("important-summary").textContent = `주의·오류 ${important.length}개 확인 (이전 알림 포함)`;
    notificationList(el("important-list"), important);
    el("important-preview").hidden = !important.length;
    el("important-preview").textContent = important.length
      ? `받은 ${important[0].level === "error" ? "오류" : "주의"} · ${important[0].time || ""} ${readable(important[0].text)}` : "";
    el("notis-caption").textContent = !newest.length ? "아직 알림이 없어요."
      : `받은 알림 ${newest.length}개 중 ${showAll ? newest.length : Math.min(8, newest.length)}개 · 최근 순`;
    el("notis-toggle").hidden = newest.length <= 8;
    el("notis-toggle").textContent = showAll ? "최근 8개만 보기" : `전체 ${newest.length}개 보기`;
    el("notis-toggle").setAttribute("aria-expanded", String(showAll));
  }
  el("notis-toggle").onclick = () => { showAll = !showAll; renderNotifications(); };

  function renderWaiting(s) {
    if (!waiting || !waiting.accepted) return;
    const expected = { start: ["cleaning", "done"], pause: ["paused"], resume: ["cleaning", "done"], stop: ["idle"], estop: ["estop"] };
    if (expected[waiting.name]?.includes(s.state)) {
      waiting = null;
      feedback();
      return;
    }
    if (waiting.name === "pause") {
      if (s.state !== "cleaning") { waiting = null; feedback(); }
      else feedback("일시정지를 요청했어요. 지금 물건까지 정리하고 멈출게요. 아직 움직이고 있어요.");
    } else if (Date.now() - waiting.at > 4000) {
      const action = waiting.name === "estop" ? "비상정지" : "동작";
      feedback(`${action} 요청은 보냈지만 바뀐 상태를 확인하지 못했어요. 로봇에 가까이 가지 말고 현재 상태를 확인해 주세요.`, true);
    }
  }

  function render(s) {
    lastStatus = s;
    const info = STATES[s.state] || STATES.error;
    const known = !!STATES[s.state];
    document.documentElement.style.setProperty("--state", `var(${info.color})`);
    el("badge").closest(".status").dataset.state = known ? s.state : "error";
    el("badge").textContent = info.label;
    const p = s.progress || { done: 0, failed: 0, remaining: 0 };
    const total = p.done + p.failed + p.remaining;
    el("message").textContent = known ? readable(s.message) : "로봇 상태를 확인할 수 없어요.";
    const guidance = {
      idle: "주변에 손이나 장애물이 없는지 확인한 뒤 ‘정리 시작’을 누르세요.",
      cleaning: "로봇이 움직이고 있어요. 팔 주변을 비워 주세요.",
      paused: "지금은 멈춰 있어요. 이어서 하려면 ‘계속’, 끝내려면 ‘중지’를 누르세요.",
      done: p.failed ? `${p.failed}개는 로봇이 정리하지 못했어요. 남겨 둔 물건을 직접 정리해 주세요.` : "선택한 물건을 모두 정리했어요. 책상을 확인해 주세요.",
      estop: "팔은 그 자리에 멈춰 있어요. 들고 있는 물건이 있으면 아래를 비우고 ‘물건 놓기’를 누르세요. 다시 시작하기 전에 주변을 확인해 주세요.",
      error: "로봇과 카메라 연결을 확인해 주세요. 위험하면 비상정지를 누르세요.",
    };
    el("next-action").textContent = guidance[s.state] || "로봇에 가까이 가지 말고 연결을 확인해 주세요.";
    if (s.state === "done") el("message").textContent = "정리를 마쳤어요";
    el("step").hidden = s.state !== "cleaning" || !STEPS[s.step];
    el("step").textContent = STEPS[s.step] || "";
    el("attempt").hidden = s.state !== "cleaning" || !(s.current?.attempt > 1);
    el("attempt").textContent = s.current?.attempt > 1 ? `${s.current.attempt}번째 시도` : "";
    for (const key of ["done", "failed", "remaining"]) el(key).textContent = known ? `${p[key]}개` : "—";
    const percent = total ? Math.round((p.done + p.failed) / total * 100) : 0;
    el("bar-fill").style.width = `${percent}%`;
    el("progress").setAttribute("aria-valuenow", String(percent));
    el("progress").setAttribute("aria-valuetext", `${p.done}개 정리 완료, ${p.failed}개 직접 정리, ${p.remaining}개 정리할 물건`);
    el("progress-note").textContent = !total ? "정리를 시작하면 물건 수를 알려 드려요."
      : s.state === "idle" ? "중지하기 전의 결과예요. 새로 시작하면 다시 셉니다."
      : s.state === "done" ? `이번 정리 결과 · 총 ${total}개 중 ${p.done}개 완료`
      : `이번 정리 · 총 ${total}개 / ‘직접 정리’는 로봇이 남겨 둔 물건이에요.`;
    el("controls-hint").textContent = s.state === "estop"
      ? "‘정리 시작’을 누르면 주변이 안전한지 한 번 더 확인해요."
      : "일시정지는 지금 물건까지 마친 뒤 멈춰요. 중지는 물건을 놓고 처음 자세로 돌아가요.";
    el("emergency-hint").textContent = s.state === "estop" ? "비상정지됨 · 다시 시작하기 전에 주변을 확인하세요" : "위험하면 바로 누르세요";
    if (!["estop"].includes(s.state) && el("ask").open) el("ask").close();
    renderWaiting(s);
    applyButtons();
    checkStreams();
    drawBoxes(s);
    const key = JSON.stringify(s.notifications || []);
    if (key !== notificationKey) {
      notificationKey = key;
      notifications = s.notifications || [];
      renderNotifications();
    }
  }

  function setOffline() {
    connected = false;
    healthy = 0;
    misses = 0;
    waiting = null;
    el("conn").className = "conn off";
    el("conn").textContent = "연결 끊김";
    el("offline").classList.add("show");
    document.documentElement.style.setProperty("--state", "var(--st-danger)");
    el("badge").closest(".status").dataset.state = "offline";
    el("badge").textContent = "상태 확인 불가";
    el("message").textContent = "지금 로봇이 멈췄는지 알 수 없어요.";
    el("next-action").textContent = "이 화면에서 조작할 수 없어요. 전원과 와이파이를 확인해 주세요.";
    el("step").hidden = true;
    el("attempt").hidden = true;
    for (const key of ["done", "failed", "remaining"]) el(key).textContent = "—";
    el("bar-fill").style.width = "0%";
    el("progress").removeAttribute("aria-valuenow");
    el("progress").setAttribute("aria-valuetext", "연결이 끊겨 진행 상황을 알 수 없어요");
    el("progress-note").textContent = "연결되면 최신 상태로 바뀌어요. 아래 알림은 끊기기 전 내용이에요.";
    el("controls-hint").textContent = "자동으로 다시 연결하고 있어요.";
    el("emergency-hint").textContent = "연결이 끊겨 비상정지도 보낼 수 없어요";
    el("ask").close();
    for (const cam of Object.keys(cams)) dropStream(cam, "연결 끊김 · 지금 영상을 볼 수 없어요.");
    applyButtons();
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    const version = commandVersion;
    try {
      const s = await api("/api/status");
      if (version !== commandVersion) return;
      connected = true;
      healthy++;
      misses = 0;
      el("conn").className = "conn";
      el("conn").textContent = "연결됨";
      el("offline").classList.remove("show");
      render(s);
    } catch {
      // 한 번 늦은 응답으로 영상을 끊었다 붙였다 하지 않게, 두 번 연속 실패해야 끊김으로 본다.
      // (명령 전송이 실패한 경우는 run()에서 바로 끊김 처리한다)
      if (version === commandVersion && ++misses >= 2) setOffline();
    } finally {
      refreshing = false;
    }
  }

  const sending = {
    start: "정리 시작을 요청하고 있어요.", pause: "일시정지를 요청하고 있어요. 아직 움직일 수 있어요.",
    resume: "계속 정리하도록 요청하고 있어요.", stop: "중지를 요청하고 있어요. 멈춘 상태를 확인할게요.",
    estop: "비상정지를 요청하고 있어요. 멈춘 상태를 확인할게요.", release: "물건 놓기를 요청하고 있어요.",
  };
  async function run(name) {
    if (el(name).disabled) return;
    const version = ++commandVersion;
    request = { name, version };
    waiting = null;
    feedback(sending[name]);
    applyButtons();
    try {
      const res = await postCommand(name);
      if (version !== commandVersion) return;
      if (!res?.ok) feedback(readable(res?.error) || "로봇이 요청을 받아들이지 않았어요. 현재 상태를 확인해 주세요.", true);
      else if (name === "release") feedback("물건 놓기 요청을 보냈어요. 비상정지는 유지돼요. 주변을 확인한 뒤 다시 시작하세요.");
      else waiting = { name, accepted: true, at: Date.now() };
    } catch {
      if (version !== commandVersion) return;
      feedback("요청이 전달됐는지 확인하지 못했어요. 연결이 돌아오면 현재 상태를 확인해 주세요.", true);
      setOffline();
    } finally {
      if (version === commandVersion) { request = null; applyButtons(); refresh(); }
    }
  }

  for (const name of ["pause", "resume", "stop", "estop"]) el(name).onclick = () => run(name);
  el("start").onclick = async () => {
    if (lastStatus?.state === "estop") {
      const yes = await ask("다시 정리할까요?", "로봇 팔이 다시 움직여요. 주변에 사람이나 장애물이 없는지, 들고 있던 물건은 안전하게 놓았는지 확인해 주세요.", "주변 확인했어요 · 시작");
      if (!yes || !connected || lastStatus?.state !== "estop") return;
    }
    run("start");
  };
  el("release").onclick = async () => {
    const yes = await ask("물건을 놓을까요?", "팔은 움직이지 않고 손만 열려요. 들고 있는 물건이 그 자리에서 떨어져요. 아래에 손이나 깨질 물건이 없는지 확인해 주세요.", "아래 확인했어요 · 놓기");
    if (yes && connected && lastStatus?.state === "estop") run("release");
  };

  setInterval(refresh, 500);
  refresh();
}

/* ---------- 설정 화면 ---------- */
function startSettings() {
  const el = id => document.getElementById(id);
  const form = el("form");
  let state = null;
  let connected = false;
  let loaded = false;
  let loading = false;
  let watching = false;
  let saving = false;
  let estopping = false;
  let estopRequested = 0;
  let estopError = "";
  let saved = "";
  let dirty = false;

  el("bins").innerHTML = Object.keys(OBJECTS).map(k => `<tr><td>${OBJECTS[k]}</td><td>${BINS[k]}</td></tr>`).join("");
  el("objects").innerHTML = Object.keys(OBJECTS).map(k =>
    `<label class="check"><input type="checkbox" name="obj" value="${k}" disabled><span>${OBJECTS[k]}</span><small>${BINS[k]}</small></label>`).join("");

  function fill(s) {
    for (const box of form.querySelectorAll('input[name="obj"]')) box.checked = !!s.objects?.[box.value];
    form.querySelector(`input[name="speed"][value="${s.speed === "slow" ? "slow" : "normal"}"]`).checked = true;
    el("retries").value = String(s.max_retries ?? 1);
  }
  function collect() {
    const objects = {};
    for (const box of form.querySelectorAll('input[name="obj"]')) objects[box.value] = box.checked;
    return { objects, speed: form.querySelector('input[name="speed"]:checked')?.value || "normal", max_retries: Number(el("retries").value) };
  }
  function say(text, kind = "") {
    el("save-msg").textContent = text;
    el("save-msg").className = "save-msg " + kind;
  }
  function lock() {
    let reason = "";
    if (!connected) reason = state === null ? "로봇 상태와 저장된 설정을 확인하고 있어요." : "로봇과 연결이 끊겨 설정을 바꿀 수 없어요. 자동으로 다시 연결할게요.";
    else if (!loaded) reason = "저장된 설정을 불러오고 있어요. 읽기 전에는 바꿀 수 없어요.";
    else if (state === "cleaning") reason = "정리 중에는 설정을 바꿀 수 없어요. 정리가 끝나거나 정리 화면에서 ‘중지’를 누른 뒤 바꿔 주세요.";
    else if (state === "paused") reason = "일시정지 중에도 설정은 잠겨 있어요. 정리 화면에서 ‘중지’를 누르면 바꿀 수 있어요.";
    else if (!STATES[state]) reason = "로봇 상태를 확인할 수 없어 설정을 잠갔어요.";
    el("locked").textContent = reason;
    el("locked").classList.toggle("show", !!reason);
    for (const input of form.querySelectorAll("input, select")) input.disabled = !!reason || saving;
    el("save").disabled = !!reason || saving || !dirty;
    el("save").textContent = saving ? "저장 중…" : "설정 저장";
    form.setAttribute("aria-busy", String(saving || !loaded));
    el("estop").disabled = !connected || estopping || !STATES[state]?.buttons.includes("estop");
    if (state === "estop") { estopRequested = 0; estopError = ""; }
    el("emergency-hint").textContent = !connected ? "연결을 확인해야 비상정지를 보낼 수 있어요"
      : state === "estop" ? "비상정지됨 · 물건 놓기와 재시작은 정리 화면에서 해 주세요"
      : estopError ? estopError
      : estopRequested ? (Date.now() - estopRequested > 4000 ? "비상정지를 요청했지만 멈춤을 확인하지 못했어요" : "비상정지를 요청했어요. 멈춘 상태를 확인할게요.")
      : "설정 중에도 위험하면 바로 누르세요";
  }
  form.addEventListener("change", () => {
    dirty = JSON.stringify(collect()) !== saved;
    say(dirty ? "아직 저장하지 않은 변경이 있어요." : "저장된 설정과 같아요.");
    lock();
  });

  async function load() {
    if (loading || loaded) return;
    loading = true;
    try {
      fill(await api("/api/settings"));
      loaded = true;
      saved = JSON.stringify(collect());
      dirty = false;
      say("저장된 설정을 불러왔어요.");
    } catch {
      say("설정을 읽지 못했어요. 자동으로 다시 불러올게요.", "bad");
    } finally { loading = false; lock(); }
  }
  async function watchState() {
    if (watching) return;
    watching = true;
    try {
      const s = await api("/api/status");
      state = s.state;
      connected = true;
      el("conn").className = "conn";
      el("conn").textContent = "연결됨";
      if (!loaded) await load();
    } catch {
      connected = false;
      if (state === null) state = "offline";
      el("conn").className = "conn off";
      el("conn").textContent = "연결 끊김";
    } finally { watching = false; lock(); }
  }

  el("save").onclick = async () => {
    if (el("save").disabled) return;
    const draft = collect();
    if (!Object.values(draft.objects).some(Boolean)) {
      say("정리할 물건을 하나 이상 선택해 주세요.", "bad");
      return;
    }
    saving = true;
    lock();
    say("저장하고 있어요.");
    try {
      const res = await api("/api/settings", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft),
      });
      if (!res?.ok) {
        say(readable(res?.error) || "저장하지 못했어요. 로봇이 정리 중인지 확인해 주세요. 바꾼 값은 그대로 있어요.", "bad");
      } else {
        // 성공 응답 뒤 실제 저장값까지 읽고 나서 성공을 표시한다.
        const actual = await api("/api/settings");
        fill(actual);
        saved = JSON.stringify(collect());
        dirty = false;
        say("설정을 저장했어요. 다음 정리부터 적용돼요.", "ok");
      }
    } catch {
      say("저장 여부를 확인하지 못했어요. 연결이 돌아오면 값을 확인하고 다시 저장해 주세요.", "bad");
    } finally { saving = false; lock(); watchState(); }
  };

  el("back").onclick = async event => {
    if (!dirty && !saving) return;
    event.preventDefault();
    if (saving) { say("저장 중이에요. 결과를 확인한 뒤 돌아가 주세요."); return; }
    if (await ask("저장하지 않고 나갈까요?", "바꾼 설정이 아직 저장되지 않았어요. 나가면 변경한 내용은 사라져요.", "저장하지 않고 나가기")) {
      dirty = false;
      location.href = el("back").href;
    }
  };
  el("estop").onclick = async () => {
    if (el("estop").disabled) return;
    estopping = true;
    estopRequested = Date.now();
    estopError = "";
    lock();
    try {
      const res = await postCommand("estop");
      if (!res?.ok) estopError = "비상정지 요청이 거부됐어요. 정리 화면에서 상태를 확인해 주세요.";
    } catch {
      connected = false;
      el("conn").className = "conn off";
      el("conn").textContent = "연결 끊김";
    } finally { estopping = false; lock(); watchState(); }
  };
  window.addEventListener("beforeunload", event => {
    if (dirty || saving) { event.preventDefault(); event.returnValue = ""; }
  });
  lock();
  watchState();
  setInterval(watchState, 1000);
}
