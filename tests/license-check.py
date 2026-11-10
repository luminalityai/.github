#!/usr/bin/env python3
"""Contract tests for .github/actions/license-check/license_check.py.

A licence gate's failure mode is a confident pass, so each "must block" case
sits beside a "must allow" control. Gem metadata comes from
tests/fixtures/license-check/gems via LICENSE_CHECK_RUBYGEMS_DIR; nothing here
touches the network.

Run: `python3 tests/license-check.py` (exits non-zero on failure).
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "license-check")
spec = importlib.util.spec_from_file_location(
    "license_check", os.path.join(ROOT, ".github", "actions", "license-check", "license_check.py"))
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)
os.environ["LICENSE_CHECK_RUBYGEMS_DIR"] = os.path.join(FIX, "gems")
os.environ.pop("GITHUB_STEP_SUMMARY", None)
os.environ.pop("GITHUB_ACTIONS", None)

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# Expression classification.
for expr, want in [
    ("MIT", "allow"), ("Apache 2.0", "allow"), ("The Apache Software License, Version 2.0", "allow"),
    ("(WTFPL OR MIT)", "allow"), ("Ruby OR GPL-2.0-only", "allow"), ("Apache-2.0 AND MIT", "allow"),
    ("MPL-2.0", "allow"), ("OFL-1.1", "allow"), ("CC-BY-4.0", "allow"),
    ("Android Software Development Kit License", "allow"),
    ("LGPL-3.0", "review"), ("GPL-3.0-or-later", "review"), ("EPL-2.0", "review"), ("WTFPL", "review"),
    ("GPL-2.0 WITH Classpath-exception-2.0", "review"), (None, "review"), ("", "review"),
    ("Brakeman Public Use License", "review"),
    ("AGPL-3.0-only", "block"), ("SSPL-1.0", "block"), ("BUSL-1.1", "block"),
    ("FSL-1.1-Apache-2.0", "block"), ("Elastic-2.0", "block"), ("PolyForm-Noncommercial-1.0.0", "block"),
    ("MIT AND Commons-Clause", "block"), ("CC-BY-NC-4.0", "block"), ("MIT AND AGPL-3.0", "block"),
]:
    check(f"classify({expr!r})", lc.classify(expr)[0], want)


def run_fixture(case):
    root = os.path.join(FIX, case)
    report = tempfile.mktemp(suffix=".json")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = lc.main(["--root", root, "--report", report])
    return code, {(r["ecosystem"], r["name"], r["version"]): r for r in json.load(open(report))}, buf.getvalue()


# Pass fixture: every class except block, so it exits 0.
code, res, out = run_fixture("pass")
check("pass exit", code, 0)
check("pass sentry excepted", res[("npm", "sentry", "0.45.0")]["class"], "except")
check("pass khroma no licence", res[("npm", "khroma", "2.1.0")]["class"], "review")
check("pass spark-md5 dual", res[("npm", "spark-md5", "3.0.2")]["class"], "allow")
check("pass rdoc dual", res[("rubygems", "rdoc", "8.1.0")]["class"], "allow")
check("pass device_detector", res[("rubygems", "device_detector", "1.1.3")]["class"], "review")
check("pass nokogiri platforms collapse",
      sum(1 for k in res if k[1] == "nokogiri"), 1)
check("pass swiftpm declared", res[("swiftpm", "https://github.com/getsentry/sentry-cocoa", "9.30.2")]["class"], "allow")
check("pass link skipped", any(k[1] == "local" for k in res), False)
check("pass summary names lockfiles", "`Gemfile.lock`" in out and "`package-lock.json`" in out, True)

# Block fixture: an SSPL package, and the excepted package relicensed to BUSL,
# which the exception's pinned licence no longer covers.
code, res, out = run_fixture("block")
check("block exit", code, 1)
check("block sspl", res[("npm", "mongo-thing", "1.0.0")]["class"], "block")
check("block relicensed exception lapses", res[("npm", "sentry", "0.46.0")]["class"], "block")
check("block control allowed", res[("npm", "react", "19.0.0")]["class"], "allow")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("license-check: all cases passed")
