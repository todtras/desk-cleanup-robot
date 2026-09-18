# 26_2_intern — 데스크 정리 로봇팔 프로젝트

PhysicalAI 로봇팔(SO-101 leader/follower) 모방학습·강화학습 프로젝트.

## 구조

```
doc/                   기획서, 발표자료
dev/
├── requirements.txt    pip install -r requirements.txt 로 환경 재현
├── scripts/            캘리브레이션/진단용 스크립트
├── configs/
│   ├── robot/            카메라·포트·calibration 설정
│   └── training/          lerobot-train용 실행 config (IL/RL 공용)
└── outputs/             (git 미추적) 녹화 데이터셋, 체크포인트, 캡처 이미지
```

## 셋업

```bash
cd dev
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
```

## 로봇 연결/캘리브레이션

```bash
python -m lerobot.scripts.lerobot_find_port
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=<PORT>
lerobot-calibrate --teleop.type=so101_leader --teleop.port=<PORT> --teleop.id=<ID>
```

## 데이터 수집

```bash
lerobot-record --robot.type=so101_follower --robot.port=<PORT> --robot.id=<ID> \
  --teleop.type=so101_leader --teleop.port=<PORT> --teleop.id=<ID> \
  --dataset.repo_id=<repo> --dataset.single_task="<task>" --dataset.num_episodes=<N>
```

## 학습 (모방학습 / 강화학습 공용)

GPU 서버(A4000)에서:

```bash
lerobot-train --config_path=dev/configs/training/<config>.yaml
```
