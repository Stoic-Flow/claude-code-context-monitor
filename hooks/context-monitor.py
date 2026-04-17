#!/usr/bin/env python3
"""
Context Monitor for Claude Code -- PostToolUse Hook
====================================================
Displays context window usage as a terse status line after each response.

Reads Claude Code's local JSONL conversation logs to calculate current
context window absorption. No API calls, no network, zero privacy risk.

Token cost: ~25 tokens per display, rate-limited via configurable cooldown.
At 200K ceiling with 20s cooldown: <1% overhead per session.

How it works:
  1. PostToolUse hook fires after each tool execution
  2. Rate limiter checks if cooldown has elapsed (default 20s) -- if not, exits immediately
  3. Reads stdin for session_id (provided by Claude Code hook protocol)
  4. Finds the session's JSONL file via session_id + CLAUDE_PROJECT_DIR env var
  5. Reads last 200KB of JSONL, scans backwards for latest usage data
  6. Calculates context % against your personal ceiling (not the model's 1M limit)
  7. Outputs JSON with additionalContext (PostToolUse protocol -- plain stdout is discarded)

Output: PostToolUse hooks must return JSON with hookSpecificOutput.additionalContext
  to inject text into Claude's context. Plain stdout is silently discarded.
  The status line appears as "PostToolUse hook additional context:" in Claude's view.

Install: Add PostToolUse hook entry to .claude/settings.json (see README)
Config:  context-monitor-config.json (same directory as this script)

License: MIT
"""

import json
import os
import sys
import time
import glob


