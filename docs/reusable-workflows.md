# Reusable Workflows

This repo hosts reusable GitHub Actions workflows shared across luminalityai
repos. Consumers reference workflows here via:

```yaml
uses: luminalityai/.github/.github/workflows/<name>.yml@main
```

## Actions-pinning self-healer

Third-party GitHub Actions across the estate are SHA-pinned (via `pinact`).
Three pieces keep that compliant over time:

- **`pin-check.yml`** — a reusable (`workflow_call`) PR gate. It runs
  [zizmor](https://docs.zizmor.sh) (the Actions security auditor) and blocks the
  PR on its `unpinned-uses` finding, plus a second, config-aware `pinact --check`.
  zizmor's full audit is surfaced as non-blocking log; only pinning blocks the
  merge. First-party org actions pinned at `@main`/`@vN` are allowed — the gate
  reads the repo's `.github/zizmor.yml` if present, else synthesizes an
  owner-scoped policy from `github.repository_owner` (`<owner>/*: ref-pin`,
  `*: hash-pin`), so it's portable to any repo with no per-repo config. The
  `pinact --check` leg does the same: it writes an owner-scoped config to
  `/tmp/pinact.yaml` **at runtime** and runs `pinact run --check -c /tmp/pinact.yaml`,
  so it never depends on a committed per-repo `.pinact.yaml`.

  Consume it from a PR workflow (see `pin-check-caller.yml` here for the
  reference wiring):

  ```yaml
  jobs:
    pin-check:
      uses: luminalityai/.github/.github/workflows/pin-check.yml@main
  ```

- **`pin-sweep.yml`** — a scheduled (`schedule` weekly + `workflow_dispatch`)
  self-healer that lives only in this org `.github` repo. It enumerates every
  non-archived org repo (via the release-bot App token), runs `pinact run`
  against the same runtime-synthesized owner-scoped config, and — if pinact
  produces a diff — opens a squash-auto-merge PR on that repo with the fix. Auth
  + cross-repo mechanics mirror luminality-sre's `ci-fix-sweep.yml`:
  `actions/create-github-app-token` (`vars.RELEASE_BOT_CLIENT_ID` +
  `secrets.RELEASE_BOT_PRIVATE_KEY`, `owner: luminalityai`), a repo matrix,
  per-target checkout, and a server-signed commit created via the API (push to
  the `pin-fix/*` branch is unsigned, then HEAD is replaced with a signed commit
  and the ref re-pointed) so PRs land even on require-signed-commits repos.
  `workflow_dispatch` supports `dry_run` (plan only) and `only_repo` (scope to
  one repo for validation).

- **Dependabot `github-actions`** — this repo's `.github/dependabot.yml` enables
  the weekly `github-actions` ecosystem, so the pinned SHAs get bumped as new
  releases land. **Fan-out note:** each consumer repo needs this same
  `github-actions` block in its *own* `.github/dependabot.yml` — the sweep pins,
  Dependabot freshens; they're complementary.

### The `anthropics/claude-code-action` exemption (org convention)

We pin `anthropics/claude-code-action` to a **main-branch commit** (ahead of the
latest release, for a thinking-block 400 fix — see rarebit-ops#119), annotated
`# main@<version>` rather than `# v<semver>`. `pinact --check` flags that comment
style as a missing semver comment and would try to "correct" the deliberate main
pin. The consistent handling — baked into the **runtime-synthesized** pinact
config both `pin-check.yml` and `pin-sweep.yml` write to `/tmp/pinact.yaml` — is
to list it under `ignore_actions`:

```yaml
version: 3
ignore_actions:
  - name: luminalityai/.*      # first-party org actions (moving @main/@vN OK)
    ref: .*
  - name: \./.*                # local composite actions (no upstream ref)
    ref: .*
  - name: anthropics/claude-code-action
    ref: .*
```

It **stays SHA-pinned** — this only silences pinact's semver-comment nit;
zizmor's `unpinned-uses` still enforces the full SHA.

### Per-repo adoption (incremental)

The `pin-sweep.yml` actuator already covers **every** non-archived luminalityai
repo automatically — no per-repo wiring needed for the healer. The `pin-check.yml`
PR gate is opt-in per repo: add a caller (copying `pin-check-caller.yml`, pointing
`uses:` at `luminalityai/.github/.github/workflows/pin-check.yml@main`). The
recommended first adopter is **luminality-web** (the busiest repo); roll the gate
out to the rest incrementally rather than adding 40+ callers at once.
