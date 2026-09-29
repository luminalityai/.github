**Claude finished @jaryl's task in 1m 5s** —— [View job](https://github.com/luminalityai/luminality-web/actions/runs/RUN_ID)

---
### Claude finished the review <img src="https://github.com/user-attachments/assets/5ac382c7-e004-429b-8e35-7feb3e8f9c6f" width="14px" height="14px" style="vertical-align: middle; margin-left: 4px;" />

- [x] Gather context
- [x] Understand the request
- [x] Review `.agents/hooks/pre-push-prepare.sh`
- [x] Review `.agents/estate.lock`
- [x] Post review feedback

### Summary

This is a mechanical re-vendor of `pre-push-prepare.sh` from `rarebit-one/agent-estate@3dd9736` via `estate-sync --estate`, tightening how `resolve_push_root` figures out which checkout a push targets (agent-estate#18, #19). I verified `sha256sum .agents/hooks/pre-push-prepare.sh` matches the `estate.lock` entry (`6caabf2...`), so the vendored content and lock are consistent.

### Review of the resolver changes

Traced through the new logic in `resolve_push_root` (`.agents/hooks/pre-push-prepare.sh:141-239`) against the stated invariants:

- **Chained `cd`s compose** (`_resolve_dir`, line 107-115; loop at 180-206): each `cd` resolves against `eff`, the directory the previous one left. `cd .. && cd sibling && git push` correctly lands in `../sibling`. ✅
- **`cd` inside a pipeline stage is ignored**: `piped` is set per list-item based on whether it contains `|` (line 172-174), and the `cd` match is gated on `piped == 0` (line 180). Matches the documented subshell semantics. ✅
- **Unresolvable `cd` (`$VAR`, backticks, globs, `cd -`) marks `eff_known=0`**, and only a later *absolute* `cd` (or `~`) re-anchors it (lines 193-205) — a subsequent relative `cd` correctly stays unknown rather than silently resolving against a stale `eff`. ✅
- **A literal `cd` to a nonexistent dir leaves `eff` unchanged** (bash's real `cd` semantics), because `_resolve_dir` failing only flips `eff_known` for non-literal targets (line 198). ✅
- **An unresolved `-C` on the push segment is now terminal** (`toplevel=$(_try_toplevel "$cbase" "$dir") || return 1`, line 219) instead of falling back to another checkout — matches the PR's stated intent that a failed resolution should skip the hook, never guess. ✅
- Priority order (push segment's own `-C` → preceding `cd` chain → session cwd) is enforced correctly: the `-C` branch returns before the `saw_cd` fallback is reached (line 210-223 vs 225-235).

No correctness issues found in the logic itself. A couple of minor, low-risk observations (not blocking):

1. `_resolve_dir` (line 107-115) doesn't handle `~otheruser`-style tilde expansion (only bare `~` and `~/`), same limitation `_try_toplevel` already had before this PR — pre-existing, not introduced here.
2. `local lit=1 next` is declared fresh inside the `cd`-handling loop body (line 191) rather than once outside; harmless in bash (each `local` re-declares per iteration) but slightly unusual placement — purely stylistic.

### Process notes

- This hook is explicitly vendored/generated (`estate-sync --estate`) per the repo's `AGENTS.md`, so the actual design/edge-case review already happened upstream in agent-estate#18/#19 (referenced inline as "review finding" comments) — this PR is a faithful sync, not new logic authored here.
- Both changed files (`.agents/hooks/pre-push-prepare.sh`, `.agents/estate.lock`) are consistent with each other and with the stated source SHA.
- I did not run `shellcheck` or the hook's own test suite (`hooks/tests/pre-push-prepare.test.sh`, referenced in the script's comments but not present in this repo since only the rendered hook is vendored) — no sandboxed way to execute those here. If that suite lives in `agent-estate`, it should already have covered these cases before the sync.

No blocking issues. This looks safe to merge.
