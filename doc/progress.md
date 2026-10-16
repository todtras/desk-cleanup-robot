# 진행 기록

## 2회차 (2026-10-02)

### 한 일
**작업 환경**
- 카메라: USB 카메라 1번(`VideoCapture(1)`), 1280x720. 0번은 노트북 카메라(사용 안 함)
- 책상 위 작업 구역과 수거함 3칸(왼쪽, 위에서부터 필기구/사무용품/쓰레기)을 테이프로 표시
- 어댑터: **리더 6V, 팔로워 12V** (반대로 꽂으면 리더 모터가 과전압 에러로 인식 안 됨)

**데이터셋**
- 클래스 7개, Roboflow 알파벳 순 번호: 0 bottle, 1 eraser, 2 paper, 3 pen, 4 stapler, 5 tape, 6 vinyl
- 정의 결정: paper는 **구겨진 종이만**(펼친 종이/서류는 라벨 X), 찌그러진 투명 페트병은 vinyl
- `dev/scripts/record_video.py`(1280x720 녹화), `extract_frames.py`(긴 변 960으로 프레임 추출, 중복 제거)
- 라벨링: Roboflow Bounding Box. 팀장이 val 33장 + train 약 90장 완료, 팀원 2명에게 각 30~50장 배정
- 가이드: `doc/라벨링_가이드.md` (애매하면 건너뛰고 `애매한.txt`로 전달)
- Roboflow 주의: Resize/Augmentation 없이 버전 생성, train/val은 영상 단위로 직접 지정(자동 분할 금지)

**학습**
- `dev/scripts/train.py`: 조건 고정(yolo11n, imgsz 960, seed 0), 증강 값만 인자로 변경, `results.csv`에 기록
- `dev/scripts/colab_train.ipynb`: 코랩용 일괄 실행
- 첫 학습(train 약 90 / val 33): mAP50 **0.994**, mAP50-95 **0.799**. 약한 클래스는 eraser(mAP50-95 0.661, recall 0.933)
- val이 train과 같은 날·같은 환경이라 점수가 낙관적일 수 있음
- `dev/scripts/live_detect.py`로 실제 카메라 확인: 잘 동작
- Ultralytics 버전 8.4.171 고정. 전역 `settings.json`이 `astro` 경로를 가리켜서 결과가 엉뚱한 곳에 저장되던 문제는 `train.py`의 `PROJECT` 절대경로로 해결

**로봇**
- 텔레오퍼레이션 정상 동작 (팔로워 COM4, 리더 COM3, ID `fd_follower`/`fd_leader`)
- 캘리브레이션 재수행 후 `dev/scripts/save_poses.py`로 포즈 저장 → `dev/configs/robot/poses.json`
  (`home`, `bin_pen/office/trash_above`, `bin_pen/office/trash_drop`)

### 확인 필요 / 미해결
- 활동보고서 2회 내용 중 "검증 사진 50장"은 실제 val 33장과 불일치 → 서류 수치 정정
- 손목 카메라의 카메라 번호 미확인
- IK 환경(`placo` + SO-101 URDF) 미설치
- 지우개 성능(mAP50-95 0.661): 데이터 추가·라벨 박스 정밀도 점검 필요
- 이미지·영상은 git 제외. 팀원 공유는 드라이브로 (Roboflow export zip 원본 사용)

## 다음주 계획 (초안)

**방향 결정 (월요일)**
- 좌표 기반 파지를 1단계로 먼저 완성하고, 파지 실패가 많은 클래스에만 손목 카메라 모방학습으로 보정(2단계)할지 결정

**팀장**
1. 스탠드로 카메라를 원위치로 복구, 기준 사진(`zones.jpg`)과 겹쳐서 같은 구도인지 확인 후 고정
2. 카메라-로봇 캘리브레이션: 좌표 쌍 수집 → 변환식 → 오차(mm) 측정, 수거함 좌표 등록
3. 탐지 결과 → 로봇 좌표 변환 연동 시험
4. 보강 촬영: 지우개(다른 색·모양), 회색 비닐, 부족한 클래스, val 보강
5. (2단계 결정 시) 손목 카메라 포함 시범 수집 약 10에피소드

**팀원 A (비대면)**
- 증강 파라미터 실험(최소 3개), 결과를 `results.csv`/그래프로 정리, 가장 좋은 `best.pt` 전달
- 약한 클래스 분석, 필요한 추가 데이터 목록 정리
- `이미지 → 탐지 결과(클래스, 박스, 신뢰도)` 추론 모듈 정리 (로봇 쪽 연결용 인터페이스)

**팀원 B (비대면)**
- 증강 실험 병행 또는 SO-101 URDF 기반 시뮬레이션/IK 환경 검토 (`placo`)

