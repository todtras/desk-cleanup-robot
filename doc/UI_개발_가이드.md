# 정리 로봇 사용자 화면(UI) 개발 가이드

대상: 정의찬, 지동현 (비대면, 2명 협업) · 기간: 5~8주차 개발, **9주차 출근일(11/27) 실제 로봇과 통합**
질문: 단톡방. 에러는 **메시지 전체를 복사해서** 붙이기 (마지막 줄만 보내면 원인을 못 찾음)

---

## 0. 한 줄 요약

> 이 로봇을 **제품으로 판다고 생각하고**, 로봇을 전혀 모르는 사람이 쓸 **조작 화면**을 만든다.
> 노트북 브라우저와 **휴대폰**에서 실시간 화면을 보고, 버튼으로 **정리 시작 / 일시정지 / 중지 / 비상정지**, 설정을 바꿀 수 있게.
> 로봇은 사무실에만 있으니, **녹화 영상으로 로봇을 흉내 내는 가짜 로봇**으로 개발하고, 마지막 주에 팀장이 진짜 로봇에 연결한다.

완성되면 이런 모습 (휴대폰에서도 같은 화면):
```
┌──────────────────────────────────────────────┐
│ 책상 정리 로봇                  ● 연결됨  [설정] │
├──────────────────────────────────────────────┤
│ ┌───────────────────┐ ┌───────────────────┐  │
│ │ 책상 전체 (실시간)  │ │ 로봇 손 (실시간)    │  │
│ │  [펜 0.82] 박스     │ │                   │  │
│ └───────────────────┘ └───────────────────┘  │
│                                              │
│  🟢 펜을 필기구 수거함으로 옮기는 중이에요       │
│  ████████░░░░  정리 3 · 실패 1 · 남음 1        │
│                                              │
│  [ 정리 시작 ] [ 일시정지 ] [ 중지 ]  [비상정지] │
├──────────────────────────────────────────────┤
│ 알림                                          │
│ 14:02 종이를 집지 못해 건너뛰었어요. 직접 정리해 주세요 │
│ 14:01 정리를 시작했어요                         │
└──────────────────────────────────────────────┘
```

---

## 1. 프로젝트 3분 이해 (처음이면 꼭 읽기)

**로봇이 하는 일**: 책상 위 물건 5종을 알아보고, 하나씩 집어서 종류별 수거함에 넣는다.

| 물건 | 수거함 |
|---|---|
| 펜, 지우개 | 필기구 |
| 테이프 | 사무용품 |
| 물병, 구겨진 종이 | 쓰레기 |

**한 번 정리할 때 로봇 안에서 일어나는 일**
```
① 책상 전체 카메라(head)로 사진 한 장 → 물건 인식 AI(YOLO)가 "펜이 여기 있다"
② 물건별로 학습한 동작 AI(ACT)가 팔을 움직여 집어서 살짝 들어 올림
③ 쥔 걸 확인하면 미리 저장한 자세로 수거함 위까지 이동 → 그리퍼를 열어 놓기
④ 처음 자세(home)로 돌아옴 → ①부터 반복, 물건이 없으면 끝
```

**용어** (화면에는 이런 말을 쓰지 않는다. 너희가 코드 읽을 때만 필요)
| 용어 | 뜻 |
|---|---|
| head 카메라 / wrist 카메라 | 책상 전체를 보는 카메라 / 로봇 손끝에 달린 카메라 |
| YOLO | 사진에서 물건 종류와 위치(박스)를 찾는 AI. 신뢰도(0~1)가 같이 나옴 |
| ACT, 정책 | 사람이 직접 로봇을 조종한 기록(시연)을 보고 따라 하게 학습한 AI |
| 에피소드 | 시연 한 번 (한 번 집는 기록). 영상 + 관절값 |
| 그리퍼 | 로봇 손 (집게). 값이 클수록 벌어짐 |
| home | 정리 전후에 돌아가는 기본 자세 |

---

## 2. 무엇을 만드나 (기능 명세)

