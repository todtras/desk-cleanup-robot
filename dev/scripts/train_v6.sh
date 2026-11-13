#!/bin/bash
# v6 = v5t(지금까지 시연 전부, 앞 대기 자름) + 11/13 실패 칸 보강 시연(pick_<물체>_demo1113, 앞 대기 자름)
# v5t 마지막 체크포인트에서 이어서 STEPS(2만). 결과: ~/train/act_pick_<물체>_v6t/checkpoints/0X0000
# 11/13 계획 B: v5t 5만 순환 대신 v6 먼저 → train_v5t_rr.sh는 종이 1만이 저장되면 멈춤
# 사용 (서버): 노트북의 outputs/datasets/pick_<물체>_demo1113을 ~/datasets로 올린 뒤
#   tmux new -d -s v6 'bash ~/train_v6.sh 2>&1 | tee ~/train_v6.log; bash'
STEPS=${STEPS:-20000}
P=~/lerobot-env/bin/python
step_of() { l=$(readlink "$HOME/train/act_pick_$1/checkpoints/last" 2>/dev/null || echo 0); echo $((10#$l)); }

# 0) v5t 순환: 종이 1만까지만 (테이프·펜·종이 v5t 1만은 v6의 출발점)
if pgrep -f train_v5t_rr.sh >/dev/null; then
  until [ "$(step_of paper_v5t)" -ge 10000 ]; do sleep 30; done
  sleep 60  # 저장 마무리
  pkill -f train_v5t_rr.sh; pkill -f "lerobot-train.*_v5t"; sleep 10
  echo "===== v5t 순환 멈춤 ($(date))"
fi

for o in bottle tape eraser pen paper; do
  d=pick_${o}_demo1113
  if [ ! -e "$HOME/datasets/$d/meta/info.json" ]; then echo "===== $d 없음 → $o 건너뜀"; continue; fi
  [ -e "$HOME/datasets/${d}t/meta/info.json" ] || $P ~/trim_idle.py "$d" 2>&1 | grep "=====" | tail -1
  [ -e "$HOME/datasets/pick_${o}_v6t/meta/info.json" ] || \
    $P -c "import sys; sys.path.insert(0, '$HOME'); from pathlib import Path; from merge_v4 import merge; merge(Path.home() / 'datasets', 'pick_${o}_v6t', ['pick_${o}_v5t', '${d}t'])" 2>&1 | grep -v -i warn | tail -2
  out=$HOME/train/act_pick_${o}_v6t
  if [ -e "$out/checkpoints/last" ]; then echo "===== ${o}_v6t 이미 학습됨 → 건너뜀"; continue; fi
  src=$(readlink -f "$HOME/train/act_pick_${o}_v5t/checkpoints/last")/pretrained_model
  echo "===== ${o}_v6t: $src 에서 $STEPS 스텝 ($(date))"
  ~/lerobot-env/bin/lerobot-train --policy.path="$src" \
    --dataset.repo_id=local/pick_${o}_v6t --dataset.root="$HOME/datasets/pick_${o}_v6t" --dataset.video_backend=pyav \
    --output_dir="$out" --policy.device=cuda --policy.push_to_hub=false \
    --steps="$STEPS" --save_freq=10000 --batch_size=8 --num_workers=8 --wandb.enable=false
done
echo "===== v6 끝 ($(date))"
