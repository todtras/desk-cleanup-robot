#!/bin/bash
# v5t(시연 앞 대기를 자른 v5) 학습 순환: 테이프·펜·종이를 먼저 1만씩, 그 뒤 다섯 물체를 1만씩 돌아가며 MAX(5만)까지
# 처음 학습은 v5 10만 체크포인트에서 이어서 (--policy.path), 그 뒤는 마지막 체크포인트에서 재개. 스텝 = v5 10만 이후 스텝
# 11/13 오후: 기존 train_v5t.sh가 테이프를 2만까지 돌리던 중 → 테이프 1만이 저장되면 그걸 멈추고 이 스크립트가 이어감
# 사용 (서버): tmux new -d -s v5trr 'bash ~/train_v5t_rr.sh 2>&1 | tee ~/train_v5t_rr.log; bash'
MAX=${MAX:-50000}
P=~/lerobot-env/bin/python
step_of() { l=$(readlink "$HOME/train/act_pick_$1_v5t/checkpoints/last" 2>/dev/null || echo 0); echo $((10#$l)); }

train_to() {  # 물체, 목표 스텝
  o=$1; out=$HOME/train/act_pick_${o}_v5t
  echo "===== ${o}_v5t: $(step_of "$o") → $2 ($(date))"
  if [ -e "$out/checkpoints/last" ]; then
    ~/lerobot-env/bin/lerobot-train --config_path="$out/checkpoints/last/pretrained_model/train_config.json" --resume=true --steps="$2"
  else
    rm -rf "$out"
    ~/lerobot-env/bin/lerobot-train --policy.path="$HOME/train/act_pick_${o}_v5/checkpoints/100000/pretrained_model" \
      --dataset.repo_id=local/pick_${o}_v5t --dataset.root="$HOME/datasets/pick_${o}_v5t" --dataset.video_backend=pyav \
      --output_dir="$out" --policy.device=cuda --policy.push_to_hub=false \
      --steps="$2" --save_freq=10000 --batch_size=8 --num_workers=8 --wandb.enable=false
  fi
}

# 0) 기존 train_v5t.sh: 테이프 1만이 저장될 때까지 기다렸다가 멈춤 (자르기 도중에 끊으면 데이터를 다시 만들어야 함)
if pgrep -f train_v5t.sh >/dev/null; then
  until [ "$(step_of tape)" -ge 10000 ]; do sleep 30; done
  sleep 60  # 저장 마무리
  pkill -f train_v5t.sh; pkill -f "lerobot-train.*pick_tape_v5t"; sleep 10
  echo "===== 기존 train_v5t.sh 멈춤 (테이프 $(step_of tape))"
fi

# 1) 자르기 (없는 것만)
for o in tape pen paper; do
  [ -e "$HOME/datasets/pick_${o}_v5t/meta/info.json" ] || $P ~/trim_idle.py pick_${o}_v5 2>&1 | grep -E "=====" | tail -1
done

# 2) 테이프·펜·종이 1만씩 먼저
for o in tape pen paper; do
  [ "$(step_of "$o")" -lt 10000 ] && train_to "$o" 10000
done

# 3) 다섯 물체를 스텝이 가장 적은 것부터 1만씩 MAX까지
while :; do
  best=""; bl=$MAX
  for o in bottle eraser tape pen paper; do
    l=$(step_of "$o"); [ "$l" -lt "$bl" ] && { best=$o; bl=$l; }
  done
  [ -z "$best" ] && break
  train_to "$best" $((bl + 10000))
done
echo "===== v5t 순환 끝 ($(date))"