### 2-1. 사용자 시나리오 (이대로 쓸 수 있으면 성공)
1. 사무실 직원이 퇴근 전 휴대폰으로 `http://<노트북 주소>:8000` 접속
2. 실시간 화면으로 책상을 보고 **[정리 시작]**
3. "펜을 필기구 수거함으로 옮기는 중이에요"처럼 지금 뭘 하는지 보인다
4. 못 집은 물건이 있으면 알림: "종이를 집지 못해 건너뛰었어요. 직접 정리해 주세요"
5. 회의 들어가야 하면 **[일시정지]** → 나중에 **[계속]**
6. 사람이 로봇 근처에 손을 넣는 등 위험하면 **[비상정지]**
7. 끝나면 "정리 끝! 4개 정리, 1개 실패"

### 2-2. 화면 3개

**① 메인 화면** (`index.html`)
| 요소 | 내용 |
|---|---|
| 실시간 화면 2개 | 책상 전체 + 로봇 손. 인식한 물건에 박스와 이름 |
| 상태 문구 | 지금 하는 일을 쉬운 말로 (Cleaner가 `message`로 줌) |
| 상태 색 | 대기=회색, 정리 중=초록, 일시정지=노랑, 비상정지·오류=빨강 |
| 진행 | 정리 / 실패 / 남음 개수 + 진행 막대 |
| 버튼 | 정리 시작, 일시정지, 계속, 중지, 비상정지 (2-3 규칙대로 켜고 끄기) |
| 알림 목록 | 최근 알림 5~10개, 경고는 눈에 띄게 |
| 연결 표시 | 서버와 연결이 끊기면 "로봇과 연결이 끊겼어요" (화면이 멈춘 채 속이지 않기) |

**② 설정 화면** (`settings.html`) — 정리 중에는 저장 못 함
| 설정 | 값 | 설명 |
|---|---|---|
| 정리할 물건 | 5종 체크박스 | 끈 물건은 건드리지 않음 |
| 속도 | 보통 / 느리게 | 처음 쓰거나 주변에 사람이 있을 때 느리게 |
| 다시 시도 횟수 | 0~3 | 못 집으면 몇 번 더 해볼지 |
| 수거함 안내 | 물건 → 수거함 표 (보기만) | 사용자가 수거함 위치를 헷갈리지 않게 |
| (선택) 고급 설정 | 숨김 메뉴 | 팀장용. 9주차에 같이 정함 |

**③ 기록 화면** (`history.html`)
- 날짜별 정리 기록: 몇 번 정리했고, 물건별 성공·실패 개수
- 자주 실패하는 물건 표시 ("종이를 자주 놓쳐요")

### 2-3. 상태와 버튼 규칙

Cleaner의 상태(`state`):
| state | 뜻 | 정리 시작 | 일시정지 | 계속 | 중지 | 비상정지 |
|---|---|---|---|---|---|---|
| `idle` | 대기 | ✅ | | | | ✅ |
| `cleaning` | 정리 중 | | ✅ | | ✅ | ✅ |
| `paused` | 일시정지 | | | ✅ | ✅ | ✅ |
| `done` | 정리 끝 | ✅ | | | | ✅ |
| `estop` | 비상정지됨 | ✅ (확인 후 다시 시작) | | | | |
| `error` | 오류 (로봇·카메라 연결 끊김 등) | | | | | ✅ |

정리 중 세부 단계(`step`): `detecting`(살펴보는 중), `picking`(집는 중), `carrying`(옮기는 중), `returning`(돌아가는 중)

**버튼 동작의 약속** (로봇 안전 때문에 이렇게 정함)
- **일시정지**: 지금 물건은 **마저 정리하고** home에서 멈춘다 (물건을 든 채 공중에서 멈추면 떨어뜨림). 그래서 누른 직후 "지금 물건까지 정리하고 멈출게요"를 보여준다
- **중지**: 지금 시도를 그만두고 그리퍼를 열고 home으로 → `idle`
- **비상정지**: **그 자리에서 즉시** 멈춤. 확인 창 없이 바로 (위급할 때 누르는 버튼). 크고 빨갛게, 항상 보이는 곳에

### 2-4. 문구 원칙
- 로봇을 모르는 사람이 읽는다 → "ACT", "정책", "에피소드", "YOLO", "체크포인트" 금지
- 무엇을 하는 중인지 + 사용자가 할 일이 있으면 그것까지: "종이를 집지 못해 건너뛰었어요. **직접 정리해 주세요**"

---

## 3. 구조

