#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <iterations>"
  exit 1
fi

for ((i=1; i<=$1; i++)); do
  tmpfile=$(mktemp)
  sbx run claude-compas-brep -- --permission-mode acceptEdits -p "@.agents/prd/unified-brep-wrapper.md @.agents/issues/unified-brep-wrapper/ @.agents/progress.txt \
  1. Find the first issue file whose acceptance criteria are not all checked off and implement it. \
  2. Run your tests and type checks. \
  3. Check off the completed acceptance criteria in the issue file. \
  4. Append your progress to .agents/progress.txt. \
  5. Commit your changes. \
  ONLY WORK ON A SINGLE ISSUE. \
  If all issue files are complete, output <promise>COMPLETE</promise>." | tee "$tmpfile" || true
  result=$(cat "$tmpfile")
  rm "$tmpfile"

  if [[ "$result" == *"session limit"* ]] || [[ "$result" == *"You've hit your"* ]]; then
    now=$(date -u +%s)
    target=$(date -u -j -f "%Y-%m-%d %H:%M:%S" "$(date -u +%Y-%m-%d) 01:00:00" +%s)
    if [ "$now" -ge "$target" ]; then
      target=$(date -u -j -v+1d -f "%Y-%m-%d %H:%M:%S" "$(date -u -v+1d +%Y-%m-%d) 01:00:00" +%s)
    fi
    wait_secs=$((target - now + 60))  # +60s buffer
    echo "Session limit hit. Sleeping ${wait_secs}s until 1am UTC..."
    sleep $wait_secs
    ((i--))  # retry the same iteration
    continue
  fi

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "PRD complete after $i iterations."
    exit 0
  fi
done