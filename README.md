# .github

Org-level configuration and shared reusable GitHub Actions workflows for the
**luminalityai** organisation.

Ported from `fundbright/.github` (itself mirrored from `rarebit-one/.github`)
at the time of the luminalityai org bring-up. The shared pieces are kept in
sync across the three org `.github` repos by convention — adapt deliberately,
not by drift.

## Reusable workflows

Located under `.github/workflows/`. Consumed by other repos in this org via
`uses: luminalityai/.github/.github/workflows/<file>@<ref>`.

| Workflow | Purpose |
|----------|---------|
| `claude-code-review.yml` | Automated Claude review on pull requests. |

## Composite actions

Located under `.github/actions/`. Consumed via
`uses: luminalityai/.github/.github/actions/<name>@<ref>`.

| Action | Purpose |
|--------|---------|
| `agentic-run` | Run Claude Code on a custom prompt — the judgment + write layer for scheduled/cron agent workflows (e.g. in `delivery-ops`). |

## Required setup (human, one-time)

The Claude workflows authenticate with a **subscription OAuth token** stored as
an org-level Actions secret. Until it exists, the review workflow logs a
warning and skips — it never hard-fails.

```bash
claude setup-token   # prints a CLAUDE_CODE_OAUTH_TOKEN value
gh secret set CLAUDE_CODE_OAUTH_TOKEN --org luminalityai --visibility all
```

Optionally set the org-wide `CLAUDE_MODEL` Actions **variable** to override the
default model; the workflows fall back to a pinned literal when it is unset.

## Pinning convention for consumers

Third-party actions inside these workflows are **pinned to full commit SHAs**
(with a `# version` comment) so a moving tag can't silently change what runs.

Consumers referencing this repo's reusable workflows/actions use `@main` for
the initial cutover, then prefer pinning to a tag or SHA once this repo starts
tagging releases:

```yaml
uses: luminalityai/.github/.github/workflows/claude-code-review.yml@<sha>  # or @main initially
```

## Note on org Actions availability

The luminalityai org's private repos currently have GitHub Actions treated as
unavailable (no paid seats). Everything here is inert until that changes; the
token-check guard means wiring up callers early is safe.
