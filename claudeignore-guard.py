#!/usr/bin/env python3
"""
.claudeignore Guard Hook (PreToolUse on Read|Edit|Write|Glob|Grep)

Intercepts file operations and blocks access to files matching .claudeignore patterns.
Uses .gitignore-style pattern matching (fnmatch + directory globs).

Exit code 2 = hard block (file is ignored)
Exit code 0 = allow (file not ignored or no .claudeignore)
Exit code 1 = error (graceful continue)
"""

import json
import os
import re
import sys
from pathlib import Path


def find_claudeignore():
    """Find .claudeignore starting from CWD, walking up to root."""
    current = Path.cwd()
    while True:
        candidate = current / ".claudeignore"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def parse_claudeignore(filepath):
    """Parse .claudeignore into a list of (pattern, is_negation) tuples.

    Supports:
    - Blank lines and comments (#)
    - Negation patterns (!)
    - Directory-only patterns (trailing /)
    - Leading / for root-relative patterns
    - ** for recursive matching
    - Standard glob patterns (*, ?)
    """
    patterns = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                is_negation = False
                if line.startswith("!"):
                    is_negation = True
                    line = line[1:]

                patterns.append((line, is_negation))
    except Exception:
        return []

    return patterns


def _glob_to_regex(pattern):
    """Convert a .gitignore-style glob pattern to a regex string.

    Handles:
    - ** (matches everything including /)
    - *  (matches everything except /)
    - ?  (matches one char except /)
    - Character classes [...]
    - Literal escaping
    """
    i = 0
    n = len(pattern)
    regex = ""

    while i < n:
        c = pattern[i]

        if c == "*":
            # Check for **
            if i + 1 < n and pattern[i + 1] == "*":
                # **/ or ** at end
                if i + 2 < n and pattern[i + 2] == "/":
                    regex += r"(?:.+/)?"
                    i += 3
                    continue
                else:
                    regex += r".*"
                    i += 2
                    continue
            else:
                regex += r"[^/]*"
        elif c == "?":
            regex += r"[^/]"
        elif c == "[":
            # Pass through character class
            j = i + 1
            if j < n and pattern[j] == "!":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            regex += pattern[i : j + 1]
            i = j
        elif c in r"\{}()+|^$.":
            regex += "\\" + c
        else:
            regex += c

        i += 1

    return regex


def matches_pattern(rel_path, pattern):
    """Check if a relative path matches a single .claudeignore pattern.

    Logic follows .gitignore semantics:
    - If pattern has no /, it matches the filename only (basename match)
    - If pattern has /, it matches the full path from root
    - Trailing / means directory only (we treat all paths as potential dirs)
    - Leading / anchors to root
    """
    # Normalize
    rel_path = rel_path.lstrip("/")
    original_pattern = pattern

    # Trailing slash = directory-only (strip it, still match)
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    # Leading slash = root-anchored
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern.lstrip("/")

    regex_str = _glob_to_regex(pattern)

    # If pattern contains / (after stripping leading), match full path
    # Otherwise, match against any path component (basename behavior)
    if "/" in pattern or anchored:
        # Full-path match: pattern must match from root
        full_re = "^" + regex_str + "(?:/.*)?$"
    else:
        # Basename match: match against filename or any directory component
        full_re = "(?:^|/)" + regex_str + "(?:/.*)?$"

    try:
        return bool(re.search(full_re, rel_path))
    except re.error:
        return False


def is_ignored(rel_path, patterns):
    """Check if a path is ignored based on .claudeignore patterns.

    Processes patterns in order (last match wins), respecting negation.
    """
    ignored = False

    for pattern, is_negation in patterns:
        if matches_pattern(rel_path, pattern):
            ignored = not is_negation

    return ignored


def extract_paths_from_input(tool_name, tool_input):
    """Extract file/directory paths from tool input based on tool type."""
    paths = []

    if tool_name in ("Read", "Edit", "Write"):
        fp = tool_input.get("file_path", "")
        if fp:
            paths.append(fp)

    elif tool_name == "Glob":
        # Glob has pattern + optional path (directory)
        p = tool_input.get("path", "")
        if p:
            paths.append(p)
        # Also check if the pattern itself targets an ignored dir
        pat = tool_input.get("pattern", "")
        if pat and not pat.startswith("*"):
            # e.g. "node_modules/**/*.js" — extract the leading directory
            parts = pat.split("/")
            if len(parts) > 1:
                paths.append(parts[0])

    elif tool_name == "Grep":
        p = tool_input.get("path", "")
        if p:
            paths.append(p)

    return paths


def make_relative(abs_path, claudeignore_dir):
    """Convert an absolute path to a path relative to the .claudeignore location."""
    try:
        return str(Path(abs_path).resolve().relative_to(claudeignore_dir.resolve()))
    except ValueError:
        # Path is outside the project — not subject to .claudeignore
        return None


def main():
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only guard file-access tools
    if tool_name not in ("Read", "Edit", "Write", "Glob", "Grep"):
        sys.exit(0)

    # Find .claudeignore
    claudeignore_path = find_claudeignore()
    if not claudeignore_path:
        sys.exit(0)  # No .claudeignore — allow everything

    claudeignore_dir = claudeignore_path.parent
    patterns = parse_claudeignore(claudeignore_path)
    if not patterns:
        sys.exit(0)

    # Extract paths from the tool input
    paths = extract_paths_from_input(tool_name, tool_input)
    if not paths:
        sys.exit(0)

    # Check each path
    blocked_paths = []
    for p in paths:
        rel = make_relative(p, claudeignore_dir)
        if rel and is_ignored(rel, patterns):
            blocked_paths.append(p)

    if blocked_paths:
        print("=" * 60, file=sys.stderr)
        print("BLOCKED BY .claudeignore", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"\nTool: {tool_name}", file=sys.stderr)
        print(f"Blocked path(s):", file=sys.stderr)
        for bp in blocked_paths:
            print(f"  - {bp}", file=sys.stderr)
        print(
            "\nThis file matches a pattern in .claudeignore and must not be accessed.",
            file=sys.stderr,
        )
        print(
            "If you need to access it, ask the user to override.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("REQUIRED BEHAVIOR: STOP. Do NOT attempt alternative", file=sys.stderr)
        print("approaches to access this file. Do NOT say 'let me", file=sys.stderr)
        print("work around it'. Report this block to the user and", file=sys.stderr)
        print("wait for their instructions.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(2)  # Hard block

    sys.exit(0)


if __name__ == "__main__":
    main()
