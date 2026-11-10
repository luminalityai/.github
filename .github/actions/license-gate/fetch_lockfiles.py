#!/usr/bin/env python3
"""Stage a pull request's changed lockfiles (at its head) and the repo's licence
policy (at its BASE) in a directory, for license_check.py to classify.

Reads data through the GitHub API only; nothing from the pull request is
checked out or executed, so this is safe under pull_request_target. The policy
comes from the base commit so a pull request can't add its own exceptions.

Prints the staged lockfile paths, one per line (none: nothing to check).
Usage: fetch_lockfiles.py <owner/repo> <pr-number> <head-sha> <base-sha> <out-dir>
Needs `gh` authenticated (GH_TOKEN) with read access to the repository.
"""
import json
import os
import subprocess
import sys

LOCKFILES = {"package-lock.json", "Gemfile.lock", "Package.resolved"}
POLICY = ".github/license-policy.json"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def raw(repo, path, ref):
    """File content at ref, or None if it doesn't exist there (e.g. a deleted lockfile)."""
    r = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={ref}"],
        capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changed_files(repo, pr):
    out = gh("api", "--paginate", f"repos/{repo}/pulls/{pr}/files", "--jq", ".[] | [.filename, .status] | @json")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main(argv):
    repo, pr, head, base, out = argv
    staged = []
    for path, status in changed_files(repo, pr):
        if os.path.basename(path) not in LOCKFILES or status == "removed":
            continue
        if path.startswith("/") or ".." in path.split("/"):
            continue
        content = raw(repo, path, head)
        if content is None:
            continue
        dest = os.path.join(out, path)
        os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
        with open(dest, "w") as f:
            f.write(content)
        staged.append(path)
    policy = raw(repo, POLICY, base)
    if policy is not None:
        os.makedirs(os.path.join(out, ".github"), exist_ok=True)
        with open(os.path.join(out, POLICY), "w") as f:
            f.write(policy)
    print("\n".join(staged))


if __name__ == "__main__":
    main(sys.argv[1:])
