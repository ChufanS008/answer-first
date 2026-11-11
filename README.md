# answer-first

A Claude Code skill plus two hooks that keep an agent's replies sized to the question and keep chat history out of the documents it writes.

You ask "why did signups drop?" and get 3,000 characters: a warm-up line, the method, three options it considered, a summary of what you just said, and the answer somewhere in paragraph four. Or you ask for a plan and the plan opens with "Compared to the previous version, per your feedback, we now...". The reader of that plan was never in your chat.

Both habits survive prompt rules. I had them written into my agent's memory for weeks and they kept coming back, so this repo checks them mechanically on every turn.

## Where the rules come from

I scanned 571 corrections I had sent my own agent over ten weeks (222 sessions) and bucketed them. The biggest buckets:

| Pattern | Corrections / sessions | What handles it |
|---|---|---|
| Reply too long, answer buried | 55 / 38 | Stop hook |
| Misread the instruction, rebuilt the work | 31 / 24 | Skill rule 4 (no hook) |
| Revision history or process written into a deliverable | 10 / 10 | PostToolUse hook, and [ship-the-result](https://github.com/ChufanS008/ship-the-result) for commits and PRs |
| AI-flavoured filler | 6 / 4 | Both hooks |

The process-history bucket is small but it is the one that convinced me: a written rule against it already existed and it still recurred in ten separate sessions.

Before turning blocking on, I replayed 679 real replies from one month through the Stop hook. It flagged 4% of them (24 replies), and reading all 24 by hand, every one deserved the rewrite. Em dashes are checked only in documents, never in chat, because in chat half the hits were false positives.

## What is in here

`SKILL.md` is the rule set: size the reply by the question, show only the final state in deliverables, no filler, one sample before a batch edit, do read-only steps yourself.

`scripts/reply_lint.py` is the linter both hooks share. It works on Chinese and English text. You can run it by hand:

```bash
echo 'Per your feedback the layout now uses a grid.' | python3 scripts/reply_lint.py --mode doc
python3 scripts/reply_lint.py --mode reply --question "why is signup down" < reply.txt
```

`scripts/hook_stop.py` is a `Stop` hook. It reads the last human message and the reply from the transcript. It blocks the stop and hands findings back to the model when a short question (under 60 characters) gets a reply over 2,500 characters, when the reply opens with preamble, when it carries stock filler, or when it hands back a read-only step ("want me to check the logs?"). Analysis requests get a looser budget, and requests for a long artifact (write, post, report, plan, translate, full list) are not length-checked. It fires at most once per turn, so the worst case is one rewrite.

`scripts/hook_doc.py` is a `PostToolUse` hook on Write / Edit / MultiEdit for `.md .html .htm .txt .rst`. It scans the text just written for revision-history residue and filler and reports immediately, so the next edit fixes it. For HTML it looks only at visible text. Changelogs, logs, handovers, meeting notes and anything under `.claude/` are skipped.

`tests/test_lint.py` has 35 fixtures covering the linter and both hooks.

## Install

One line. Clones the skill into `~/.claude/skills/`, merges both hooks into `~/.claude/settings.json` (backup kept, safe to re-run), and runs the tests:

```bash
curl -fsSL https://raw.githubusercontent.com/ChufanS008/answer-first/main/install.sh | bash
```

Open a new Claude Code session and it is active.

### Manual install

```bash
git clone https://github.com/ChufanS008/answer-first ~/.claude/skills/answer-first
```

Then merge `hooks/settings.example.json` into `~/.claude/settings.json` or a project's `.claude/settings.json`.

## Settings

All optional, set as environment variables:

| Variable | Default | Effect |
|---|---|---|
| `ANSWER_FIRST_MODE` | `block` | `warn` logs findings without blocking. Run this for a week first to see your own false-positive rate |
| `ANSWER_FIRST_LOG` | `~/.cache/answer-first/stop.log` | Where the Stop hook logs each hit |
| `ANSWER_FIRST_LANG` | `en` | `zh` for Chinese feedback messages |
| `ANSWER_FIRST_SKIP` | none | Extra regex of file paths the doc hook ignores |
| `ANSWER_FIRST_SHORT_Q` | `60` | A question shorter than this counts as short |
| `ANSWER_FIRST_LONG_REPLY` | `2500` | Reply budget for a short question |
| `ANSWER_FIRST_MEDIUM_REPLY` | `4000` | Budget when the question asks for analysis or review |
| `ANSWER_FIRST_HARD_CAP` | `6000` | Budget for any question that did not ask for a long piece |

## Tuning

When a correction shows up that the linter misses, add the line to `tests/test_lint.py` and a pattern to `reply_lint.py`. When the doc hook flags a file whose job really is history, add its path to `ANSWER_FIRST_SKIP` instead of ignoring the message.

## License

MIT