```
[브라우저: 노트북 / 휴대폰]  ← HTML·CSS·JS (B 담당)
        │  0.5초마다 상태 묻기, 버튼 → 명령, <img>로 실시간 화면
        ▼
[server.py: 웹 서버 (FastAPI)]  (A 담당)
        │  Cleaner의 메서드만 부름
        ▼
[Cleaner: 로봇 두뇌]
   ├ FakeCleaner  ← 지금: 녹화 영상으로 흉내 (A 담당, 시작 코드 제공)
   └ RealCleaner  ← 9주차: 진짜 로봇·카메라·AI (팀장 담당)
```

**왜 웹 방식인가**: 휴대폰에서 원격으로 쓰려면 어차피 웹이 필요하다. 노트북에서도 브라우저로 같은 화면을 쓰면 화면을 한 번만 만들면 된다. 앱 설치도 필요 없다.

### 3-1. 서버 API (A와 B의 약속 — 바꿀 때는 둘이 상의)

| 요청 | 하는 일 | 응답 |
|---|---|---|
| `GET /api/status` | 지금 상태 | 아래 JSON |
| `POST /api/start` `/pause` `/resume` `/stop` `/estop` | 버튼 | `{"ok": true}` (안 되는 상황이면 `false`) |
| `GET /api/settings` | 설정 읽기 | `{"objects": {...}, "speed": "normal", "max_retries": 1}` |
| `PUT /api/settings` | 설정 저장 (바꿀 항목만 보내도 됨) | `{"ok": true}` (정리 중이면 `false`) |
| `GET /api/history` | 기록 (6주차에 A가 추가) | 2-2 ③에 필요한 데이터 |
| `GET /video/head`, `/video/wrist` | 실시간 화면 | `<img src="/video/head">`로 바로 보임 |

`/api/status` 예:
```json
{
  "state": "cleaning",
  "step": "carrying",
  "current": {"object": "pen", "bin": "필기구", "attempt": 1},
  "message": "펜을(를) 필기구 수거함으로 옮기는 중",
  "detected": [{"object": "pen", "conf": 0.82, "box": [305, 241, 380, 290]}],
  "progress": {"done": 2, "failed": 1, "remaining": 2},
  "notifications": [{"time": "14:02:11", "level": "warn", "text": "종이를 집지 못해 건너뛰었어요. 직접 정리해 주세요"}]
}
```
물건 이름은 영어 키(`tape, bottle, pen, eraser, paper`)로 온다. 화면에 보일 때는 한글로 바꿔서 (`cleaner.py`의 `OBJECTS` 표).

---

## 4. 역할 분담

| | A: 서버 · 로봇 두뇌 | B: 화면 |
|---|---|---|
| 파일 | `dev/app/server.py`, `dev/app/cleaner.py` | `dev/app/static/` 안의 `index.html`, `settings.html`, `history.html`, `style.css`, `app.js` |
| 주요 일 | API, 가짜 로봇 다듬기, 기록 저장, 원격 접속·보안, 오류 상황 흉내 | 화면 3개 디자인, 버튼 규칙, 휴대폰 화면, 연결 끊김 표시 |
| 필요한 것 | Python | HTML/CSS/JavaScript (`fetch`) |

- 누가 A/B를 할지는 둘이 정한다. **1일차(5장)는 둘 다 똑같이 따라 한다** (전체 흐름을 둘 다 알아야 함)
- 서로의 파일은 고치지 않는다. 고쳐야 하면 상대에게 말하고 상대가 고친다
- API(3-1)를 바꾸면 반드시 둘이 같이 PR 확인

---

## 5. 1일차: 따라 하기 (둘 다)

**집에서 개인 노트북으로 개발하면 된다.** 로봇, 카메라, 회사 네트워크, GPU 서버는 전혀 필요 없다. 필요한 건 아래 세 가지뿐이다.
- 레포 접근 권한 (GitHub 아이디를 팀장에게 알려주면 초대)
- 레포에 들어 있는 가짜 로봇 데이터 `dev/ui_pack.zip` (clone하면 같이 받아짐)
- Python이 되는 노트북 (윈도우 기준으로 적었고, 맥·리눅스는 `activate` 명령만 다름)

### 5-1. 설치 (윈도우 기준, 한 번만)
1. Python **3.10** 설치 (python.org, 설치할 때 "Add python.exe to PATH" 체크)
2. Git 설치 후 레포 받기
   ```bash
   git clone <팀장이 알려준 레포 주소>
   cd 26_2_intern/dev
   ```
