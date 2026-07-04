# .github

Org-level configuration and shared reusable GitHub Actions workflows for the
**luminalityai** organisation.

Ported from `fundbright/.github` (itself mirrored from `rarebit-one/.github`)
at the time of the luminalityai org bring-up. The shared pieces are kept in
sync across the sibling org `.github` repos by convention — adapt deliberately,
not by drift.

## GitHub Actions are live here

The luminalityai org is on the **GitHub Team plan with Actions enabled for all
private repos** (`enabled_repositories: all`). These workflows are **not** inert —
live org automation depends on them: the `luminality-release-bot` auto-fix PRs,
the daily Sentry `sentry-autofix` sweep, the Dependabot auto-lander, and Claude
code review all run through the workflows in this repo. Wiring up a caller in
any repo takes effect immediately.

Where a Claude workflow can't find its OAuth token it logs a `::warning::` and
skips rather than hard-failing (see [Required setup](#required-setup-human-one-time)),
so a repo can reference the reusables before its secrets are provisioned.

## Documentation

| Doc | Covers |
|-----|--------|
| [`docs/reusable-workflows.md`](docs/reusable-workflows.md) | Full input contract for the reusables + a deep dive on the actions-pinning self-healer (`pin-check` / `pin-sweep` / Dependabot). |
| [`docs/slack-release-notifications.md`](docs/slack-release-notifications.md) | The fail-soft Slack notify steps in `deploy-production.yml` / `sentry-release.yml` — what posts, when, and the `SLACK_BOT_TOKEN` / `SLACK_RELEASE_CHANNEL_ID` settings they read. |

## Reusable workflows

Located under `.github/workflows/`. Grouped by how they're triggered.

### Called by other org repos (`on: workflow_call`)

Consumed via `uses: luminalityai/.github/.github/workflows/<file>@<ref>`.

| Workflow | Purpose | Called by |
|----------|---------|-----------|
| `claude-code-review.yml` | Claude reviews a pull request's diff and posts findings. Runs (but step-gates out the LLM call) for Dependabot PRs so the required check still reports green. | Each repo's `claude-code-review-caller.yml` on `pull_request`. |
| `claude-agent.yml` | Runs Claude Code as an interactive/dispatched agent (the shared job behind `@claude` mentions and agent tasks). | Consumer repos' agent callers. |
| `deploy-production.yml` | Promotes `main → production` and cuts the release tag; posts the 🚀 "release started" Slack note and notifies Sentry (both fail-soft). | A repo's production caller — today only `luminality-web`. |
| `sentry-release.yml` | Creates a Sentry release and associates commits; optionally uploads frontend source maps (`has_frontend`). | A repo's release caller (and the deploy flow). |
| `reusable-weekly-maintenance.yml` | Per-stack (`rails` / `ruby-gem` / `node-lib` / `node-app` / `kmp`) weekly dependency + lint + security maintenance, opened as a PR. Referenced at `@v2`. | Each repo's weekly-maintenance caller. |
| `pin-check.yml` | PR gate that **fails** when a third-party action isn't SHA-pinned (zizmor `unpinned-uses` + a config-aware `pinact --check`), using an owner-scoped policy synthesized at runtime. | Each repo's `pin-check-caller.yml` on `pull_request`. |
| `dependabot-auto-merge.yml` | Auto-lander: enables squash auto-merge for Dependabot patch/minor bumps and for vetted SRE engine branches (`issue-worker/`, `ci-fix/`, `sentry-autofix/`). Reads metadata only — checks out no PR code. | Each repo's thin `dependabot-auto-merge.yml` caller on `pull_request_target`. |

### This repo's own self-callers / gates (run on PRs to `.github` itself)

| Workflow | Purpose |
|----------|---------|
| `claude-code-review-caller.yml` | Fires `claude-code-review.yml` (referenced as `./`) on PRs to this repo, so changes to the shared reusables get reviewed. Reference wiring consumer repos copy. |
| `pin-check-caller.yml` | Fires `pin-check.yml` on this repo's own PRs. Reference wiring consumer repos copy (pointing `uses:` at `@main` instead of `./`). |

### Org-level scheduled sweeps (one instance for the whole org)

Not reusable — single cron jobs that act across every org repo.

| Workflow | Purpose |
|----------|---------|
| `pin-sweep.yml` | Weekly cron (+ dispatch): runs `pinact` across every non-archived org repo and opens auto-mergeable fix PRs for any drift, via a release-bot App token and server-signed commits. The actuator to `pin-check.yml`'s sensor. |
| `dependabot-sweep.yml` | Every-6h cron: single-pass mop-up that complements the per-PR auto-lander — merges ready approved Dependabot PRs and rebases exactly one behind-branch PR per repo per pass. |
| `weekly-actions-audit.yml` | Weekly cron: audits Actions usage/waste across the org (including this repo's own workflows) and files deduped `ci-audit` issues in the SRE tracker. Issue-only sensor — opens no PRs. |

## Composite actions

Located under `.github/actions/`. Consumed via
`uses: luminalityai/.github/.github/actions/<name>@<ref>`.

| Action | Purpose |
|--------|---------|
| `agentic-run` | Run Claude Code on a custom prompt (inline or `prompt-file`) — the judgment + write layer for scheduled/cron agent workflows (e.g. in `delivery-ops`). Takes an OAuth token, an optional cross-repo App `github-token`, and `model` / `allowed-tools` / `effort` inputs. See its [`README.md`](.github/actions/agentic-run/README.md). |

## Required setup (human, one-time)

The Claude workflows authenticate with a **subscription OAuth token** stored as
an org-level Actions secret. Until it exists, the Claude steps log a warning and
skip — they never hard-fail.

```bash
claude setup-token   # prints a CLAUDE_CODE_OAUTH_TOKEN value
gh secret set CLAUDE_CODE_OAUTH_TOKEN --org luminalityai --visibility all
```

Optionally set the org-wide `CLAUDE_MODEL` Actions **variable** to override the
default model; the workflows fall back to a pinned literal when it is unset.

The cross-repo sweeps (`pin-sweep.yml`) and release-bot flows additionally use
the `luminality-release-bot` App — org variable `RELEASE_BOT_CLIENT_ID` + secret
`RELEASE_BOT_PRIVATE_KEY`. The Slack notify steps read `SLACK_BOT_TOKEN` /
`SLACK_RELEASE_CHANNEL_ID` (see [`docs/slack-release-notifications.md`](docs/slack-release-notifications.md)).

## Pinning convention for consumers

Third-party actions inside these workflows are **pinned to full commit SHAs**
(with a `# version` comment) so a moving tag can't silently change what runs.
The `pin-check.yml` gate enforces this on every PR; see
[`docs/reusable-workflows.md`](docs/reusable-workflows.md) for the full policy
(including the `anthropics/claude-code-action` main-branch exemption).

Consumers referencing this repo's reusable workflows/actions use `@main` for
the initial cutover, then prefer pinning to a tag or SHA once this repo starts
tagging releases:

```yaml
uses: luminalityai/.github/.github/workflows/claude-code-review.yml@<sha>  # or @main initially
```
