#!/bin/bash
# v5 시연 앞 대기를 자른 데이터(_v5t)로 v5 10만 체크포인트에서 이어서 학습. 물병·지우개 먼저 (오늘 스텝 비교용), 나머지는 그 뒤
# 사용 (서버): tmux new -d -s v5t 'bash ~/train_v5t.sh 2>&1 | tee ~/train_v5t.log; bash'
# 결과: ~/train/act_pick_<물체>_v5t/checkpoints/0X0000 (= v5 10만 + X만 스텝)
STEPS=${STEPS:-20000}
P=~/lerobot-env/bin/python
ft() {
  name=$1; out=$HOME/train/act_${name}t
  [ -e "$out/checkpoints/last" ] && { echo "===== ${name}t 이미 학습됨 → 건너뜀"; return; }
  rm -rf "$out"
  echo "===== ${name}t: v5 10만에서 $STEPS 스텝 ($(date))"
  ~/lerobot-env/bin/lerobot-train --policy.path="$HOME/train/act_$name/checkpoints/100000/pretrained_model" \
    --dataset.repo_id=local/${name}t --dataset.root="$HOME/datasets/${name}t" --dataset.video_backend=pyav \
    --output_dir="$out" --policy.device=cuda --policy.push_to_hub=false \
    --steps="$STEPS" --save_freq=10000 --batch_size=8 --num_workers=8 --wandb.enable=false
}
for o in bottle eraser; do $P ~/trim_idle.py pick_${o}_v5 2>&1 | grep -E "=====|자름$" | tail -3; ft pick_${o}_v5; done
for o in tape pen paper; do $P ~/trim_idle.py pick_${o}_v5 2>&1 | grep -E "=====|자름$" | tail -3; ft pick_${o}_v5; done
echo "===== v5t 끝 ($(date))"
