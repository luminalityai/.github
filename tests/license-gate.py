#!/usr/bin/env python3
"""Contract tests for .github/actions/license-gate (the Dependabot auto-merge licence gate).

A stub `gh` on PATH serves a fake pull request:
  * at the HEAD sha: a package-lock.json with an SSPL package, plus a
    .github/license-policy.json that tries to except it;
  * at the BASE sha: no policy file.
The gate must stage the lockfile from the head, take the policy from the base
(so the PR's own exception is ignored) and block. A second PR changing no
lockfile must pass, and a permissive lockfile must pass. Network-free.

Run: `python3 tests/license-gate.py` (exits non-zero on failure).
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCH = os.path.join(ROOT, ".github", "actions", "license-gate", "fetch_lockfiles.py")
CHECK = os.path.join(ROOT, ".github", "actions", "license-check", "license_check.py")

SSPL_LOCK = json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/mongo-thing": {"version": "1.0.0", "license": "SSPL-1.0"}}})
MIT_LOCK = json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/react": {"version": "19.0.0", "license": "MIT"}}})
SELF_EXCEPTION = json.dumps({"exceptions": [{"ecosystem": "npm", "name": "mongo-thing", "reason": "PR grants itself"}]})

STUB = r'''#!/usr/bin/env python3
import json, sys, os
fx = json.load(open(os.environ["GATE_FIXTURE"]))
args = sys.argv[1:]
url = [a for a in args if a.startswith("repos/")][0]
if url.endswith("/files"):
    for f in fx["files"]:
        print(json.dumps([f["filename"], f.get("status", "modified")]))
    sys.exit(0)
path, ref = url.split("/contents/", 1)[1].split("?ref=")
content = fx["contents"].get(ref, {}).get(path)
if content is None:
    sys.exit(1)
sys.stdout.write(content)
'''

failures = []


def gate(fixture):
    with tempfile.TemporaryDirectory() as t:
        bindir = os.path.join(t, "bin")
        os.makedirs(bindir)
        stub = os.path.join(bindir, "gh")
        open(stub, "w").write(STUB)
        os.chmod(stub, 0o755)
        fx = os.path.join(t, "fixture.json")
        json.dump(fixture, open(fx, "w"))
        out = os.path.join(t, "out")
        os.makedirs(out)
        env = {**os.environ, "PATH": bindir + os.pathsep + os.environ["PATH"], "GATE_FIXTURE": fx}
        env.pop("GITHUB_ACTIONS", None)
        env.pop("GITHUB_STEP_SUMMARY", None)
        staged = subprocess.run([sys.executable, "-I", FETCH, "o/r", "1", "HEAD", "BASE", out],
                                env=env, capture_output=True, text=True, check=True).stdout.split()
        policy_staged = os.path.exists(os.path.join(out, ".github", "license-policy.json"))
        if not staged:
            return "pass", staged, policy_staged
        r = subprocess.run([sys.executable, "-I", CHECK, "--root", out, "--lockfiles", " ".join(staged)],
                           env=env, capture_output=True, text=True)
        return ("pass" if r.returncode == 0 else "block"), staged, policy_staged


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


verdict, staged, policy = gate({
    "files": [{"filename": "package-lock.json"}, {"filename": ".github/license-policy.json"}, {"filename": "src/app.ts"}],
    "contents": {"HEAD": {"package-lock.json": SSPL_LOCK, ".github/license-policy.json": SELF_EXCEPTION}, "BASE": {}},
})
check("sspl blocks", verdict, "block")
check("only the lockfile is staged", staged, ["package-lock.json"])
check("the PR's own policy is not used", policy, False)

verdict, staged, _ = gate({"files": [{"filename": ".github/workflows/ci.yml"}], "contents": {"HEAD": {}, "BASE": {}}})
check("no lockfile passes", (verdict, staged), ("pass", []))

verdict, staged, policy = gate({
    "files": [{"filename": "web/package-lock.json"}, {"filename": "old/package-lock.json", "status": "removed"}],
    "contents": {"HEAD": {"web/package-lock.json": MIT_LOCK},
                 "BASE": {".github/license-policy.json": json.dumps({"exceptions": []})}},
})
check("permissive passes", verdict, "pass")
check("removed lockfiles are skipped", staged, ["web/package-lock.json"])
check("base policy is staged", policy, True)

verdict, _, _ = gate({
    "files": [{"filename": "package-lock.json"}],
    "contents": {"HEAD": {"package-lock.json": SSPL_LOCK},
                 "BASE": {".github/license-policy.json": json.dumps({"exceptions": [
                     {"ecosystem": "npm", "name": "mongo-thing", "license": "SSPL-1.0", "reason": "recorded on main"}]})}},
})
check("an exception already on the base branch applies", verdict, "pass")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("license-gate: all cases passed")
