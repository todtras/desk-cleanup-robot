#!/bin/bash
# 공장 부품(계단 모양, 짧은·중간·긴 3종) 공용 ACT. 11/13 녹화 pick_step_demo 45개 (0~14 짧은, 15~29 중간, 30~44 긴)
# 시작 대기를 자르고(_demot), 길이별 5·10·15개로 각각 v5 펜 정책 10만에서 이어서 STEPS. "시연 몇 개면 되나" 곡선용
# 결과: ~/train/act_pick_step_k{5,10,15}/checkpoints/0X0000
# 사용 (서버): 노트북 outputs/datasets/pick_step_demo를 ~/datasets로 올린 뒤 tmux new -d -s step 'bash ~/train_step.sh 2>&1 | tee ~/train_step.log; bash'
STEPS=${STEPS:-20000}
P=~/lerobot-env/bin/python
[ -e "$HOME/datasets/pick_step_demot/meta/info.json" ] || $P ~/trim_idle.py pick_step_demo 2>&1 | grep "=====" | tail -1
eps() { python3 -c "k=$1; print('[' + ','.join(str(b + i) for b in (0, 15, 30) for i in range(k)) + ']')"; }
for k in 15 5 10; do  # 15개(전부) 먼저: 내일 시험할 주 모델
  out=$HOME/train/act_pick_step_k$k
  [ -e "$out/checkpoints/last" ] && { echo "===== k$k 이미 있음 → 건너뜀"; continue; }
  rm -rf "$out"
  echo "===== step k$k ($(eps $k)): v5 펜 10만에서 $STEPS 스텝 ($(date))"
  ~/lerobot-env/bin/lerobot-train --policy.path="$HOME/train/act_pick_pen_v5/checkpoints/100000/pretrained_model" \
    --dataset.repo_id=local/pick_step_demot --dataset.root="$HOME/datasets/pick_step_demot" --dataset.video_backend=pyav \
    --dataset.episodes="$(eps $k)" --output_dir="$out" --policy.device=cuda --policy.push_to_hub=false \
    --steps="$STEPS" --save_freq=10000 --batch_size=8 --num_workers=8 --wandb.enable=false
done
echo "===== step 끝 ($(date))"
