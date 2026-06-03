#!/bin/bash

claude --permission-mode acceptEdits "@.agents/prd/unified-brep-wrapper.md @.agents/issues/unified-brep-wrapper/ @.agents/progress.txt \
1. Find the first issue file whose acceptance criteria are not all checked off and implement it. \
2. Run your tests and type checks. \
3. Check off the completed acceptance criteria in the issue file. \
4. Commit your changes. \
5. Append your progress to .agents/progress.txt. \
ONLY DO ONE ISSUE AT A TIME."