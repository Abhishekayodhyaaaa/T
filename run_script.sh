#!/bin/bash

# Keep Alive Trick
keep_alive() {
  while true; do
    echo "🟢 Still Running - $(date)"
    sleep 100  # Har 5 min baad message print karega
  done
}

# Auto-Restart Trick
while true; do
  echo "🚀 Starting Process at $(date)"
  nohup python3 Master.py > output.log 2>&1 &  # Background Execution
  keep_alive &  # Keep Alive Function Ko Background Me Chalao
  wait $!  # Process ko wait karne do
  echo "⚠️ Process Stopped, Restarting..."
  sleep 10  # 10 sec delay before restart
done
