#!/usr/bin/env python3
"""Lint a chat reply or a document for the things users correct most often:
too long for the question, process narration, AI-flavoured filler, handing a
read-only step back to the user.

    reply_lint.py --mode reply --question "用户原话" < reply.txt
    reply_lint.py --mode doc  path/to/file.md

Exit 0 clean, 1 findings (printed to stdout).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

# ---------- pattern families ----------

# Filler that adds words and no information. Both chat and docs.
AI_TELLS = [
    r"—",                                   # em dash in Chinese prose
    r"值得(注意|一提|关注)的是", r"需要(注意|指出|说明)的是", r"总的来说", r"综上所述", r"总而言之",
    r"让我们", r"深入(探讨|分析|了解)", r"赋能", r"旨在", r"在这个.{0,8}时代", r"不仅.{0,12}而且",
    r"首先.{0,40}其次.{0,40}(最后|再次)",   # three-beat parallelism
    r"希望(这|以上).{0,6}(对你|有帮助)", r"如果(你)?还有(其他|别的)(问题|需要)",
    r"\bdelve\b", r"it'?s worth noting", r"in conclusion", r"i hope this helps", r"great question",
    r"\bleverage\b", r"\bseamless(ly)?\b", r"\brobust\b", r"\bnavigat(e|ing) the\b",
]

# Chat-only: throat clearing before the answer.
PREAMBLE = [
    r"^(好的|明白了|没问题|收到|了解|当然|OK|Sure|Got it|Absolutely)[,，。!！\s]",
    r"^(让我|我来|我会|我将)(帮你|为你|来)?",
    r"^以下是", r"^下面是", r"^这是一个",
]

# Doc-only: the document talks about its own revision history or the chat that produced it.
DOC_RESIDUE = [
    r"此前", r"上一版", r"上个版本", r"之前的版本", r"旧版", r"原先(的)?(方案|版本|写法)", r"原来的(方案|版本|写法)",
    r"(修改|改动|变更|更新)说明", r"本次(改动|修改|更新|调整|迭代)", r"这次(改动|修改|更新|调整)",
    r"相比(之前|上一版|上版|原来)", r"较上一版", r"与之前相比",
    r"根据(你|您|大家|老板|反馈)的?(反馈|意见|建议|要求)", r"按(照)?(你|您)的?(要求|意思|说法)", r"应(你|您)要求",
    r"(之前|此前|原先)(的)?判断", r"已(修复|修正|按|改为|调整为)", r"不再(使用|采用|保留)",
    r"（(已删除|已移除|新增|已新增|已修改|待删)）", r"\((added|removed|updated|fixed)\)",
    r"参考过程", r"测试过程(如下|是)", r"讨论过程", r"我们(先|尝试|试了|讨论了)", r"我(先|尝试|试了|一开始)",
    r"v\d+ ?(修复|更新|修正)版",
    # English residue, same families as ship-the-result
    r"\bper (your|the) (feedback|request|review)\b", r"\bas (we )?discussed\b", r"\bas (you )?(requested|asked|suggested)\b",
    r"\b(previous|earlier|original|first) (version|draft|attempt)\b", r"\b(updated|fixed|revised) version\b",
    r"\bcompared to (the )?(previous|last|earlier)\b",
]

# Chat-only: handing the user a read-only step the agent could do itself (browser, dashboard, chat, mailbox, docs).
_READ = r"(查|看|拉|找|读|核|核对|对一下|验证|确认一下|导出|截图|截个图)"
PUSHBACK = [
    rf"要不要我.{{0,24}}{_READ}", rf"需要(的话)?我(再)?(去|来)?{_READ}吗",
    r"你(先|去|帮我|自己)?(截图|截个图|导出|拉|查|找).{0,12}(发|给|告诉)我", rf"(把|将).{{0,20}}(截图|导出|链接|数据)(发|给)我",
    rf"你确认(后|的话|之后)?我(再)?(去)?{_READ}", rf"等你.{{0,10}}(截图|导出|发来|确认)",
    r"shall i (check|look|pull|find)", r"want me to (check|look|pull|find)",
]
# A step that truly needs the user: credentials, payment, scanning a QR code, account signup, a physical device, an outward action.
HARD_LIMIT = re.compile(r"(消息|TestFlight|发给|发到|发群|发出|发送|发布|开.{0,4}权限|上线|删除|密码|密钥|API ?Key|token|扫码|付款|支付|续费|注册账号|实名|验证码|人机|工单|手机上|真机|sudo|登录态|授权)", re.I)

# Signals in the user's message that a long answer is wanted.
LONG_OK = re.compile(
    r"(写|帖子|文章|报告|文档|方案|PRD|规划|计划|策略|翻译|润色|改写|粘贴|prompt|完整|详细|全部|全量|列出|清单|逐条|逐个|一步一步|展开|"
    r"draft|write|post|report|plan|detailed|full|complete|list all|step by step)",
    re.I,
)
# Analysis-type asks get a looser budget: depth is wanted, padding is not.
MEDIUM_OK = re.compile(r"(分析|复盘|检查|审核|评估|对标|梳理|整理|review|audit|analy[sz]e)", re.I)
# Not a human turn: scheduled tasks, resumed sessions, skill preambles.
AUTOMATED = re.compile(r"^(执行定时任务|You are running|You are |This session is being continued|Base directory|<)", re.I)

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Thresholds in characters. A short question with a long reply is the main signal.
SHORT_QUESTION_CHARS = _env_int("ANSWER_FIRST_SHORT_Q", 60)
LONG_REPLY_CHARS = _env_int("ANSWER_FIRST_LONG_REPLY", 2500)
MEDIUM_REPLY_CHARS = _env_int("ANSWER_FIRST_MEDIUM_REPLY", 4000)
HARD_CAP_CHARS = _env_int("ANSWER_FIRST_HARD_CAP", 6000)


@dataclass
class Finding:
    family: str
    match: str
    line: str


def _scan(text: str, patterns: list[str], family: str) -> list[Finding]:
    out: list[Finding] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("```", "|", ">")):  # skip code, tables, quotes
            continue
        for p in patterns:
            m = re.search(p, s, re.I)
            if m:
                out.append(Finding(family, m.group(0), s[:80]))
                break
    return out


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    if re.search(r"<(html|body|div|p|script|style)\b", text, re.I):
        # HTML: only visible prose counts. Scripts, styles, tags and comments are code.
        text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S | re.I)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
    return text


def lint_reply(reply: str, question: str = "") -> list[Finding]:
    prose = strip_code(reply)
    f: list[Finding] = []
    n = len(prose)
    q = (question or "").strip()
    if AUTOMATED.match(q):
        return f
    budget = MEDIUM_REPLY_CHARS if MEDIUM_OK.search(q) else LONG_REPLY_CHARS
    if q and len(q) < SHORT_QUESTION_CHARS and n > budget and not LONG_OK.search(q):
        f.append(Finding("too-long", msg("q-vs-a", q=len(q), n=n), msg("too-long-hint")))
    elif n > HARD_CAP_CHARS and not LONG_OK.search(q):
        f.append(Finding("too-long", msg("chars", n=n), msg("hard-cap-hint")))
    first = prose.strip().splitlines()[0] if prose.strip() else ""
    for p in PREAMBLE:
        if re.search(p, first, re.I):
            # "Sure, <actual content>" passes; only a line that is nothing but warm-up counts
            if p.startswith("^(好的") and len(first) > 12:
                continue
            f.append(Finding("preamble", first[:40], msg("preamble-hint")))
            break
    f += _scan(prose, [x for x in AI_TELLS if x != "—"], "ai-tell")  # em dash only matters in deliverables
    for x in _scan(prose, PUSHBACK, "push-back"):
        if not HARD_LIMIT.search(x.line):
            f.append(x)
    return f


def lint_doc(text: str) -> list[Finding]:
    prose = strip_code(text)
    f = _scan(prose, DOC_RESIDUE, "doc-residue")
    f += _scan(prose, AI_TELLS, "ai-tell")
    return f


MESSAGES = {
    "en": {
        "too-long": "Rewrite: conclusion in the first sentence, keep only what the user needs to act. No method, no options you rejected.",
        "doc-residue": "Documents show the final state only. The reader was not in this chat: delete every sentence about earlier versions, changes, feedback or process.",
        "push-back": "If a step is read-only (browser, dashboard, chat, mailbox, doc), do it and report. Only credentials, payment, QR scans and account signup need the user, and those get named once at the start.",
        "style": "Drop em dashes, preamble, stock phrases and three-beat lists. Write plainly.",
        "too-long-hint": "conclusion first, cut to a third",
        "hard-cap-hint": "nobody asked for a long piece, cut it",
        "preamble-hint": "first sentence is the answer, delete the warm-up",
        "q-vs-a": "{q}-char question, {n}-char reply",
        "chars": "{n} chars",
        "reply-where": "The reply you are about to send has problems. Rewrite it, then stop:",
        "doc-where": "What you just wrote into {name} carries chat residue. Fix it now:",
    },
    "zh": {
        "too-long": "重写：第一句给结论，只保留用户做决定需要的内容，不解释过程，不列你考虑过的选项。",
        "doc-residue": "文档只写最终态。读者没参加这场对话，删掉所有关于上一版、改动、反馈、过程的句子。",
        "push-back": "能读能查的事直接去做（浏览器、后台、群聊、邮箱、文档），做完再汇报，不要问要不要、也不要让用户截图。真要用户来的只有密码密钥、付款、扫码、注册账号这类，开工时一次说清。",
        "style": "去掉破折号、开场白、套话和三段排比，用人话。",
        "too-long-hint": "把结论放第一句，其余砍到三分之一",
        "hard-cap-hint": "没人要求长文，砍",
        "preamble-hint": "第一句就是结论，删掉开场白",
        "q-vs-a": "{q} 字的问题，{n} 字的回答",
        "chars": "{n} 字",
        "reply-where": "你准备发出的回复有问题，重写后再结束：",
        "doc-where": "刚写进 {name} 的内容带会话残留，现在就改：",
    },
}


def msg(key: str, **kw) -> str:
    lang = os.environ.get("ANSWER_FIRST_LANG", "en")
    table = MESSAGES.get(lang, MESSAGES["en"])
    return table[key].format(**kw)


def format_findings(findings: list[Finding], where: str) -> str:
    out = [f"[answer-first] {where}"]
    seen = set()
    for x in findings:
        key = (x.family, x.match)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"  [{x.family}] \"{x.match}\"  <- {x.line}")
    out.append("")
    fams = {x.family for x in findings}
    if "too-long" in fams:
        out.append(msg("too-long"))
    if "doc-residue" in fams:
        out.append(msg("doc-residue"))
    if "push-back" in fams:
        out.append(msg("push-back"))
    if fams & {"ai-tell", "preamble"}:
        out.append(msg("style"))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["reply", "doc"], default="reply")
    ap.add_argument("--question", default="")
    ap.add_argument("file", nargs="?")
    a = ap.parse_args()
    text = open(a.file, encoding="utf-8", errors="replace").read() if a.file else sys.stdin.read()
    f = lint_reply(text, a.question) if a.mode == "reply" else lint_doc(text)
    if f:
        print(format_findings(f, a.file or "stdin"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
