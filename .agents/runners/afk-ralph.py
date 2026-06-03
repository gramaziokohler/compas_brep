#!/usr/bin/env python3
import argparse
import datetime
import re
import subprocess
import sys
import time


def next_reset_utc(hour: int) -> float:
    """Return the Unix timestamp of the next occurrence of <hour>:00 UTC."""
    now = datetime.datetime.now(datetime.UTC)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    return target.timestamp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("iterations", type=int)
    args = parser.parse_args()

    iterations = args.iterations

    i = 1
    while i <= iterations:
        result = subprocess.run(
            [
                "sbx",
                "run",
                "claude-compas-brep",
                "--",
                "--permission-mode",
                "acceptEdits",
                "-p",
                (
                    "@.agents/prd/unified-brep-wrapper.md "
                    "@.agents/issues/unified-brep-wrapper/ "
                    "@.agents/progress.txt "
                    "1. Find the first issue file whose acceptance criteria are not all checked off and implement it. "
                    "2. Run your tests and type checks. "
                    "3. Check off the completed acceptance criteria in the issue file. "
                    "4. Append your progress to .agents/progress.txt. "
                    "5. Commit your changes. "
                    "ONLY WORK ON A SINGLE ISSUE. "
                    "If all issue files are complete, output <promise>COMPLETE</promise>."
                ),
            ],
            capture_output=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        output = result.stdout or ""
        print(output, end="")

        if "session limit" in output or "You've hit your" in output:
            m = re.search(r"resets\s+(\d{1,2})(?:am|pm)?\s*\(UTC\)", output, re.IGNORECASE)
            if not m:
                print("Session limit hit but could not parse reset time. Exiting.")
                sys.exit(1)
            reset_hour = int(m.group(1))
            now = time.time()
            wait_secs = int(next_reset_utc(reset_hour) - now) + 60  # +60s buffer
            print(f"Session limit hit. Sleeping {wait_secs}s until {reset_hour:02d}:00 UTC...")
            time.sleep(wait_secs)
            # retry the same iteration
            continue

        if "<promise>COMPLETE</promise>" in output:
            print(f"PRD complete after {i} iterations.")
            sys.exit(0)

        i += 1


if __name__ == "__main__":
    main()