3. 가상환경 만들고 패키지 설치 (로봇·AI 패키지는 필요 없음)
   ```bash
   python -m venv .venv-ui
   .venv-ui\Scripts\activate
   pip install fastapi==0.115.12 uvicorn==0.34.2 opencv-python-headless
   ```
   이후 작업할 때마다 `dev` 폴더에서 `.venv-ui\Scripts\activate` 먼저. (맥·리눅스: `source .venv-ui/bin/activate`)
4. **가짜 로봇 데이터 풀기**: 레포의 `dev/ui_pack.zip`(14MB)을 `dev/outputs/` 폴더에 풀어서 `dev/outputs/ui_pack/`이 되게 둔다
   ```bash
   python -c "import shutil; shutil.unpack_archive('ui_pack.zip', 'outputs')"
   ```
   ```
   dev/outputs/ui_pack/clips.json         ← 영상 목록 (물건, 박스 위치, 길이)
   dev/outputs/ui_pack/clips/pen_0_head.mp4, pen_0_wrist.mp4 ...   ← 물건 5종 × 4개 시연 영상
   ```

### 5-2. 시작 코드 3개 만들기
아래 3개 파일을 **그대로** 만든다. 팀장 노트북에서 실제로 돌려서 확인한 코드다 (정리 시작 → 일시정지 → 계속 → 끝 → 중지 → 비상정지까지 자동 시험 통과, 브라우저에서 실시간 화면 확인).

```
dev/app/__init__.py          ← 빈 파일
dev/app/cleaner.py
dev/app/server.py
dev/app/static/index.html
```

<details>
<summary><b>dev/app/cleaner.py</b> (로봇 두뇌 — 가짜)</summary>

