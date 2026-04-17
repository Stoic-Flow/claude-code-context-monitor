# /context -- Context Window Status Check

## When to Use
User types `/context` or asks "what's context at?", "how much context left?", "context status", etc.

## What to Do

### 1. Read current state
Read `.claude/hooks/.ctx-monitor-state.json`. Contains:
```json
{"pct": 35.1, "total": 70200, "ceiling": 200000, "ts": 1776259100}
```

### 2. Read session history
Read `.claude/hooks/.ctx-monitor-history.jsonl`. Each line:
```json
{"ts": 1776259100, "pct": 35.1, "total": 70200, "inp": 500, "cache_create": 2000, "cache_read": 67700, "out": 1200}
```

### 3. Calculate and present

**Burn rate:** Compare first and last history entries.
- `tokens_added = last.total - first.total`
- `elapsed_minutes = (last.ts - first.ts) / 60`
- `burn_rate = tokens_added / elapsed_minutes` (tokens/min)

**Remaining capacity:**
- `remaining = ceiling - total`
- `estimated_minutes = remaining / burn_rate` (if burn_rate > 0)
- `estimated_exchanges = remaining / 7500` (avg tokens per user exchange)
- `estimated_file_reads = remaining / 2500` (avg tokens per file read)

**Compaction events:** Scan history for entries where `total` drops by >20K from previous entry. Each drop = one compaction.

### 4. Output format

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
| Session cost | ~$1.24 (est. from 15 readings) |

Progress: |====......| 35%

Status: Healthy -- no action needed.
```

**Cost calculation** (if `cost_usd` present in history entries):
- Last turn cost: from most recent history entry's `cost_usd`
- Session cost estimate: sum all `cost_usd` values in history, then extrapolate.
  Since readings are sampled (cooldown-limited), multiply by `(total_turns / readings_count)`
  where total_turns can be estimated from the JSONL line count.
  If unsure, just sum history and note "estimated from N sampled readings."
- If `cost_usd` is null in history, skip cost rows.

**Pricing note**: Cost is based on `cost_per_million` in config (defaults to Opus 4 API pricing).
Tell user to update pricing in config if using a different model or plan.

At WARN (>=70%): Status line = "Warning -- consider /compact soon"
At CRITICAL (>=85%): Status line = "Critical -- compact or start new session"
At AUTO-STOP (>=90%): Status line = "Auto-stop active -- next tool use will be blocked"

### 5. If no state file exists
Report: "Context monitor hasn't fired yet this session. Use any tool to trigger the first reading."

### 6. If no history file exists
Skip burn rate and compaction sections. Report current state only.

### 7. `/context override` -- Manual Override
When user runs `/context override` or says "continue anyway" after an auto-stop block:
1. Read `.claude/hooks/context-monitor-config.json`
2. Get `override_duration_minutes` (default 30)
3. Calculate expiry: current epoch seconds + (duration * 60)
4. Write `override_until` with the expiry timestamp to the config JSON
5. Report: "Override active for {duration} minutes (expires {HH:MM}). Context at {pct}% -- /compact recommended when convenient."
6. Resume the previously blocked operation if one was pending

To cancel an active override: set `override_until: 0` in the config, or run `/context override cancel`.