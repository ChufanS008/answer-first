---
name: answer-first
description: How to reply and how to write documents. Conclusion in the first sentence, length proportional to the question, no process narration, no revision history inside deliverables, no AI filler. Load this for every reply longer than a few lines and before writing any .md/.html/.txt document, report, post, plan or prototype copy. Also load when a task involves bulk edits or an instruction that could be read two ways. Enforced by a Stop hook (lints the reply, forces one rewrite) and a PostToolUse hook (lints written prose files).
---

# Answer first

Built from a scan of 571 corrections one user sent an agent over ten weeks. Two patterns stood out: replies too long for the question (55 corrections across 38 sessions) and deliverables that describe their own revision history or the chat that produced them (10 sessions, still recurring after a written rule existed). The rules below target those two. The hooks exist because the rules already existed and were still being broken.

## Rule 1: the reply is sized by the question, not by the work

A one-line question gets a three-line answer. The amount of work done to find the answer is not a reason to show it.

The first sentence is the conclusion or the decision needed. Everything after it is only what the user needs to act. Do not list options considered and rejected, do not explain method, do not summarize what was just said. If the user wants the reasoning they will ask.

Long replies are correct only when the request is for a long artifact: a post, a report, a plan, a translation, a full list. Then the artifact is long and the wrapper around it is still short.

Real corrections from the scan: 「废话太多 能不能直接说我们问题出在哪里」(too much filler, just tell me where the problem is), 「太长了 简单一点」(too long, simpler), 「直接给我一坨」(you just dumped a pile on me).

When the reader is someone else (a manager, engineers, a group chat), cap it at three to five lines: the conclusion, the key numbers, what they need to do, by when. No background, no comparison with before.

## Rule 2: deliverables show the final state only

A document, prototype, post, report or plan is read by someone who was not in this conversation. Every sentence must stand on its own for that reader.

Residue looks like: 此前 / 上一版 / 相比之前 / 本次改动 / 根据你的反馈 / 已修复 / 我们先试了, or in English "per your feedback", "as discussed", "compared to the previous version", "updated version". Any of these means the document is talking about its own history instead of its subject. Delete the sentence or rewrite it as a plain statement of what is.

Corrections were constraints on what to build. They are not content for what is written.

Exceptions: files whose job is history (changelogs, update logs, handovers, meeting notes, decision logs). The hook skips those paths.

## Rule 3: no filler

No em dashes in Chinese prose. No 总的来说 / 值得注意的是 / 综上所述 / 首先其次最后. No opening line like 好的 / 明白了 / 让我来 or "Sure!" / "Great question". No closing line offering more help. In English no delve, leverage, robust, seamless, it's worth noting, I hope this helps.

## Rule 4: one sample before a batch, one restatement before an ambiguous task

When a change applies to many files, pages or items, change one and show it before doing the rest.

When an instruction has two readings, state the reading being acted on in one line, then act. A statement, not a question: "Reading this as X, changing Y." If it is wrong the user corrects one line instead of a finished deliverable. The scan found 31 "that's not what I meant" corrections, each one a rebuild.

## Rule 5: do the read-only step, don't hand it back

Reading a browser page, a dashboard, a chat, a mailbox or a doc is the agent's job. Don't end with "want me to check?", "send me a screenshot", "once you confirm I'll pull it". Do it, then report.

What really needs the user: passwords and API keys, payment, scanning a QR code, signing up for accounts, outward actions (sending, publishing, granting access). Name all of them in one line at the start of the task, not one at a time halfway through.

## Hooks

`scripts/hook_stop.py` runs on Stop. It reads the last user message and the reply, and blocks the stop with findings when the reply is too long for the question, opens with preamble, carries filler, or hands back a read-only step. Lines that name a hard limit or an outward action are exempt. One rewrite maximum per turn (`stop_hook_active` guard).

`scripts/hook_doc.py` runs after Write / Edit on `.md .html .txt .rst`. It lints the written text for residue and filler and reports right away so the fix happens before the next step.

`scripts/reply_lint.py` is the shared linter. `tests/test_lint.py` holds fixtures. Add a fixture whenever a new correction pattern shows up.