```python
"""정리 로봇 '두뇌' 쪽. 화면(server.py)은 이 파일의 Cleaner만 쓴다.
지금은 녹화 영상으로 흉내 내는 FakeCleaner. 나중에 팀장이 같은 메서드를 가진 RealCleaner(진짜 로봇)를 만든다."""
import json
import random
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

PACK = Path(__file__).resolve().parent.parent / "outputs" / "ui_pack"  # 팀장이 준 가짜 로봇 데이터
SETTINGS_FILE = Path(__file__).resolve().parent.parent / "configs" / "app_settings.json"

OBJECTS = {"tape": "테이프", "bottle": "물병", "pen": "펜", "eraser": "지우개", "paper": "종이"}
BINS = {"tape": "사무용품", "bottle": "쓰레기", "pen": "필기구", "eraser": "필기구", "paper": "쓰레기"}
DEFAULT_SETTINGS = {"objects": {k: True for k in OBJECTS}, "speed": "normal", "max_retries": 1}


def load_settings():
    if SETTINGS_FILE.exists():
        return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    return dict(DEFAULT_SETTINGS)


class FakeCleaner:
    def __init__(self):
        self.clips = json.loads((PACK / "clips.json").read_text(encoding="utf-8"))
        self.settings = load_settings()
        self.lock = threading.Lock()
        self.cmd = None  # 화면이 누른 버튼: "pause" / "stop" / "estop"
        self.frames = {"head": None, "wrist": None}  # 지금 화면 (JPEG bytes)
        self.st = {"state": "idle", "step": None, "current": None, "message": "대기 중이에요",
                   "detected": [], "progress": {"done": 0, "failed": 0, "remaining": 0}, "notifications": []}
        self._show_still()

    # ---------- 화면이 부르는 메서드 (모두 바로 반환) ----------
    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.st))  # 복사본

    def frame(self, cam):
        return self.frames[cam]

    def start(self):
        if self.st["state"] in ("cleaning", "paused"):
            return False
        self.cmd = None
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def pause(self):
        """지금 물건은 마저 정리하고 멈춤 (물건을 든 채 공중에서 멈추면 위험)"""
        if self.st["state"] == "cleaning":
            self.cmd = "pause"
            self._set(message="지금 물건까지 정리하고 멈출게요")

    def resume(self):
        if self.st["state"] == "paused":
            self.cmd = None

    def stop(self):
        self.cmd = "stop"

    def estop(self):
        self.cmd = "estop"

    def get_settings(self):
        return self.settings

    def set_settings(self, new):
        if self.st["state"] in ("cleaning", "paused"):
            return False  # 정리 중에는 못 바꿈
        self.settings = {**self.settings, **new}
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=1), encoding="utf-8")
        return True

    # ---------- 내부 ----------
    def _set(self, **kw):
        with self.lock:
            self.st.update(kw)

    def _notify(self, text, level="info"):
        with self.lock:
            self.st["notifications"].append({"time": datetime.now().strftime("%H:%M:%S"), "level": level, "text": text})
            self.st["notifications"] = self.st["notifications"][-50:]

    def _show_still(self, clip=None, boxes=()):
        clip = clip or self.clips[0]
        for cam in ("head", "wrist"):
            ok, img = cv2.VideoCapture(str(PACK / clip[cam])).read()
            if cam == "head":
                for b in boxes:
                    cv2.rectangle(img, tuple(b["box"][:2]), tuple(b["box"][2:]), (0, 200, 0), 2)
                    cv2.putText(img, f'{b["object"]} {b["conf"]:.2f}', (b["box"][0], b["box"][1] - 6),  # OpenCV 글씨는 영어만
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
            self.frames[cam] = cv2.imencode(".jpg", img)[1].tobytes()

    def _wait_if_paused(self):
        while self.cmd == "pause":
            self._set(state="paused", message="일시정지 — 계속하려면 '계속'을 누르세요")
            time.sleep(0.2)
        if self.cmd is None:
            self._set(state="cleaning")

    def _play(self, clip, until=None):
        """영상 재생 (= 로봇이 움직이는 중). 중지 버튼이면 False"""
        caps = {c: cv2.VideoCapture(str(PACK / clip[c])) for c in ("head", "wrist")}
        speed = 1.0 if self.settings["speed"] == "normal" else 0.6
        n = 0
        while until is None or n < until * 15:
            if self.cmd in ("stop", "estop"):
                return False
            imgs = {c: cap.read() for c, cap in caps.items()}
            if not all(ok for ok, _ in imgs.values()):
                break
            for c, (_, img) in imgs.items():
                self.frames[c] = cv2.imencode(".jpg", img)[1].tobytes()
            n += 1
            time.sleep(1 / 15 / speed)
        return True

    def _run(self):
        todo = [o for o, on in self.settings["objects"].items() if on]
        random.shuffle(todo)
        self._set(state="cleaning", step="detecting", current=None, message="책상을 살펴보는 중이에요",
                  progress={"done": 0, "failed": 0, "remaining": len(todo)})
        self._notify("정리를 시작했어요")
        done = failed = 0
        for obj in todo:
            self._wait_if_paused()
            clip = random.choice([c for c in self.clips if c["object"] == obj])
            det = [{"object": obj, "conf": round(random.uniform(0.6, 0.95), 2), "box": clip["box"]}]
            self._set(step="detecting", detected=det, message=f"{OBJECTS[obj]}을(를) 찾았어요")
            self._show_still(clip, det)
            time.sleep(1.0)
            ok = False
            for attempt in range(1 + self.settings["max_retries"]):
                self._set(step="picking", current={"object": obj, "bin": BINS[obj], "attempt": attempt + 1},
                          message=f"{OBJECTS[obj]} 집는 중 ({attempt + 1}번째)")
                if not self._play(clip):
                    return self._finish_stop()
                ok = random.random() < 0.7  # 가짜: 70% 확률로 성공
                if ok:
                    break
                self._notify(f"{OBJECTS[obj]}을(를) 놓쳤어요. 다시 시도해요", "warn")
            if ok:
                self._set(step="carrying", message=f"{OBJECTS[obj]}을(를) {BINS[obj]} 수거함으로 옮기는 중")
                time.sleep(2.0)
                done += 1
            else:
                failed += 1
                self._notify(f"{OBJECTS[obj]}을(를) 집지 못해 건너뛰었어요. 직접 정리해 주세요", "warn")
            self._set(step="returning", message="처음 자세로 돌아가는 중" if self.cmd != "pause" else "처음 자세로 돌아가서 멈출게요")
            time.sleep(1.0)
            self._set(progress={"done": done, "failed": failed, "remaining": len(todo) - done - failed})
        self._set(state="done", step=None, current=None, detected=[], message=f"정리 끝! {done}개 정리, {failed}개 실패")
        self._notify(f"정리를 마쳤어요 ({done}개 정리, {failed}개 실패)")

    def _finish_stop(self):
        if self.cmd == "estop":
            self._set(state="estop", step=None, message="비상정지! 로봇이 그 자세로 멈췄어요. 주변을 확인한 뒤 다시 시작하세요")
            self._notify("비상정지 버튼이 눌렸어요", "error")
        else:
            self._set(state="idle", step=None, current=None, message="중지했어요. 처음 자세로 돌아왔어요")
            self._notify("정리를 중지했어요")
        self.cmd = None
```
</details>

