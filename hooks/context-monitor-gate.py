#!/usr/bin/env python3
"""
Context Monitor Gate -- PreToolUse Hook
========================================
Blocks tool execution when context usage exceeds the auto-stop threshold.

Reads the state file written by context-monitor.py (PostToolUse) and returns
a block decision if context is critically high. Designed to be fast -- reads
one small JSON file, no JSONL parsing.

Supports a time-limited override: when the user acknowledges the warning and
chooses to continue, Claude sets override_until in config. The gate honors
this override until it expires (default 30 min window).

The block message tells both Claude and the user what happened and what to do.
User can override by saying "continue anyway" (Claude sets the override),
setting "auto_stop": false in config, or by compacting.

License: MIT
"""

import json
import os
import sys
import time


def main():
    """Check context state and block if over threshold."""
    try:
        # Always read stdin (hook input with session_id)
        try:
            raw = sys.stdin.buffer.read()
            hook_input = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            hook_input = {}

        my_session_id = hook_input.get("session_id", "")

        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Load config
        config_path = os.path.join(script_dir, "context-monitor-config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            return  # No config = no gate

        if not config.get("auto_stop", False):
            return  # Auto-stop disabled

        # Check for active override (time-limited bypass)
        override_until = config.get("override_until", 0)
        if override_until > 0 and time.time() < override_until:
            return  # Override active -- allow through

        # Read state file (written by PostToolUse hook)
        state_path = os.path.join(script_dir, ".ctx-monitor-state.json")
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            return  # No state = can't gate

        # Don't block on stale data (>5 min old)
        if time.time() - state.get("ts", 0) > 300:
            return

        # Session isolation: only block if state was written by THIS session
        # Prevents cross-session contamination when running parallel sessions
        state_session = state.get("session_id", "")
        if my_session_id and state_session and my_session_id != state_session:
            return  # State belongs to a different session -- ignore

        pct = state.get("pct", 0)
        stop_pct = config.get("auto_stop_pct", 90)

        if pct >= stop_pct:
            total = state.get("total", 0)
            ceiling = state.get("ceiling", 200000)

            def fmt(n):
                return "{:.1f}K".format(n / 1000) if n >= 1000 else str(n)

            reason = (
                "AUTO-STOP: Context at {pct:.0f}% ({total}/{ceil}). "
                "Threshold: {stop}%.\n\n"
                "Options:\n"
                "1. Say \"continue anyway\" to override for 30 minutes\n"
                "2. Run /compact to free context and continue working\n"
                "3. Start a new session with a resume prompt\n"
                "4. Set \"auto_stop\": false in config to disable permanently"
            ).format(
                pct=pct, total=fmt(total), ceil=fmt(ceiling), stop=stop_pct
            )

            print(json.dumps({"decision": "block", "reason": reason}))

    except Exception:
        pass  # Never break the session


if __name__ == "__main__":
    main()