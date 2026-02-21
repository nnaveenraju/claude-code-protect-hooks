#!/usr/bin/env python3
"""
Hook Guardian (PreToolUse on Edit|Write|Bash)

Prevents Claude from tampering with its own safety hooks.
Three protections:

1. PROTECTED FILES — Blocks Edit/Write to hook scripts, settings.json,
   and .claudeignore (the files that define the safety boundary).
2. BYPASS FLAGS — Blocks Bash commands containing --no-verify,
   --no-gpg-sign, or other hook-skipping flags.
3. DESTRUCTIVE GIT — Blocks force push, reset --hard, clean -fd,
   and other commands that destroy work.

Exit code 2 = hard block
Exit code 0 = allow
"""

import json
import re
import sys
from pathlib import Path

# ── Protected file patterns (Edit/Write) ──────────────────────────
# Paths ending with any of these are off-limits.
PROTECTED_SUFFIXES = [
    "hooks/hook-guardian.py",
    "hooks/claudeignore-guard.py",
    "hooks/secret-scanner.py",
    "hooks/code-quality.py",
    "hooks/story-validator.py",
    "settings.json",
    ".claudeignore",
]

# ── Blocked Bash patterns ─────────────────────────────────────────
BLOCKED_BASH_PATTERNS = [
    # Hook bypass flags
    (r"--no-verify", "Hook bypass flag --no-verify"),
    (r"--no-gpg-sign", "Hook bypass flag --no-gpg-sign"),
    # Destructive git commands
    (r"git\s+push\s+.*--force(?!-with-lease)", "Force push (use --force-with-lease instead)"),
    (r"git\s+reset\s+--hard", "Destructive reset --hard"),
    (r"git\s+clean\s+-[a-zA-Z]*f", "Destructive git clean"),
    (r"git\s+checkout\s+\.\s*$", "Destructive git checkout ."),
    (r"git\s+restore\s+\.\s*$", "Destructive git restore ."),
    # Removing or renaming hook files via bash
    (r"(?:rm|mv|unlink)\s+.*hooks/(?:hook-guardian|claudeignore-guard|secret-scanner|code-quality|story-validator)", "Removing/moving hook files"),
    # Editing settings.json via sed/awk/perl to strip hooks
    (r"(?:sed|awk|perl)\s+.*settings\.json", "Modifying settings.json via sed/awk/perl"),
    # Piping/redirecting over protected files
    (r">\s*.*(?:settings\.json|\.claudeignore)", "Overwriting protected file via redirect"),
    (r"tee\s+.*(?:settings\.json|\.claudeignore)", "Overwriting protected file via tee"),
]


def check_protected_file(tool_input):
    """Check if an Edit/Write targets a protected file."""
    filepath = tool_input.get("file_path", "")
    if not filepath:
        return None

    # Normalize
    filepath = str(Path(filepath).resolve())

    for suffix in PROTECTED_SUFFIXES:
        if filepath.endswith(suffix):
            return filepath

    return None


def check_bash_command(tool_input):
    """Check if a Bash command contains bypass or destructive patterns."""
    command = tool_input.get("command", "")
    if not command:
        return None

    for pattern, description in BLOCKED_BASH_PATTERNS:
        if re.search(pattern, command):
            return description

    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # ── Check Edit/Write to protected files ──
    if tool_name in ("Edit", "Write"):
        blocked = check_protected_file(tool_input)
        if blocked:
            print("=" * 60, file=sys.stderr)
            print("BLOCKED — PROTECTED FILE", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(f"\nTool: {tool_name}", file=sys.stderr)
            print(f"File: {blocked}", file=sys.stderr)
            print(
                "\nThis file is part of the safety boundary (hooks, settings,",
                file=sys.stderr,
            )
            print(
                "or .claudeignore) and cannot be modified by Claude.",
                file=sys.stderr,
            )
            print("Only the user may edit protected files.", file=sys.stderr)
            print("", file=sys.stderr)
            print("REQUIRED BEHAVIOR: STOP. Do NOT attempt alternative", file=sys.stderr)
            print("approaches to achieve the same result. Do NOT say", file=sys.stderr)
            print("'let me work around it'. Report this block to the", file=sys.stderr)
            print("user and wait for their instructions.", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            sys.exit(2)

    # ── Check Bash for bypass / destructive commands ──
    if tool_name == "Bash":
        blocked = check_bash_command(tool_input)
        if blocked:
            print("=" * 60, file=sys.stderr)
            print("BLOCKED — UNSAFE COMMAND", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(f"\nReason: {blocked}", file=sys.stderr)
            print(f"Command: {tool_input.get('command', '')[:200]}", file=sys.stderr)
            print(
                "\nThis command would bypass safety hooks or destroy work.",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
            print("REQUIRED BEHAVIOR: STOP. Do NOT attempt alternative", file=sys.stderr)
            print("approaches to achieve the same result. Do NOT say", file=sys.stderr)
            print("'let me work around it'. Report this block to the", file=sys.stderr)
            print("user and wait for their instructions.", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