<details>
<summary><b>dev/app/server.py</b> (웹 서버)</summary>

```python
"""웹 서버: 브라우저 화면(static/)과 정리 로봇(Cleaner)을 이어준다.
실행 (dev 폴더에서): python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
→ 노트북: http://localhost:8000   같은 와이파이의 폰: http://<노트북 IP>:8000"""
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.cleaner import FakeCleaner

app = FastAPI()
cleaner = FakeCleaner()


@app.get("/api/status")
def status():
    return cleaner.status()


@app.post("/api/{action}")
def command(action: str):
    actions = {"start": cleaner.start, "pause": cleaner.pause, "resume": cleaner.resume,
               "stop": cleaner.stop, "estop": cleaner.estop}
    if action not in actions:
        return {"ok": False, "error": f"모르는 명령: {action}"}
    result = actions[action]()
    return {"ok": result is not False}


@app.get("/api/settings")
def get_settings():
    return cleaner.get_settings()


@app.put("/api/settings")
def put_settings(new: dict):
    return {"ok": cleaner.set_settings(new)}


@app.get("/video/{cam}")
def video(cam: str):
    """MJPEG: 브라우저에서 <img src="/video/head"> 하나로 실시간 화면이 나온다"""
    def gen():
        while True:
            jpg = cleaner.frame(cam)
            if jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(1 / 15)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
```
</details>

<details>
<summary><b>dev/app/static/index.html</b> (메인 화면 — 뼈대만)</summary>

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>책상 정리 로봇</title>
  <style>
    body { font-family: sans-serif; margin: 16px; max-width: 900px; }
    #cams { display: flex; gap: 8px; flex-wrap: wrap; }
    #cams img { width: 100%; max-width: 440px; border-radius: 8px; background: #ddd; }
    #message { font-size: 1.3em; margin: 12px 0; }
    button { font-size: 1.1em; padding: 10px 18px; margin: 4px; border-radius: 8px; }
    #estop { background: #d32f2f; color: white; }
  </style>
</head>
<body>
  <h1>책상 정리 로봇</h1>
  <div id="cams">
    <img src="/video/head" alt="책상 전체 카메라">
    <img src="/video/wrist" alt="로봇 손 카메라">
  </div>
  <div id="message">연결 중...</div>
  <div id="progress"></div>
  <button id="start">정리 시작</button>
  <button id="pause">일시정지</button>
  <button id="resume">계속</button>
  <button id="stop">중지</button>
  <button id="estop">비상정지</button>
  <ul id="notifications"></ul>
  <script>
    for (const id of ["start", "pause", "resume", "stop", "estop"]) {
      document.getElementById(id).onclick = () => fetch("/api/" + id, { method: "POST" });
    }
    async function refresh() {
      const s = await (await fetch("/api/status")).json();
      document.getElementById("message").textContent = s.message;
      const p = s.progress;
      document.getElementById("progress").textContent = `정리 ${p.done} · 실패 ${p.failed} · 남음 ${p.remaining}`;
      document.getElementById("start").disabled = ["cleaning", "paused"].includes(s.state);
      document.getElementById("pause").disabled = s.state !== "cleaning";
      document.getElementById("resume").disabled = s.state !== "paused";
      document.getElementById("stop").disabled = !["cleaning", "paused"].includes(s.state);
      document.getElementById("notifications").innerHTML =
        s.notifications.slice(-5).reverse().map(n => `<li>${n.time} ${n.text}</li>`).join("");
    }
    setInterval(refresh, 500);
    refresh();
  </script>
