#!/usr/bin/env python3
"""Claude Code PostToolUse hook for Write / Edit / MultiEdit.

Scans prose files Claude just wrote for revision-history residue and AI filler.
Exit 2 shows the findings to Claude right after the write, so it fixes the file
before moving on. Cannot undo the write; that is fine, the next Edit fixes it.

Skipped: code files, anything under .claude/ or a memory dir, and files whose
job is to record change history (changelogs, logs, handovers, notes, reflections).
Add your own skip pattern with ANSWER_FIRST_SKIP=<regex>.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reply_lint import lint_doc, format_findings, msg  # noqa: E402

PROSE_EXT = {".md", ".html", ".htm", ".txt", ".rst"}
SKIP_PATH = re.compile(
    r"(/\.claude/|/memory/|/scratchpad/|/node_modules/|changelog|update-log|handover|reflection|"
    r"heartbeat|\.log$|memory-write-log|decision|台账|会议|meeting|minutes|周报|日报|notes?\.md$)",
    re.I,
)
EXTRA_SKIP = os.environ.get("ANSWER_FIRST_SKIP")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0
    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    if not fp or Path(fp).suffix.lower() not in PROSE_EXT or SKIP_PATH.search(fp):
        return 0
    if EXTRA_SKIP and re.search(EXTRA_SKIP, fp, re.I):
        return 0
    # For Edit only the new text is Claude's; for Write the whole content.
    text = ti.get("content") or ti.get("new_string") or ""
    if not text and ti.get("edits"):
        text = "\n".join(e.get("new_string", "") for e in ti["edits"])
    if len(text.strip()) < 20:
        return 0
    findings = lint_doc(text)
    if not findings:
        return 0
    sys.stderr.write(format_findings(findings, msg("doc-where", name=Path(fp).name)) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
