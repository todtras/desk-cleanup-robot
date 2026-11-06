#!/bin/bash
# 데이터셋을 돌아가며 1만 스텝씩 학습 (물체마다 첫 체크포인트를 빨리 받으려고). 매번 ~/datasets/$GLOB 중 스텝이 가장 적은 것을 +1만
# → 나중에 올린 데이터셋도 바로 차례가 옴. 학습 중인 게 있으면 끝나길 기다림
# 사용 (서버): tmux new -d -s rr 'GLOB="*_v4*" MAX=100000 bash ~/train_rr.sh; bash'   기본 GLOB=*_v2, MAX=30000. 결과: ~/train/act_<이름>/checkpoints/0X0000
MAX=${MAX:-30000}
while :; do
  while pgrep -f "bin/lerobot-train" >/dev/null; do sleep 30; done
  best=""; bl=$MAX
  for d in ~/datasets/${GLOB:-*_v2}; do
    name=$(basename "$d")
    l=$(readlink ~/train/act_$name/checkpoints/last 2>/dev/null || echo 0); l=$((10#$l))
    [ $l -lt $bl ] && { best=$name; bl=$l; }
  done
  [ -z "$best" ] && break
  STEPS=$((bl + 10000)) bash ~/train_server.sh "$best"
done
echo "===== rr 끝"