</body>
</html>
```
</details>

### 5-3. 실행해 보기
```bash
cd dev
.venv-ui\Scripts\activate
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```
1. 브라우저에서 `http://localhost:8000` → 영상 2개와 "대기 중이에요"가 보이면 성공
2. **[정리 시작]** → 영상이 움직이고 문구가 바뀐다. 일시정지·계속·중지·비상정지도 눌러 보기
3. **휴대폰으로 보기 (원격)**
   - 노트북과 휴대폰이 **같은 와이파이**인지 확인
   - 노트북에서 `ipconfig` → "IPv4 주소" (예: `192.168.0.12`)
   - 휴대폰 브라우저에서 `http://192.168.0.12:8000`
   - 처음 실행할 때 윈도우 방화벽 창이 뜨면 **허용** (안 떴는데 안 열리면 9장 참고)
4. 서버 끄기: 터미널에서 `Ctrl+C`

### 5-4. 코드 읽기 (둘 다, 30분)
아래 질문에 답할 수 있으면 다음 단계로:
- [정리 시작]을 누르면 어떤 순서로 코드가 실행되나? (`index.html` 버튼 → `server.py` `command` → `cleaner.py` `start` → `_run`)
- 화면 문구는 어디서 오나? (`_set(message=...)` → `/api/status` → `refresh()`)
- 실시간 화면은 어떻게 나오나? (`_play`가 `self.frames`를 바꿈 → `/video/head`가 계속 보냄)
- 일시정지를 누르면 왜 바로 안 멈추나? (2-3 참고)

---

## 6. 주차별 할 일 (목요일까지 main에 머지 → 금요일 출근일에 팀장이 확인)

### 5주차 (마감 11/5 목)
| | 할 일 | 완료 기준 |
|---|---|---|
| 둘 다 | 5장 따라 하기, A/B 정하기, Git 브랜치 만들기 (8장) | 둘 다 휴대폰에서 화면이 열림 |
| 둘 다 | 시작 코드 커밋 (한 명이 PR, 한 명이 확인) | main에 `dev/app/` 들어감 |
| B | 메인 화면 레이아웃 스케치 (종이나 Figma 아무거나) | 단톡방에 공유 |

### 6주차 (마감 11/12 목)
| | 할 일 | 완료 기준 |
|---|---|---|
| A | **기록 저장**: 물건 하나 끝날 때마다 `outputs/history.csv`에 한 줄 (시각, 물건, 성공/실패, 시도 횟수) + `GET /api/history` | 정리 2번 하면 기록 2번 분이 나옴 |
| A | **설정 검사**: 이상한 값(`max_retries: -1`, 없는 물건 이름) 거부 | 잘못 보내면 `{"ok": false, "error": "..."}` |
| B | **메인 화면 완성**: 상태 색, 진행 막대, 큰 버튼, 비상정지 눈에 띄게, 알림 경고 색 | 2-2 ① 표의 항목 전부 |
| B | **설정 화면**: 체크박스·속도·재시도, 저장 버튼, 정리 중이면 "정리 중에는 바꿀 수 없어요" | 저장 후 새로고침해도 값 유지 |

### 7주차 (마감 11/19 목)
| | 할 일 | 완료 기준 |
|---|---|---|
| A | **원격 보안**: 같은 와이파이의 아무나 로봇을 움직이면 곤란 → 첫 접속 시 4자리 PIN 입력 (PIN은 설정 파일에) | PIN 없이는 버튼 API가 거부됨 (화면 보기는 허용해도 됨) |
| A | **오류 흉내**: 가짜 로봇에 "카메라 끊김", "로봇 연결 끊김"을 일부러 내는 방법 (예: `POST /api/debug/error`) → `state: "error"` + 알림 | B가 오류 화면을 시험할 수 있음 |
| B | **기록 화면** (2-2 ③) | 물건별 성공/실패 개수와 "자주 놓치는 물건" |
| B | **휴대폰 화면 맞춤**: 세로 화면에서 버튼이 손가락으로 누르기 좋게, 영상이 위아래로 | 휴대폰에서 한 손으로 조작 가능 |
| B | **연결 끊김 표시**: 서버를 껐을 때 화면이 "로봇과 연결이 끊겼어요"로 바뀜 | `fetch` 실패 처리 |

### 8주차 (마감 11/26 목)
| | 할 일 | 완료 기준 |
|---|---|---|
| 둘 다 | **사용자 시험**: 이 프로젝트를 모르는 사람(가족, 친구) 2명에게 휴대폰만 주고 "책상 정리시켜 봐" → 헷갈린 점 기록 → 고치기 | 고친 목록을 단톡방에 |
| 둘 다 | **사용 설명서** `doc/사용_설명서.md` 1쪽: 켜는 법, 휴대폰 접속, 버튼 설명, 문제가 생기면 | 처음 보는 사람이 따라 할 수 있음 |
| A | 팀장과 RealCleaner 연결 준비 (7장) — 화면이 FakeCleaner에만 있는 기능을 쓰지 않는지 확인 | |

