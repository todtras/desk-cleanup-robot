#!/bin/bash
# GPU 서버(gpu-lab)에서 ACT 학습. 데이터셋을 순서대로 학습하고, 중간에 끊겼으면 마지막 체크포인트부터 이어감.
# 사용 (서버에서, 접속이 끊겨도 계속 돌게 tmux 안에서):
#   tmux new -s train 'bash ~/train_server.sh pick_tape pick_pen; bash'
#   다시 보기: tmux attach -t train   /  빠져나오기(학습은 계속): Ctrl+B 누르고 D
# 데이터: ~/datasets/<이름>/  결과: ~/train/act_<이름>/checkpoints/<스텝>/pretrained_model
set -e
STEPS=${STEPS:-50000}
for name in "$@"; do
  out=$HOME/train/act_$name
  if [ -e "$out/checkpoints/last" ]; then
    echo "===== $name: 이어서 학습 ($(readlink "$out/checkpoints/last"))"
    ~/lerobot-env/bin/lerobot-train --config_path="$out/checkpoints/last/pretrained_model/train_config.json" --resume=true
  else
    rm -rf "$out"  # 첫 저장 전에 끊긴 찌꺼기 (있으면 lerobot이 FileExistsError)
    echo "===== $name: 새로 학습 ($STEPS 스텝)"
    # pyav: 서버에 ffmpeg가 없어서 torchcodec 대신. num_workers 8: 컨테이너 CPU 상한 12스레드
    ~/lerobot-env/bin/lerobot-train --policy.type=act --dataset.repo_id=local/$name --dataset.root="$HOME/datasets/$name" \
      --dataset.video_backend=pyav --output_dir="$out" --policy.device=cuda --policy.push_to_hub=false \
      --steps="$STEPS" --save_freq=10000 --batch_size=8 --num_workers=8 --wandb.enable=false
  fi
done
echo "===== 끝: $*"
