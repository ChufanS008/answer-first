#!/usr/bin/env python3
"""Fixtures for reply_lint and both hooks. Run: python3 tests/test_lint.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from reply_lint import lint_reply, lint_doc  # noqa: E402

REPLY = [
    # (question, reply, should_flag)
    ("为什么今天没涨", "好的，让我来分析一下。" + "首先，我们需要了解背景。" * 120 + "总的来说，原因有三个。", True),
    ("为什么今天没涨", "没涨是因为周五的邮件序列停了，昨天只发出 1.2 万封。今天重启，明天看数。", False),
    ("帮我写一篇 reddit 帖子，完整版", "Title: ..." + "正文段落。" * 400, False),
    ("这个 hook 是啥意思", "这个 hook 在 commit 前扫消息。" * 300, True),
    ("看一下周报", "值得注意的是，本周注册下降。", True),
    ("看一下周报", "本周注册降 15%，主因是一个渠道停投，下周补上。", False),
    ("翻译一下", "Here is the translation. It's worth noting the tone.", True),
    ("这个颜色行吗", "不行，蓝色和竞品撞了，换成 #7B3FF2 试一版。", False),
    ("看一下投放", "账户我没动。要不要我去后台看一下转化回传？", True),
    ("周报写完了吗", "还差两处：流量页和留存页，你截图发我就补上。", True),
    ("域名买好了吗", "DNS 我来加。邮件服务的 API Key 需要你生成后填进去，注册账号和填密钥我不能代办。", False),
    ("提审了吗", "已提审，版本 0.3.2。控制台要你扫码登录一次，扫完我改超时。", False),
    ("why is signup down", "Great question! Let me delve into the data. " * 80, True),
    ("why is signup down", "Signups fell 15% because the Friday email sequence stopped. It restarts today.", False),
    ("is the build green", "Want me to check the CI logs for you?", True),
]

DOC = [
    ("本次改动：把价格模块删掉，只保留行程。", True),
    ("相比上一版，卡片改成了三列。", True),
    ("根据你的反馈，搜索按钮移到右上角。", True),
    ("此前判断账户不在我们手上，现已修正。", True),
    ("我们先试了正则方案，后来换成 tokenizer。", True),
    ("搜索按钮在右上角。点击后立即生效，无需确认。", False),
    ("卡片三列：头像、近 28 天销量、等级。", False),
    ("广告账户由增长团队管理。", False),
    ("The hook blocks the commit and hands the findings back to the model.", False),
    ("Per your feedback the layout now uses a grid.", True),
    ("Compared to the previous version, the table has two columns.", True),
    ("The table has two columns: date and count.", False),
]


def run_hook(script: str, payload: dict, env: dict | None = None) -> int:
    e = dict(os.environ, **(env or {}))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], input=json.dumps(payload),
                       capture_output=True, text=True, env=e)
    return r.returncode


def hook_cases() -> list[tuple[str, bool]]:
    out = []
    with tempfile.TemporaryDirectory() as d:
        log = str(Path(d) / "stop.log")
        tr = Path(d) / "t.jsonl"
        long_reply = "好的，让我来分析一下。" + "首先，我们需要了解背景。" * 300
        rows = [
            {"type": "user", "message": {"role": "user", "content": "这个是啥意思"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": long_reply}]}},
        ]
        tr.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
        env = {"ANSWER_FIRST_LOG": log}
        out.append(("stop blocks long reply", run_hook("hook_stop.py", {"transcript_path": str(tr)}, env) == 2))
        out.append(("stop lets second pass through", run_hook("hook_stop.py", {"transcript_path": str(tr), "stop_hook_active": True}, env) == 0))
        out.append(("stop warn mode logs only", run_hook("hook_stop.py", {"transcript_path": str(tr)}, dict(env, ANSWER_FIRST_MODE="warn")) == 0))
        out.append(("stop wrote log", Path(log).exists()))
        doc = {"tool_name": "Write", "tool_input": {"file_path": "/x/plan.md", "content": "本次改动：删掉价格模块，只保留行程安排。"}}
        out.append(("doc flags residue", run_hook("hook_doc.py", doc) == 2))
        cl = {"tool_name": "Write", "tool_input": {"file_path": "/x/CHANGELOG.md", "content": "本次改动：删掉价格模块，只保留行程安排。"}}
        out.append(("doc skips changelog", run_hook("hook_doc.py", cl) == 0))
        out.append(("doc honours ANSWER_FIRST_SKIP", run_hook("hook_doc.py", doc, {"ANSWER_FIRST_SKIP": r"plan\.md$"}) == 0))
        code = {"tool_name": "Write", "tool_input": {"file_path": "/x/a.py", "content": "# 本次改动：重写解析器，加上重试逻辑"}}
        out.append(("doc ignores code files", run_hook("hook_doc.py", code) == 0))
    return out


def main() -> int:
    bad = 0
    for q, r, exp in REPLY:
        got = bool(lint_reply(r, q))
        if got != exp:
            bad += 1
            print(f"REPLY mismatch exp={exp} got={got}: q={q!r} r={r[:50]!r}")
    for t, exp in DOC:
        got = bool(lint_doc(t))
        if got != exp:
            bad += 1
            print(f"DOC mismatch exp={exp} got={got}: {t!r}")
    hooks = hook_cases()
    for name, ok in hooks:
        if not ok:
            bad += 1
            print(f"HOOK fail: {name}")
    n = len(REPLY) + len(DOC) + len(hooks)
    print(f"{n - bad}/{n} fixtures pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
