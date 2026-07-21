#!/bin/bash

claude --permission-mode acceptEdits "@CONTEXT.md @.agents/adr/0001-native-json-brep-exchange.md @.agents/adr/0002-rhino-rebuild-via-brepbuilder.md @.agents/issues/brep-exchange/ @.agents/issues/brep-exchange/progress.txt \
1. Find the first issue file whose acceptance criteria are not all checked off and implement it. \
2. Run your tests and type checks. Install the OCC backend first if needed: uv pip install 'cadquery-ocp-novtk>=7.8' — then pytest -m occ -q must pass. \
3. Check off the completed acceptance criteria in the issue file. \
4. Commit your changes. \
5. Append your progress to .agents/issues/brep-exchange/progress.txt. \
The issues are a strict chain — do not start one whose blocker is unfinished. \
CI has no Rhino license and -m 'not rhino' skips Rhino tests by default, so Rhino-marked tests will not run here: say so plainly rather than claiming they passed. \
ONLY DO ONE ISSUE AT A TIME."
