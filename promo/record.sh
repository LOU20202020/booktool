#!/usr/bin/env bash
# 一次完整录制：起程序 → 等窗口就绪 → 开录 → 放行动作 → 收尾
set -u
cd "$(dirname "$0")"
PY="C:/Users/LOU0122/booktool-venv/Scripts/python.exe"
RAW="C:/Users/LOU0122/booktool/promo/clips/raw.mp4"
LOG="$LOCALAPPDATA/Temp/demo_run.log"

rm -f go.flag ready.flag beats.json "$RAW"
PYTHONUTF8=1 "$PY" demo.py > "$LOG" 2>&1 &
DEMO_PID=$!

# 等窗口真的画出来（demo 建好窗口后会写 ready.flag）
for i in $(seq 1 60); do
  [ -f ready.flag ] && break
  sleep 0.5
done
echo "window ready" >> "$LOG"

ffmpeg -hide_banner -loglevel warning -f gdigrab -framerate 30 -t 45 \
  -i title="BookTool Demo" -c:v libx264 -preset veryfast -crf 16 -pix_fmt yuv420p \
  "$RAW" -y >> "$LOG" 2>&1 &
FF_PID=$!

sleep 1.2
touch go.flag

wait $DEMO_PID
echo "demo done" >> "$LOG"
wait $FF_PID
echo "ffmpeg done" >> "$LOG"
ffprobe -v error -show_entries format=duration -show_entries stream=width,height \
  -of default=nw=1 "$RAW" >> "$LOG" 2>&1
