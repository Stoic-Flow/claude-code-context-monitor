# Claude Code Context Monitor

**Make Claude aware of its own context window.** The only context monitor that injects usage data into Claude's conversation context — so Claude itself can warn you, adjust strategy, and stop before quality degrades.

Built for **VS Code extension** users and anyone running Claude Code where the terminal status bar isn't visible.

## The Problem

Claude Code sessions silently degrade when context fills up. You don't get a warning. Quality drops gradually — each response slightly worse than the last — until you're debugging bad output instead of building. By the time you notice, you've wasted tokens and time.

Existing tools show you a number in a status bar. You have to notice it yourself. This tool makes **Claude notice it for you.**

## What It Does

| Feature | Description |
|---------|-------------|
| **Claude self-awareness** | Injects context % into Claude's conversation via `additionalContext` — Claude proactively warns at thresholds |
| **Visual footer** | Optional `CTX 44% -- 88.7K/200K` at the bottom of every response (toggleable) |
| **Auto-stop gate** | Blocks all tool execution at 90% — forces a pause before quality collapses (toggleable) |
| **Continue anyway** | Time-limited override when auto-stop fires — say "continue anyway" for a 30-min bypass |
| **Session isolation** | Gate only blocks the session that measured the high context — parallel sessions can't contaminate each other |
| **Burn rate tracking** | Session history tracks context growth over time |
| **Cost estimation** | Optional per-turn cost display based on configurable model pricing |
| **On-demand check** | `/context` skill for detailed status with remaining capacity estimates |
| **Self-installing** | `/setup-context-monitor` skill walks you through configuration |

### How It Looks

Normal operation — terse footer at the bottom of Claude's responses:
```
---
CTX 44% -- 88.7K/200K
```

Approaching limits:
```
---
CTX 74% -- 148K/200K !! consider /compact
```

Critical — Claude leads with a warning:
```
---
CTX 88% -- 176K/200K !!! compact or close session
```

Auto-stop — tool execution blocked with override option:
```
AUTO-STOP: Context at 92% (184K/200K). Threshold: 90%.

Options:
1. Say "continue anyway" to override for 30 minutes
2. Run /compact to free context and continue working
3. Start a new session with a resume prompt
4. Set "auto_stop": false in config to disable permanently
```

With optional tokens and cost enabled:
```
---
CTX 44% -- 88.7K/200K | in:87K out:1.6K | ~$0.0842
```

## How It Works

```
You use a tool (Read, Edit, Bash, etc.)
        |
        v
[PostToolUse hook fires]
        |
        v
context-monitor.py reads Claude's local JSONL session log
        |
        v
Extracts token usage from Anthropic API response data
(input_tokens + cache_creation + cache_read = context total)
        |
        v
Compares against your personal ceiling (default 200K)
        |
        v
Returns JSON with additionalContext --> injected into Claude's context
        |
        v
Claude sees the [CTX] line and renders a visual footer / warns proactively

---

Before your NEXT tool use:
        |
        v
[PreToolUse hook fires]
        |
        v
context-monitor-gate.py reads the state file
        |
        v
If context >= auto_stop_pct --> BLOCKS the tool with an explanation
```

**Zero API calls. Zero network. Reads local files only.** Your conversation data never leaves your machine.

## Requirements

- **Python 3.6+** (standard library only — no pip install needed)
- **Claude Code** (VS Code extension, CLI, or desktop app)
- Works on **Windows, macOS, and Linux**

## Install

### Quick Install (recommended)

1. Copy the files into your project:

```
your-project/
  .claude/
    hooks/
      context-monitor.py          <-- from hooks/
      context-monitor-gate.py     <-- from hooks/
      context-monitor-config.json <-- from hooks/
    rules/
      context-monitor.md          <-- from rules/
    skills/
      context-check/
        SKILL.md                  <-- from skills/context-check/
      context-monitor-setup/
        SKILL.md                  <-- from skills/context-monitor-setup/
```