**전체 마감**
- 라벨링: 이번주 주말까지, 학습 실험 결과: 다음주 금요일까지
- 최종 모델 평가용 test 세트는 카메라 복구 후 새로 찍은 장면으로 만들고, 마지막에 1회만 사용

## 3회차 (2026-10-16, 오전 근무)

### 방향 전환
- 이사님 일정표(9주, ACT 모방학습으로 픽 앤 플레이스) 기준으로 진행. 좌표 변환·IK 방식은 보류
- 구조: **YOLO가 물체 종류 판별 → 해당 물체의 ACT 정책이 집어서 자기 수거함 위까지 옮김 → 코드로 그리퍼 열기 → home**
  - ACT는 카메라 이미지로 위치를 스스로 찾으므로 YOLO 좌표는 쓰지 않음. YOLO는 분류·순서·완료 판정용
- 3주차 마일스톤(시연 데이터셋 v1) 충족

### 한 일
**시연 데이터 수집** (`dev/outputs/datasets/`, git 제외, 카메라 head+wrist 640x480 30fps)

| 데이터셋 | 물체 → 수거함 | 에피소드 | 잡는 방법 |
|---|---|---|---|
| `pick_tape` | 테이프 → 사무용품 | 40 | 위에서, 롤 테두리 꼬집기 |
| `pick_bottle` | 물병(세움) → 쓰레기 | 31 | 옆에서(수평), 목 부분 |
| `pick_pen` | 펜 → 필기구 | 34 | 위에서, 가운데를 펜과 직각으로 |

- 배치: 정중앙 + ±2~3cm 이동 + 회전(±30° 이내, 물병은 회전 없음)
- 에피소드 = 집기 → 수거함 위까지 옮기기 → 쥔 채 멈춤. 놓기는 녹화하지 않음
- 테이프는 대부분 15초를 꽉 채움(조기 종료 안 함). 물병·펜은 20초 제한, 멈춘 뒤 → 로 종료

**도구**
- `dev/configs/robot/record_pick.yaml`: 녹화 설정 (포트, 카메라 번호, 시간)
- `dev/scripts/record.py`: lerobot-record 래퍼. 영어 음성 안내, 키 반복 입력 무시, 저장 위치 `outputs/datasets/<이름>`, 녹화 끝나도 Ctrl+C 전까지 텔레옵 유지
- `dev/scripts/dashboard.py`: 포트·카메라 번호·데이터셋(에피소드 길이) 점검 페이지 (localhost:8000)

### 겪은 문제와 해결
- **카메라 두 대를 같은 USB 허브에 꽂으면 동시에 안 열림** → wrist를 노트북 본체 포트로
- **카메라 번호(1/2)가 실행할 때마다 바뀜** (같은 모델 두 대) → 녹화 시작마다 rerun 창에서 head/wrist 확인
  - `pick_bottle` 5~30번이 head/wrist 뒤바뀐 채 저장됨 → 영상 파일·통계 맞바꿔 복구 (원본 `_backup_pick_bottle`)
- **대시보드가 켜져 있으면 카메라를 잡고 있어 녹화 실패** → 녹화 전 Ctrl+C로 종료
- **구글 드라이브가 바탕화면을 미러링** → 녹화 중 "액세스 거부". 녹화 동안 드라이브 일시중지
- yaml에 한글이 있으면 lerobot이 cp949로 읽다가 실패 → yaml은 영어만
- PowerShell에서 카메라 인자에 `\"` 쓰면 깨짐 → `'{head: {type: opencv, ...}}'` 처럼 따옴표 없이
- 녹화 종료 시 그리퍼(id 6) Overload error → 팔로워 전원 재투입으로 해제. 펜처럼 얇은 물체는 꽉 쥐지 않기

### 확인 필요 / 미해결
- 데이터셋을 GPU 서버로 옮기는 방법 (git 제외 폴더라 압축해서 전달)
- 실행 스크립트(YOLO → ACT → 그리퍼 열기 → home) 미작성
- `pick_bottle` 전체 통계의 분위수(q01~q99)는 재계산 안 함 (ACT는 평균/표준편차만 써서 영향 없음)

## 다음주 계획 (4주차, 마일스톤: 첫 자율 동작)
1. GPU 서버에서 ACT 학습: `pick_tape` 먼저, 되면 `pick_bottle`, `pick_pen`
   ```
   lerobot-train --policy.type=act --dataset.repo_id=local/pick_tape --dataset.root=outputs/datasets/pick_tape --output_dir=outputs/train/act_pick_tape --policy.device=cuda --policy.push_to_hub=false --steps=50000 --batch_size=8
   ```
2. 출근일: 학습된 정책으로 첫 자율 동작 시연, 성공률 1차 측정 시작(30회), 실패 유형 기록
3. 실행 스크립트 작성: YOLO 분류 → 물체별 ACT → 그리퍼 열기 → home
