#!/bin/bash
# train_step.sh(k15 → k5 → k10, 각 2만)가 끝나면 k15를 5만까지 이어서 학습 (11/13: 1만에서 실물 성공률이 낮아 학습량 확인)
# 사용 (서버): tmux new -d -s stepmore 'bash ~/train_step_more.sh 2>&1 | tee ~/train_step_more.log; bash'
until grep -q "===== step 끝" ~/train_step.log 2>/dev/null; do sleep 60; done  # tmux 창 명령줄에 train_step.sh가 남아 pgrep으로는 못 기다림
out=$HOME/train/act_pick_step_k15
echo "===== k15: $(readlink $out/checkpoints/last) → 50000 ($(date))"
~/lerobot-env/bin/lerobot-train --config_path="$out/checkpoints/last/pretrained_model/train_config.json" --resume=true --steps=50000
echo "===== 끝 ($(date))"
