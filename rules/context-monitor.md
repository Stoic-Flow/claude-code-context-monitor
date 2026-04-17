# Context Monitor Rules

## Hook Data
PostToolUse hook injects `[CTX]` lines into your context via `additionalContext`. These appear as `PostToolUse hook additional context:` in system-reminder tags.

## Visual Indicator
When the `[CTX]` line ends with `[VISUAL:ON]`:
- Append a context status footer at the **very end** of your final response to the user
- Format: `---` newline then the compact status line in a code span
- Base: `CTX 27% -- 53.8K/200K`
- With tokens (show_tokens on): `CTX 27% -- 53.8K/200K | in:53K out:1.2K`
- With cost (show_cost on): `CTX 27% -- 53.8K/200K | ~$0.0842`
- With both: `CTX 27% -- 53.8K/200K | in:53K out:1.2K | ~$0.0842`
- At WARN (>=70%): append `!! consider /compact`
- At CRITICAL (>=85%): append `!!! compact or close session`
- Extract cost from the `cost:$X.XXXX` field in the [CTX] line if present
- Only on the final message to the user (not between tool calls)
- Use the MOST RECENT `[CTX]` data available in your context

When `[VISUAL:OFF]`: do NOT append any footer. Still use the data internally for proactive warnings.

## Auto-Stop Gate
A PreToolUse hook (`context-monitor-gate.py`) blocks ALL tool execution when context exceeds `auto_stop_pct` (default 90%). When blocked:
- Claude receives a block reason explaining what happened
- The user sees the block message
- No tool can execute until the user overrides, compacts, starts a new session, or disables auto-stop

If auto-stop fires, do NOT try to work around it. Present the options to the user.

## Override (Continue Anyway)
When the user says "continue anyway", "override", "yes continue", or similar after an auto-stop block:
1. Read `.claude/hooks/context-monitor-config.json`
2. Calculate override expiry: `current_epoch + (override_duration_minutes * 60)` (default 30 min)
3. Write `override_until` with the expiry timestamp to the config file
4. Confirm: "Override active for 30 minutes. Context is at X% -- /compact recommended when possible."
5. Resume the blocked operation

The gate checks `override_until` on every tool call. If current time < override_until, it allows through regardless of context %. Override expires automatically -- no cleanup needed. To cancel early, set `override_until: 0` in config.

## Proactive Warnings (always active, regardless of visual flag)
- At >=70%: mention context pressure naturally in your response
- At >=85%: lead with a clear warning before other content
- At >=90% with auto-stop on: expect tool blockage, proactively suggest /compact

## State Files (written by PostToolUse hook)
- `.claude/hooks/.ctx-monitor-state.json` -- current context snapshot (read by gate)
- `.claude/hooks/.ctx-monitor-history.jsonl` -- session history (read by /context skill)
- `.claude/hooks/.ctx-monitor-stamp` -- rate limiter timestamp

## Toggle Reference
All toggles in `.claude/hooks/context-monitor-config.json`:
- `enabled` -- master on/off for the entire monitor
- `visual_indicator` -- footer display on/off
- `auto_stop` -- PreToolUse gate on/off
- `auto_stop_pct` -- gate threshold (default 90)
- `override_until` -- epoch timestamp; gate allows through if current time < this value (0 = no override)
- `override_duration_minutes` -- how long an override lasts (default 30)
- `cooldown_seconds` -- minimum interval between readings (default 60)

Changes take effect on next tool use, no restart needed.