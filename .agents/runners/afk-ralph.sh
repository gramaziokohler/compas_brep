#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <iterations>"
  exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

for ((i=1; i<=$1; i++)); do
  log "=== Iteration $i/$1 ==="
  tmpfile=$(mktemp)
  log "Output file: $tmpfile"

  sbx run claude-compas-brep -- --permission-mode acceptEdits --verbose -p "@.agents/prd/surface-type-support-plan.md @.agents/issues/surface-type-support/ @.agents/issues/surface-type-support/progress.txt \
  1. Find the first issue file whose acceptance criteria are not all checked off and implement it. \
  2. Run your tests and type checks. \
  3. Check off the completed acceptance criteria in the issue file. \
  4. Append your progress to .agents/progress.txt. \
  5. Commit your changes. \
  ONLY WORK ON A SINGLE ISSUE. \
  If all issue files are complete, output <promise>COMPLETE</promise>." 2>&1 | tee "$tmpfile" || true

  bytes=$(wc -c < "$tmpfile" | tr -d ' ')
  log "Captured $bytes bytes"

  if [ "$bytes" -eq 0 ]; then
    log "WARNING: no output captured — sbx may be using a PTY that bypasses the pipe"
  else
    log "--- first 10 lines ---"
    head -10 "$tmpfile"
    log "--- last 5 lines ---"
    tail -5 "$tmpfile"
    log "--- end of output preview ---"
  fi

  result=$(cat "$tmpfile")
  rm "$tmpfile"

  if [[ "$result" == *"session limit"* ]] || [[ "$result" == *"You've hit your"* ]]; then
    now=$(date -u +%s)
    target=$(date -u -j -f "%Y-%m-%d %H:%M:%S" "$(date -u +%Y-%m-%d) 01:00:00" +%s)
    if [ "$now" -ge "$target" ]; then
      target=$(date -u -j -v+1d -f "%Y-%m-%d %H:%M:%S" "$(date -u -v+1d +%Y-%m-%d) 01:00:00" +%s)
    fi
    wait_secs=$((target - now + 60))  # +60s buffer
    log "Session limit hit. Sleeping ${wait_secs}s until 1am UTC..."
    sleep $wait_secs
    ((i--))  # retry the same iteration
    continue
  fi

  if [[ "$result" == *"<promise>COMPLETE</promise>"* ]]; then
    log "PRD complete after $i iterations."
    exit 0
  fi

  log "Iteration $i done — no COMPLETE signal, continuing."
done

log "Finished $1 iterations."