# `agentic-run` — org-shared composite

Runs Claude Code on a custom prompt for the **cron/ops workflows** in
`delivery-ops`, via the org-standard
[`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action)
(subscription OAuth). It is the **judgment + write layer**: where a repo runs
deterministic collectors first (they emit JSON), this action reads that data and
produces the human-facing output (reports, issues, guarded draft PRs).

This is the single source of truth for the luminalityai org. It mirrors the
same-named composite in the sibling org `.github` repos (rarebit-one,
fundbright) — they are kept in sync by convention. Harden / fix the agent
invocation here and it lands once for all consumers in this org.

## Use it

```yaml
- name: <step name>
  uses: luminalityai/.github/.github/actions/agentic-run@main
  with:
    prompt-file: .github/prompts/<your-prompt>.md
    claude-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
    github-token: ${{ github.token }}            # or an app token for cross-repo writes
    model: ${{ vars.CLAUDE_MODEL || 'claude-opus-4-8' }}
    allowed-tools: "Bash,Read,Write,Edit,Glob,Grep"
```

## Input contract

| Input | Required | Default | Notes |
|-------|----------|---------|-------|
| `prompt` | no | `""` | Inline prompt. Ignored when `prompt-file` is set. |
| `prompt-file` | no | `""` | Path to a prompt file. Preferred over `prompt`. |
| `claude-oauth-token` | **yes** | — | `CLAUDE_CODE_OAUTH_TOKEN` (subscription auth). |
| `github-token` | no | job token | Pass an app token for cross-repo writes; defaults to `github.token`. |
| `model` | no | `claude-opus-4-8` | Pass `vars.CLAUDE_MODEL \|\| 'claude-opus-4-8'`. |
| `allowed-tools` | no | `Bash,Read,Write,Edit,Glob,Grep` | Comma-separated allowed tools. |

The action assembles the prompt with a hardened heredoc (random delimiter,
trailing-newline guard, `set -euo pipefail`), extends the agent's token with
`additional_permissions: actions: read`, and exports `GH_TOKEN` so the agent's
`gh`/`git` Bash calls authenticate.

> Tip: prefer pinning to a tag/SHA over `@main` for the consumer once the org
> repo starts tagging releases. `@main` is fine for the initial cutover.
