#!/usr/bin/env python3
"""Claude Code Stop hook: lint the reply Claude is about to finish with.

Input on stdin: {"transcript_path": ..., "stop_hook_active": bool, ...}
Exit 2 blocks the stop and feeds stderr back to Claude, which then rewrites.
When stop_hook_active is true the hook already fired once this turn; let it through
so one rewrite is the maximum.

Env:
  ANSWER_FIRST_MODE=warn   log instead of block (for measuring false positives)
  ANSWER_FIRST_LOG=<path>  log file (default ~/.cache/answer-first/stop.log)
  ANSWER_FIRST_LANG=zh     Chinese messages (default en)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reply_lint import lint_reply, format_findings, msg  # noqa: E402

LOG = Path(os.environ.get("ANSWER_FIRST_LOG") or Path.home() / ".cache" / "answer-first" / "stop.log").expanduser()


def last_exchange(transcript: Path) -> tuple[str, str]:
    """Return (last real user text, assistant text after it)."""
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    except Exception:
        return "", ""
    user_text, assistant_parts = "", []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        msg = d.get("message") or {}
        content = msg.get("content")
        if t == "user":
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                blocks = [b for b in content if isinstance(b, dict)]
                if any(b.get("type") == "tool_result" for b in blocks):
                    continue  # tool output, not a human turn
                text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            else:
                continue
            if text.strip() and not text.lstrip().startswith("<"):
                user_text, assistant_parts = text.strip(), []
        elif t == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    assistant_parts.append(b["text"])
    return user_text, "\n".join(assistant_parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    path = payload.get("transcript_path")
    if not path:
        return 0
    question, reply = last_exchange(Path(path))
    if len(reply.strip()) < 200:
        return 0
    findings = lint_reply(reply, question)
    if not findings:
        return 0
    report = format_findings(findings, msg("reply-where"))
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(json.dumps({"q": question[:80], "len": len(reply), "f": [x.family for x in findings]}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    if os.environ.get("ANSWER_FIRST_MODE", "block") == "warn":
        return 0
    sys.stderr.write(report + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