### 9주차 (11/27 금 출근일) — 통합
팀장이 `RealCleaner`를 연결해서 **실제 로봇을 너희 화면으로** 돌린다. 이날 측정하는 30회 시험도 이 화면으로 진행하는 게 목표.

---

## 7. 진짜 로봇과 연결 (팀장 작업, 알아만 두기)

- 팀장이 `RealCleaner`를 만든다: `FakeCleaner`와 **메서드 이름·`status()` 형식이 똑같고**, 안에서만 진짜 로봇·카메라·AI를 쓴다
- `server.py`에서 `cleaner = FakeCleaner()` 한 줄만 `RealCleaner()`로 바뀐다
- 그래서 너희가 지킬 것:
  - 화면(B)은 `/api/...`와 `/video/...`만 쓴다 (`cleaner.py` 내부를 직접 기대하지 않기)
  - `status()`에 필드를 **추가**하는 건 괜찮지만, 있는 필드 이름·뜻을 바꾸면 팀장에게 알리기
  - **카메라를 화면 쪽에서 직접 열지 않는다**: 윈도우에서 카메라는 한 프로그램만 열 수 있어서, 다른 게 열고 있으면 로봇이 못 본다 (실제로 겪은 문제)
- 진짜 로봇에서 "성공"은 놓은 뒤 head 카메라로 다시 봤을 때 그 물건이 없어졌는지로 판단할 예정 (가짜에서는 70% 확률)

---

## 8. Git 협업 (처음이면 이대로)

```bash
# 처음 한 번: 내 브랜치 만들기 (A는 ui/server, B는 ui/screen)
git checkout main
git pull
git checkout -b ui/server

# 작업할 때마다
git pull origin main             # 상대 작업 받아오기 (충돌 나면 단톡방에)
git add dev/app/server.py dev/app/cleaner.py   # 내 파일만 골라서 (git add . 금지)
git commit -m "기록 저장 추가"
git push -u origin ui/server
```
- GitHub에서 **Pull Request** 만들기 → 상대가 "Files changed" 보고 승인 → 머지
- **커밋하면 안 되는 것**: `outputs/` (영상, 기록), `.venv-ui/`, `configs/app_settings.json`(개인 설정). `.gitignore`에 `.venv-ui/`, `dev/configs/app_settings.json` 추가하는 것도 첫 PR에 넣기
- 커밋 전 확인: 서버 켜서 [정리 시작] → 끝까지 한 바퀴

---

## 9. 자주 막히는 것

| 증상 | 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | `dev` 폴더에서 실행했는지, `dev/app/__init__.py`(빈 파일)가 있는지 |
| `FileNotFoundError: ...ui_pack/clips.json` | `ui_pack.zip`을 `dev/outputs/ui_pack/`에 풀었는지 (폴더가 한 겹 더 생기지 않았는지) |
| `[Errno 10048] ... address already in use` | 서버가 이미 켜져 있음 → 다른 터미널의 서버 끄기, 또는 `--port 8001` |
| 휴대폰에서 안 열림 | ① 같은 와이파이인지 (회사·학교 와이파이는 기기끼리 막힌 경우가 많음 → 휴대폰 핫스팟에 노트북 연결) ② `--host 0.0.0.0`으로 켰는지 ③ 윈도우 방화벽: "Windows Defender 방화벽 → 앱 허용"에서 Python 허용 |
| 고쳤는데 화면이 그대로 | 브라우저 캐시 → `Ctrl+F5` (휴대폰은 새로고침 길게) |
| 영상 위 글씨가 `???` | OpenCV는 한글을 못 씀 → 영상 위 글씨는 영어, 한글은 HTML로 |
| 한글이 깨짐 | 파일을 UTF-8로 저장 (VS Code 오른쪽 아래 인코딩 확인) |
| Python 수정이 반영 안 됨 | 서버를 껐다 켜기 (또는 `--reload` 옵션) |

막히면 30분 이상 혼자 붙잡지 말고 단톡방에: **무엇을 하려고 했는지 + 실행한 명령 + 에러 전체**.
