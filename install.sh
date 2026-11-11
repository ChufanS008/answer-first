#!/usr/bin/env bash
# One-line install for answer-first.
#
#   curl -fsSL https://raw.githubusercontent.com/ChufanS008/answer-first/main/install.sh | bash
#
# What it does:
#   1. clones (or updates) the skill into ~/.claude/skills/answer-first
#   2. merges the Stop and PostToolUse hooks into ~/.claude/settings.json (backup kept, idempotent)
#   3. runs the fixture test so you can see the linter works on your machine
#
# Uninstall: remove the two hook entries from ~/.claude/settings.json and delete the skill directory.
set -euo pipefail

REPO="${ANSWER_FIRST_REPO:-https://github.com/ChufanS008/answer-first}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILL_DIR="$CLAUDE_DIR/skills/answer-first"
SETTINGS="$CLAUDE_DIR/settings.json"

command -v git >/dev/null || { echo "git is required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }

mkdir -p "$CLAUDE_DIR/skills"
if [ -d "$SKILL_DIR/.git" ]; then
  echo "updating $SKILL_DIR"
  git -C "$SKILL_DIR" pull -q --ff-only
else
  echo "cloning into $SKILL_DIR"
  git clone -q "$REPO" "$SKILL_DIR"
fi

python3 - "$SETTINGS" <<'PY'
import json, sys, shutil, pathlib, datetime
path = pathlib.Path(sys.argv[1])
base = '$HOME/.claude/skills/answer-first/scripts/'
wanted = {
    "Stop": ("hook_stop.py", {"hooks": [{"type": "command", "command": f'python3 "{base}hook_stop.py"', "timeout": 15}]}),
    "PostToolUse": ("hook_doc.py", {"matcher": "Write|Edit|MultiEdit",
                    "hooks": [{"type": "command", "command": f'python3 "{base}hook_doc.py"', "timeout": 15}]}),
}

settings = {}
if path.exists():
    text = path.read_text().strip()
    if text:
        settings = json.loads(text)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy(path, path.with_name(f"settings.json.bak-{stamp}"))

hooks = settings.setdefault("hooks", {})
changed = False
for event, (script, entry) in wanted.items():
    lst = hooks.setdefault(event, [])
    present = any(f"answer-first/scripts/{script}" in h.get("command", "")
                  for e in lst for h in e.get("hooks", []))
    if present:
        print(f"{event} hook already present")
    else:
        lst.append(entry)
        changed = True
        print(f"{event} hook added")
if changed:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
PY

echo
python3 "$SKILL_DIR/tests/test_lint.py" | tail -2
echo
echo "installed. Open a new Claude Code session and it is active."
echo "try it:  echo 'Per your feedback the layout now uses a grid.' | python3 $SKILL_DIR/scripts/reply_lint.py --mode doc"
