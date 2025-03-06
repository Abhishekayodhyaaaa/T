#!/bin/bash

# Keep Alive Trick
keep_alive() {
  while true; do
    echo "🟢 Still Running - $(date)" | tee -a output.log
    sleep 30  # ✅ Print output every 30 sec
  done
}

# Auto-Restart Trick
while true; do
  echo "🚀 Starting Process at $(date)" | tee -a output.log
  nohup python3 Master.py >> output.log 2>&1 &  # ✅ Append logs to output.log
  keep_alive &  # ✅ Start Keep Alive Function in background
  wait $!  # ✅ Wait for Master.py to finish
  echo "⚠️ Process Stopped, Restarting..." | tee -a output.log
  sleep 10  # ✅ 10 sec delay before restart
done