2. Add these entries to your `.claude/settings.json` (create the file if it doesn't exist):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Write|Edit|Read|Grep|Glob|Agent|WebFetch|WebSearch",
        "hooks": [
          {
            "type": "command",
            "command": "python \".claude/hooks/context-monitor.py\"",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit|Read|Grep|Glob|Agent|WebFetch|WebSearch",
        "hooks": [
          {
            "type": "command",
            "command": "python \".claude/hooks/context-monitor-gate.py\"",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

> **Important:** If you already have hooks in your settings.json, merge the new entries into your existing `PostToolUse` and `PreToolUse` arrays — don't overwrite them.

> **Recommended:** Use absolute paths instead of relative ones. If any Bash command changes the working directory (e.g., `cd /tmp`), relative paths break and **all hooks fail silently**. Replace `.claude/hooks/context-monitor.py` with the full path to your project, e.g.:
> ```
> python "/home/you/my-project/.claude/hooks/context-monitor.py"
> ```

3. Start a new Claude Code session. The monitor activates on your first tool use.

### Guided Install

If the skill files are in place, tell Claude:
```
/setup-context-monitor
```
Claude will walk you through configuration and set everything up.

## Configuration

Edit `.claude/hooks/context-monitor-config.json`:

```json
{
  "context_ceiling": 200000,     // Your quality drop-off point (not the model's max)
  "warn_pct": 70,                // Yellow zone — Claude mentions context pressure
  "critical_pct": 85,            // Red zone — Claude leads with a warning
  "auto_stop": true,             // Block tool execution at auto_stop_pct
  "auto_stop_pct": 90,           // Threshold for auto-stop gate
  "override_until": 0,           // Epoch timestamp — gate allows through if now < this (0 = no override)
  "override_duration_minutes": 30, // How long "continue anyway" lasts
  "cooldown_seconds": 60,        // Minimum interval between readings
  "show_breakdown": true,        // Show cache/new/out in Claude's context
  "show_tokens": false,          // Show in/out token counts in status line
  "show_cost": false,            // Show per-turn cost estimate
  "cost_per_million": {          // API pricing for cost calculation
    "input": 15.00,              //   Opus 4: $15/M input
    "output": 75.00,             //   Opus 4: $75/M output
    "cache_read": 1.50,          //   Opus 4: $1.50/M cache read
    "cache_write": 18.75         //   Opus 4: $18.75/M cache write
  },
  "visual_indicator": true,      // Show footer at bottom of responses
  "enabled": true                // Master on/off switch
}
```

### Ceiling Guide

| Model | Max Context | Suggested Ceiling | Why |
|-------|-------------|-------------------|-----|
| Opus 4 | 200K (standard) / 1M (extended) | 200K | Quality degrades well before the hard limit |
| Sonnet 4 | 200K | 120-150K | Smaller model, tighter effective window |
| Haiku 4.5 | 200K | 80-100K | Prioritize concise sessions |

The ceiling is **your** threshold for when to compact — not the model's technical maximum.

### Pricing Guide

Default pricing is Opus 4 API rates. If you're on a different model:

| Model | input | output | cache_read | cache_write |
|-------|-------|--------|------------|-------------|
| **Opus 4** | 15.00 | 75.00 | 1.50 | 18.75 |
| **Sonnet 4** | 3.00 | 15.00 | 0.30 | 3.75 |
| **Haiku 4.5** | 0.80 | 4.00 | 0.08 | 1.00 |

> If you're on a Claude subscription (Max/Pro), cost tracking is less relevant — but still useful for understanding relative expense between sessions.

All changes take effect on the next tool use. No restart needed.

## On-Demand Check

Type `/context` or ask Claude "what's context at?" for a detailed report:

```
## Context Window Status

| Metric | Value |
|--------|-------|
| Current usage | 70.2K / 200K (35%) |
| Remaining | 129.8K tokens |
| Burn rate | ~2.1K tokens/min |
| Est. remaining | ~62 min at current rate |
| Est. exchanges | ~17 more user exchanges |
| Compactions | 0 this session |
| Last turn cost | $0.0842 |

Progress: |====......| 35%
Status: Healthy — no action needed.
```

## Overhead

| Metric | Value |
|--------|-------|
| Tokens per display | ~25 |
| Default cooldown | 60 seconds |
| Displays per hour | ~60 max |
| Hourly token cost | ~1,500 tokens (0.75% of 200K) |
| Python startup time | ~50-100ms per invocation |
| Gate check time | <5ms (reads one small JSON file) |

**Less than 0.5% of your context window for full visibility into the other 99.5%.**

## How It Compares

| Feature | This tool | claude-context-monitor | claude-code-session-kit | VS Code extensions |
|---------|-----------|----------------------|------------------------|-------------------|
| Claude self-awareness | Yes | No | No | No |
| Auto-stop gate | Yes (configurable) | No | Yes (fixed 70%) | No |
| Visual in conversation | Yes (footer) | No (file output) | No | Status bar |
| Cost tracking | Yes | No | No | Some |
| Burn rate / history | Yes | Yes | No | No |
| On-demand `/context` | Yes | No | No | No |
| Self-installing | Yes | No | No | N/A |
| Token overhead | ~25/display | Varies | Varies | 0 (extension) |
| Works in VS Code ext | Yes | CLI only | CLI only | Yes |
| Works in terminal | Yes | Yes | Yes | No |
| No dependencies | Yes (stdlib) | Varies | Varies | N/A |

**Key differentiator:** Every other tool treats this as a display problem — show the human a number. This tool makes Claude itself aware of context pressure, so it changes behavior at thresholds without you having to watch a meter.

## Files Reference

| File | Purpose | Size |
|------|---------|------|
| `hooks/context-monitor.py` | Core PostToolUse hook — reads JSONL, calculates usage, outputs additionalContext | ~300 lines |
| `hooks/context-monitor-gate.py` | PreToolUse auto-stop gate — blocks tools at threshold | ~80 lines |
| `hooks/context-monitor-config.json` | User configuration — all toggles and thresholds | ~15 lines |
| `rules/context-monitor.md` | Behavioral rules — tells Claude how to render and warn | ~50 lines |
| `skills/context-check/SKILL.md` | `/context` on-demand status check | ~80 lines |
| `skills/context-monitor-setup/SKILL.md` | `/setup-context-monitor` guided installer | ~90 lines |

Runtime files (created automatically, don't commit):
- `.ctx-monitor-stamp` — rate limiter timestamp
- `.ctx-monitor-state.json` — current context snapshot
- `.ctx-monitor-history.jsonl` — session history

## Troubleshooting

**All hooks suddenly failing?**
- A Bash `cd` command likely changed the working directory. Relative hook paths resolve against CWD, not the project root.
- **Fix:** Use absolute paths in settings.json (see Install section). This prevents recurrence.

**Monitor not firing?**
- Check `.claude/settings.json` has the hook entries
- Verify Python is on your PATH: `python --version`
- Start a new session after changing settings.json (hooks load at session start)

**No output / no footer?**
- The monitor needs at least one assistant response before it can read usage data
- Check cooldown hasn't suppressed it: delete `.claude/hooks/.ctx-monitor-stamp`

**Auto-stop blocking everything?**
- Say "continue anyway" — Claude sets a 30-minute override automatically
- Or: run `/compact` and continue working
- Or: start a new session
- Nuclear option: edit config, set `"auto_stop": false`

**Auto-stop triggered by a different session?**
- Fixed in v1.1. The gate now checks `session_id` — it only blocks the session that measured the high context. If you're on an older version, update `context-monitor.py` and `context-monitor-gate.py`.

**Wrong cost numbers?**
- Update `cost_per_million` in config to match your model's pricing
- Default is Opus 4 API rates

## Contributing

Issues and PRs welcome. If you find a bug or have a feature idea, open an issue.

## License

MIT License. See [LICENSE](LICENSE).

## Credits

Built by [Florian Kittler](https://github.com/fkittler) with Claude (Opus 4.6).
