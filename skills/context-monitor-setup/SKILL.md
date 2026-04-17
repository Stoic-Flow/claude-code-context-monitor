# /setup-context-monitor -- First-Run Installer

## When to Use
User types `/setup-context-monitor` or asks to install/configure the context monitor.
Also auto-suggested if the context monitor files are missing.

## What to Do

### 1. Check existing installation
Look for these files:
- `.claude/hooks/context-monitor.py` (core hook)
- `.claude/hooks/context-monitor-gate.py` (auto-stop gate)
- `.claude/hooks/context-monitor-config.json` (config)
- `.claude/rules/context-monitor.md` (behavioral rules)
- PostToolUse + PreToolUse entries in `.claude/settings.json`

If all exist, report "Context monitor is already installed" and show current config values.

### 2. Ask user preferences (if new install or reconfigure)
Ask these questions in ONE message, with defaults shown:

```
Context Monitor Setup:

1. Context ceiling (tokens) -- your quality drop-off point, NOT the model's max
   Default: 200000 (200K). Opus users typically use 200-500K, Sonnet 120-150K.
   Your choice? [200000]

2. Warning threshold (%) -- when to start mentioning context pressure
   Default: 70%
   Your choice? [70]

3. Critical threshold (%) -- when to strongly recommend /compact
   Default: 85%
   Your choice? [85]

4. Auto-stop -- block all tool use when context is dangerously high?
   Default: ON at 90%
   Your choice? [on/off, threshold %]

5. Visual footer -- show context % at bottom of every response?
   Default: ON
   Your choice? [on/off]

6. Cooldown (seconds) -- minimum interval between context readings
   Default: 60. Lower = more frequent updates, slightly higher token cost.
   Your choice? [60]

7. Show token counts -- display in/out token counts?
   Default: OFF
   Your choice? [on/off]

8. Show cost -- display estimated per-turn cost?
   Default: OFF (requires correct pricing in config for your model)
   Your choice? [on/off]
```

### 3. Write config file
Write `.claude/hooks/context-monitor-config.json` with user's choices:
```json
{
  "context_ceiling": <their_choice>,
  "warn_pct": <their_choice>,
  "critical_pct": <their_choice>,
  "auto_stop": <true/false>,
  "auto_stop_pct": <their_choice>,
  "cooldown_seconds": <their_choice>,
  "show_breakdown": true,
  "show_tokens": <true/false>,
  "show_cost": <true/false>,
  "cost_per_million": {
    "input": 15.00,
    "output": 75.00,
    "cache_read": 1.50,
    "cache_write": 18.75
  },
  "visual_indicator": <true/false>,
  "enabled": true
}
```

### 4. Add hooks to settings.json
Add TWO entries to the user's `.claude/settings.json`:

**PostToolUse** (monitoring):
```json
{
  "matcher": "Bash|Write|Edit|Read|Grep|Glob|Agent|WebFetch|WebSearch",
  "hooks": [{
    "type": "command",
    "command": "python \".claude/hooks/context-monitor.py\"",
    "timeout": 5
  }]
}
```

**PreToolUse** (auto-stop gate):
```json
{
  "matcher": "Bash|Write|Edit|Read|Grep|Glob|Agent|WebFetch|WebSearch",
  "hooks": [{
    "type": "command",
    "command": "python \".claude/hooks/context-monitor-gate.py\"",
    "timeout": 5
  }]
}
```

IMPORTANT: Merge into existing hooks arrays -- don't overwrite other hooks.

### 5. Copy rules file
Write `.claude/rules/context-monitor.md` (the behavioral rules for Claude).

### 6. Confirm installation
Report what was installed, show the config, and tell the user:
- "The monitor activates on your next tool use."
- "Type /context anytime for a detailed status check."
- "Edit .claude/hooks/context-monitor-config.json to change settings."
- "Set enabled: false to disable completely without removing files."