def load_config(script_dir):
    """Load user configuration with sensible defaults."""
    defaults = {
        "context_ceiling": 200000,
        "warn_pct": 70,
        "critical_pct": 85,
        "cooldown_seconds": 20,
        "show_breakdown": True,
        "enabled": True
    }
    config_path = os.path.join(script_dir, "context-monitor-config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            defaults.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        pass
    return defaults


def check_and_update_stamp(script_dir, cooldown_seconds):
    """Rate-limit displays. Returns True if enough time has passed.
    Updates stamp immediately to prevent concurrent display from parallel hooks.
    """
    stamp_path = os.path.join(script_dir, ".ctx-monitor-stamp")
    now = time.time()
    try:
        with open(stamp_path, "r") as f:
            last_time = float(f.read().strip())
        if now - last_time < cooldown_seconds:
            return False
    except (FileNotFoundError, ValueError, PermissionError):
        pass
    # Update stamp immediately (prevents race from parallel tool calls)
    try:
        with open(stamp_path, "w") as f:
            f.write(str(now))
    except (PermissionError, OSError):
        pass
    return True


def read_hook_input():
    """Read and parse the hook's stdin JSON (tool context).
    Returns dict with at least session_id if available.
    Claude Code pipes JSON to hook stdin and closes the pipe immediately.
    """
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def derive_project_key(project_dir):
    """Convert a filesystem path to Claude Code's project key format.

    Example: C:\\Users\\jane\\projects\\my-app
          -> C--Users-jane-projects-my-app

    Drive letter casing is PRESERVED -- Claude Code uses uppercase on Windows.
    """
    key = ""
    for ch in project_dir:
        if ch.isalnum() or ch == "-":
            key += ch
        else:
            key += "-"
    return key


def find_jsonl(session_id, project_dir):
    """Find the JSONL file for the active session.

    Primary: exact match via session_id + project_key (fast, precise).
    Fallback: most recently modified JSONL across all projects (robust).
    """
    home = os.path.expanduser("~")
    projects_base = os.path.join(home, ".claude", "projects")
    if not os.path.isdir(projects_base):
        return None

    # Primary: exact match using session_id and project directory
    if session_id and project_dir:
        key = derive_project_key(project_dir)
        exact = os.path.join(projects_base, key, session_id + ".jsonl")
        if os.path.isfile(exact):
            return exact

    # Fallback: most recently modified JSONL across all projects
    all_jsonl = []
    try:
        for d in os.listdir(projects_base):
            dp = os.path.join(projects_base, d)
            if os.path.isdir(dp):
                all_jsonl.extend(glob.glob(os.path.join(dp, "*.jsonl")))
    except (PermissionError, OSError):
        return None
    return max(all_jsonl, key=os.path.getmtime) if all_jsonl else None


def extract_usage(jsonl_path):
    """Extract the most recent usage data from the JSONL tail.

    Reads the last 200KB of the file for efficiency -- handles multi-MB logs
    without loading the entire file. Scans backwards for the last assistant
    message containing usage data.
    """
    tail_bytes = 200 * 1024

    try:
        with open(jsonl_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            start_pos = max(0, file_size - tail_bytes)
            f.seek(start_pos)
            chunk = f.read().decode("utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return None

    lines = chunk.split("\n")
    if start_pos > 0:
        lines = lines[1:]  # Skip potentially truncated first line

    for line in reversed(lines):
        # Fast pre-filter: skip lines without usage data
        if '"input_tokens"' not in line:
            continue
        try:
            msg = json.loads(line)
            if msg.get("type") == "assistant" and "message" in msg:
                usage = msg["message"].get("usage")
                if usage and "input_tokens" in usage:
                    return usage
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return None


def format_tokens(n):
    """Format token count compactly: 59595 -> '59.6K', 334 -> '334'."""
    if n >= 1000:
        return "{:.1f}K".format(n / 1000)
    return str(n)


def build_status_line(usage, config):
    """Build the terse status line from usage data and config.
    Returns (line, stats) where stats has pct, total, ceiling for state file.
    """
    inp = usage.get("input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # Context = everything sent to the model (input + all cached content)
    ctx_total = inp + cache_create + cache_read
    ceiling = config["context_ceiling"]
    pct = (ctx_total / ceiling * 100) if ceiling > 0 else 0

    # Progress bar (10 chars wide)
    bar_width = 10
    filled = min(int(pct / 100 * bar_width), bar_width)
    bar = "=" * filled + "." * (bar_width - filled)

    # Threshold tag and advice
    if pct >= config["critical_pct"]:
        tag = "CRITICAL "
        advice = " - compact or close session"
    elif pct >= config["warn_pct"]:
        tag = "WARN "
        advice = " - consider /compact"
    else:
        tag = ""
        advice = ""

    # Core status
    line = "[CTX] {tag}{total} / {ceil} ({pct:.0f}%) |{bar}|".format(
        tag=tag,
        total=format_tokens(ctx_total),
        ceil=format_tokens(ceiling),
        pct=pct,
        bar=bar
    )

    # Optional breakdown: cached vs new vs output
    if config.get("show_breakdown", True):
        line += " cache:{cached} new:{new} out:{out}".format(
            cached=format_tokens(cache_read),
            new=format_tokens(inp + cache_create),
            out=format_tokens(output_tokens)
        )

    # Optional per-turn cost estimate
    cost_usd = None
    pricing = config.get("cost_per_million", {})
    if pricing:
        cost_usd = (
            inp * pricing.get("input", 15.0) / 1_000_000
            + cache_create * pricing.get("cache_write", 18.75) / 1_000_000
            + cache_read * pricing.get("cache_read", 1.50) / 1_000_000
            + output_tokens * pricing.get("output", 75.0) / 1_000_000
        )
        if config.get("show_cost", False):
            line += " cost:${:.4f}".format(cost_usd)

    # Optional token in/out counts
    if config.get("show_tokens", False):
        line += " in:{inp} out:{out}".format(
            inp=format_tokens(inp + cache_create + cache_read),
            out=format_tokens(output_tokens)
        )

    line += advice

    stats = {
        "pct": round(pct, 1),
        "total": ctx_total,
        "ceiling": ceiling,
        "inp": inp,
        "cache_create": cache_create,
        "cache_read": cache_read,
        "out": output_tokens,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None
    }
    return line, stats


def write_state(script_dir, stats, session_id=""):
    """Write current context state for the PreToolUse gate to read.
    Includes session_id so the gate only blocks the session that wrote it.
    """
    state = {
        "session_id": session_id,
        "pct": stats["pct"],
        "total": stats["total"],
        "ceiling": stats["ceiling"],
        "cost_usd": stats.get("cost_usd"),
        "ts": time.time()
    }
    state_path = os.path.join(script_dir, ".ctx-monitor-state.json")
    try:
        with open(state_path, "w") as f:
            json.dump(state, f)
    except (PermissionError, OSError):
        pass


def append_history(script_dir, stats):
    """Append a reading to session history. Auto-truncates at 200 entries."""
    history_path = os.path.join(script_dir, ".ctx-monitor-history.jsonl")
    entry = json.dumps({
        "ts": time.time(),
        "pct": stats["pct"],
        "total": stats["total"],
        "inp": stats["inp"],
        "cache_create": stats["cache_create"],
        "cache_read": stats["cache_read"],
        "out": stats["out"],
        "cost_usd": stats.get("cost_usd")
    })
    try:
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
        # Truncate if over 200 lines
        with open(history_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 200:
            with open(history_path, "w", encoding="utf-8") as f:
                f.writelines(lines[-100:])
    except (PermissionError, OSError):
        pass


def main():
    """Main entry point. Designed to never raise -- all errors silently pass."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config = load_config(script_dir)

        if not config.get("enabled", True):
            return

        # Always read stdin first (drain pipe to prevent broken pipe errors)
        hook_input = read_hook_input()
        session_id = hook_input.get("session_id", "")
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")

        # Rate limit check -- returns immediately if within cooldown
        if not check_and_update_stamp(script_dir, config["cooldown_seconds"]):
            return

        # Find and parse the active session's JSONL
        jsonl_path = find_jsonl(session_id, project_dir)
        if not jsonl_path:
            return

        usage = extract_usage(jsonl_path)
        if not usage:
            return

        # Build status and persist state
        status, stats = build_status_line(usage, config)
        write_state(script_dir, stats, session_id)
        append_history(script_dir, stats)

        # Output as JSON additionalContext (PostToolUse protocol)
        # Plain stdout is discarded; additionalContext injects into Claude's context
        visual = "VISUAL:ON" if config.get("visual_indicator", False) else "VISUAL:OFF"
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": status + " [" + visual + "]"
            }
        }
        print(json.dumps(output))

    except Exception:
        pass  # Never break the session -- silent failure is correct behavior


if __name__ == "__main__":
    main()