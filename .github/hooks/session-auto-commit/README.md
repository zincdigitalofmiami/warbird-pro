---
name: 'Session Git Status'
description: 'Reports pending git changes when a Copilot coding agent session ends'
tags: ['automation', 'git', 'productivity']
---

# Session Git Status Hook

Reports pending git changes when a GitHub Copilot coding agent session ends.
This Warbird copy is report-only and must not stage, commit, bypass hooks, or
push automatically.

## Overview

This hook runs at the end of each Copilot coding agent session and:

- Detects if there are uncommitted changes
- Prints `git status --short`
- Leaves all staging, commits, and pushes to the repo's normal gated workflow

## Features

- **Visibility**: Surfaces pending work at session end
- **Repo-safe behavior**: Does not mutate git state
- **Gate-compatible workflow**: Preserves Warbird pre-commit and pre-push hooks

## Installation

1. Copy this hook folder to your repository's `.github/hooks/` directory:
   ```bash
   cp -r hooks/session-auto-commit .github/hooks/
   ```

2. Ensure the script is executable:
   ```bash
   chmod +x .github/hooks/session-auto-commit/auto-commit.sh
   ```

3. Commit the hook configuration to your repository's default branch

## Configuration

The hook is configured in `hooks.json` to run on the `sessionEnd` event:

```json
{
  "version": 1,
  "hooks": {
    "sessionEnd": [
      {
        "type": "command",
        "bash": ".github/hooks/session-auto-commit/auto-commit.sh",
        "timeoutSec": 30
      }
    ]
  }
}
```

## How It Works

1. When a Copilot coding agent session ends, the hook executes
2. Checks if inside a Git repository
3. Detects uncommitted changes using `git status`
4. Prints a short status report
5. Exits without mutating the repository

## Customization

You can customize the hook by modifying `auto-commit.sh`:

- **Status Format**: Add branch, stash, or upstream information
- **Notifications**: Add desktop notifications or Slack messages

## Disabling

To temporarily disable auto-commits:

1. Remove or comment out the `sessionEnd` hook in `hooks.json`
2. Or set an environment variable: `export SKIP_AUTO_COMMIT=true`

## Notes

- The hook intentionally avoids automatic commits and pushes.
- Do not add bypasses around `.githooks` or `scripts/guards/warbird-agent-precheck.sh`.
- Works with both Copilot coding agent and GitHub Copilot CLI
