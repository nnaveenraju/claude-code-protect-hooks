# Claude Code Safety Hooks

A set of five automated hooks that enforce security, quality, and access control in Claude Code projects. They run via `settings.json` — no manual invocation needed.

## Hooks

### `claudeignore-guard.py` — File Access Control
**Event:** PreToolUse (Read, Edit, Write, Glob, Grep)

Blocks Claude from reading, editing, or searching files that match patterns in `.claudeignore`. Uses full `.gitignore` syntax — globs, `**` recursion, negation (`!`), directory patterns, and basename matching. Walks up from CWD to find the nearest `.claudeignore`, so it works at any depth.

### `hook-guardian.py` — Anti-Tamper Protection
**Event:** PreToolUse (Edit, Write, Bash)

Prevents Claude from disabling its own safety net. Protects three attack surfaces:

- **File edits** — blocks modifications to hook scripts, `settings.json`, and `.claudeignore`
- **Bypass flags** — catches `--no-verify`, `--no-gpg-sign`, and similar
- **Destructive commands** — blocks `git reset --hard`, `git push --force`, `git clean -f`, `rm`/`mv` on hook files, `sed`/`awk` on settings, and shell redirects over protected files

## Exit Codes

All hooks follow the same convention:

| Code | Meaning | Effect |
|------|---------|--------|
| `0` | Clean | Operation proceeds normally |
| `1` | Hook error | Operation proceeds (graceful degradation) |
| `2` | Blocked | Operation is stopped before execution |

## Installation

### Per-project (recommended for teams)

Copy the `hooks/` folder into your project root and add the hook configuration to `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|Glob|Grep",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.claude/hooks/claudeignore-guard.py",
          "timeout": 10,
          "statusMessage": "Checking .claudeignore..."
        }]
      },
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.claude/hooks/hook-guardian.py",
          "timeout": 10,
          "statusMessage": "Checking safety boundary..."
        }]
      }
    ]
  }
}
```

### Global (applies to all projects)

Place the hook scripts in `~/.claude/hooks/` and add the configuration to `~/.claude/settings.json` with absolute paths. The `claudeignore-guard` gracefully does nothing for projects without a `.claudeignore` file.

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## .claudeignore

Create a `.claudeignore` file in your project root using `.gitignore` syntax. The `claudeignore-guard` hook will enforce it automatically. Example:

```gitignore
# Secrets
.env
.env.*
!.env.example
*.pem

# Dependencies
node_modules/
vendor/
__pycache__/

# Build output
dist/
build/

# Binary files
*.png
*.jpg
*.pdf
*.zip
```

## License

MIT
