**Claude finished @jaryl's task in 47s** —— [View job](https://github.com/luminalityai/luminality-web/actions/runs/RUN_ID)

---
### Review: chore/estate-revendor (PR #1261)

- [x] Gather context (read diff, changed files)
- [x] Understand request (code review)
- [x] Review `pre-push-prepare.sh` changes
- [x] Review `.agents/estate.lock` changes
- [x] Post review feedback

This is a mechanical re-vendor of `pre-push-prepare.sh` from `agent-estate` `071da7f`, pulled in via `estate-sync --estate`. Findings below focus on repo-side correctness of the sync rather than re-litigating the upstream lexer/resolver logic (that's already been through review at agent-estate#20/#21/#22, and its comments document each fixed edge case).

**Verified**
- `.agents/estate.lock` sha bump (`3dd9736` → `071da7f`) matches the PR description.
- The vendored file's `sha256` in the lock (`9c4cd8dce79bb821...`) matches `sha256sum .agents/hooks/pre-push-prepare.sh` locally — the lockfile is not stale relative to the vendored content. ✅
- `.agents/hooks.toml`'s `pre-push-prepare` entry (id, timeout, event wiring) is untouched, so no re-wiring is needed for this change.
- Diff is additive/rewrite only within the one file the PR claims to touch; no unrelated files changed.

**Comments (non-blocking)**

1. **No way to run the hook's own test suite in this repo.** The new header comment points at `hooks/tests/resolve-push-root.test.sh` and `hooks/tests/pre-push-prepare.test.sh`, but those tests live upstream in `agent-estate`, not vendored here — so this repo has no local way to verify the resolver behaves as documented (e.g., the `cd <dir> || exit` special case, the `GIT_DIR`/`GIT_WORK_TREE` skip, heredoc/`$(...)` handling). That's expected for a vendored single-file hook (per `AGENTS.md`'s note that estate hooks are vendored as single files), but worth flagging: correctness here is only as good as the upstream PR's own test coverage, and this repo can't independently catch a regression if a future re-vendor introduces one.
2. **Complexity/maintainability**: the lexer (`_rpr_lex`) and resolver (`resolve_push_root`) are now considerably larger and denser (bash regex-heavy state machine with mask tracking, heredoc scanning, etc.). This is appropriate for a security-relevant hook that must correctly identify "which checkout is being pushed," and the "skip rather than guess wrong" philosophy is sound and well-documented in the comments. Just noting that any future local modification to this file (rather than a re-vendor) would carry real risk of subtly breaking one of these edge cases — best to always update via `estate-sync` rather than hand-editing.
3. **Behavior change worth confirming intentional**: the old resolver fell back to `git -C` resolution even without a preceding `cd`, using the session cwd as the base. The new version still supports `-C`, but now the overall function first walks the *entire* and-or list for `control`/`complex` constructs and bails (`return 1`) more aggressively (e.g., any subshell/brace/compound command combined with a `cd` anywhere). This is a strictly more conservative (skip-more) posture, consistent with the PR description ("skips whenever it can't be certain") — just flagging it as a real behavior change so it's not a surprise if this hook starts skipping more often in complex push commands (e.g., scripts with `if`/`for` around a `git push`). That's the intended tradeoff per the linked issues, not a bug.

**Security/perf**: No security concerns — the change only *narrows* when the hook acts (more skip-safe, fewer certainty windows), which reduces risk of acting on the wrong checkout. No performance concerns for a pre-push hook; the lexer is O(n) with single-pass character consumption using batched regex runs (comment even calls out avoiding the quadratic char-at-a-time approach).

No code changes requested — this looks like a faithful, hash-verified re-vendor.
