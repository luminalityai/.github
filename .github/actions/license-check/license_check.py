#!/usr/bin/env python3
"""Classify every package resolved in a repo's lockfiles against the org licence policy.

Reads lockfiles only (nothing is installed or built):

    package-lock.json   npm lockfile v2/v3, `license` field per package
    Gemfile.lock        resolved gems; licences from the RubyGems v2 API
    Package.resolved    SwiftPM pins; no licence metadata, so each pin needs a
                        `declared` entry in the repo policy file or it is flagged

Each package lands in one of four classes:

    allow    on the org allowlist
    review   GPL/LGPL/EPL, or no detectable licence: a warning, never a failure
    block    source-available or noncommercial (AGPL, SSPL, BUSL, FSL, ...)
    except   would be review/block, but the repo policy records a reason

Exit status: 1 when any package is `block`, else 0. Callers run the job with
`continue-on-error: true` while the check is advisory.

The repo policy file (JSON, optional) adds two things the lockfiles can't say:

    {"exceptions": [{"ecosystem": "npm", "name": "sentry", "license": "FSL-1.1-Apache-2.0",
                     "reason": "Sentry CLI, build-time only"}],
     "declared":   [{"ecosystem": "swiftpm", "name": "https://github.com/getsentry/sentry-cocoa",
                     "license": "MIT", "source": "LICENSE.md at 9.30.2"}]}

An exception with a `license` only applies while the resolved licence still
matches it, so a relicense surfaces again. `declared` supplies a licence for a
package whose lockfile carries none; it is classified like any other licence.

Stdlib only. Set LICENSE_CHECK_RUBYGEMS_DIR to a directory of
`<name>-<version>.json` files to read gem metadata offline (tests do this).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ALLOW = {
    "MIT", "MIT-0", "ISC", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "Apache-2.0",
    "BlueOak-1.0.0", "Unlicense", "CC0-1.0", "Python-2.0", "PSF-2.0", "Ruby", "Zlib",
    "MPL-2.0", "OFL-1.1", "CC-BY-4.0",
}
# CC-BY-4.0 is allowed for data only (caniuse-lite and the like); the report notes it.
DATA_ONLY = {"CC-BY-4.0"}
# Google's proprietary SDK terms already in use (Play services, Billing, Firebase).
GOOGLE_SDK = {"Android-SDK-License"}
BLOCK_PATTERNS = [
    r"\bAGPL", r"\bSSPL", r"\bBUSL", r"\bBSL-1\.1\b", r"Business Source", r"Commons[- ]Clause",
    r"\bElastic-", r"Elastic License", r"PolyForm", r"\bFSL-", r"Functional Source",
    r"\bCC-BY-NC", r"non-?commercial", r"Server Side Public",
]
REVIEW_PATTERNS = [r"\bL?GPL", r"\bEPL-", r"Eclipse Public"]

ALIASES = {
    "apache 2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0",
    "the apache software license, version 2.0": "Apache-2.0",
    "the apache license, version 2.0": "Apache-2.0",
    "mit license": "MIT", "the mit license": "MIT", "expat": "MIT",
    "bsd-2": "BSD-2-Clause", "bsd 2-clause": "BSD-2-Clause", "2-clause bsd": "BSD-2-Clause",
    "bsd-3": "BSD-3-Clause", "bsd 3-clause": "BSD-3-Clause", "3-clause bsd": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause", "isc license": "ISC", "python-2.0": "Python-2.0",
    "android software development kit license": "Android-SDK-License",
}


def canon(token):
    t = token.strip().strip("()").strip()
    return ALIASES.get(t.lower(), t)


def classify_one(lic):
    if not lic:
        return "review", "no licence detected"
    for p in BLOCK_PATTERNS:
        if re.search(p, lic, re.I):
            return "block", "source-available or noncommercial"
    if lic in ALLOW:
        return "allow", "data only" if lic in DATA_ONLY else ""
    if lic in GOOGLE_SDK:
        return "allow", "Google SDK terms"
    for p in REVIEW_PATTERNS:
        if re.search(p, lic, re.I):
            return "review", "copyleft: check use and distribution"
    return "review", "unrecognised licence"


RANK = {"allow": 0, "review": 1, "block": 2}


def classify(expr):
    """Classify an SPDX-ish expression. OR takes the best option, AND the worst.

    A RubyGems `licenses` list arrives joined with " OR ": the gemspec field
    lists the licences a gem is offered under (Ruby's own "Ruby OR BSD-2-Clause").
    """
    if expr is None or not str(expr).strip():
        return classify_one("")
    expr = str(expr).strip()
    if expr.startswith("(") and expr.endswith(")") and expr.count("(") == 1:
        expr = expr[1:-1]
    ors = re.split(r"\s+OR\s+", expr)
    if len(ors) > 1:
        return min((classify(o) for o in ors), key=lambda r: RANK[r[0]])
    ands = re.split(r"\s+AND\s+", expr)
    if len(ands) > 1:
        return max((classify(a) for a in ands), key=lambda r: RANK[r[0]])
    if re.search(r"\s+WITH\s+", expr):
        base = re.split(r"\s+WITH\s+", expr)[0]
        cls, why = classify_one(canon(base))
        return cls, (why + "; with exception").strip("; ")
    return classify_one(canon(expr))


def read_npm(path):
    data = json.load(open(path))
    out = []
    for key, p in (data.get("packages") or {}).items():
        if not key or p.get("link"):
            continue
        name = p.get("name") or key.split("node_modules/")[-1]
        lic = p.get("license")
        if isinstance(lic, dict):
            lic = lic.get("type")
        if lic is None and isinstance(p.get("licenses"), list):
            lic = " OR ".join(x.get("type", "") if isinstance(x, dict) else str(x) for x in p["licenses"])
        scope = "dev" if p.get("dev") or p.get("devOptional") else "prod"
        out.append({"ecosystem": "npm", "name": name, "version": p.get("version", ""),
                    "license": lic, "scope": scope, "lockfile": path})
    return out


PLATFORM = re.compile(r"-(x86|x64|arm|aarch|universal|java|mingw|mswin)")


def read_gems(path):
    out, section = [], None
    for line in open(path):
        if re.match(r"^[A-Z]", line):
            section = line.strip()
            continue
        m = re.match(r"^    ([^ ]+) \(([^)]+)\)$", line.rstrip("\n"))
        if m and section in ("GEM", "GIT", "PATH"):
            name, ver = m.groups()
            pm = PLATFORM.search(ver)
            if pm:
                ver = ver[: pm.start()]
            out.append({"ecosystem": "rubygems", "name": name, "version": ver, "license": None,
                        "scope": "", "lockfile": path, "source": section})
    seen, uniq = set(), []
    for g in out:
        k = (g["name"], g["version"])
        if k not in seen:
            seen.add(k)
            uniq.append(g)
    return uniq


def gem_license(name, version):
    offline = os.environ.get("LICENSE_CHECK_RUBYGEMS_DIR")
    if offline:
        f = os.path.join(offline, f"{name}-{version}.json")
        if not os.path.exists(f):
            return None, "no offline metadata"
        meta = json.load(open(f))
    else:
        url = f"https://rubygems.org/api/v2/rubygems/{name}/versions/{version}.json"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=20) as r:
                    meta = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, "not on rubygems.org"
                time.sleep(2 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(2 * (attempt + 1))
        else:
            return None, "RubyGems lookup failed"
    lics = [x for x in (meta.get("licenses") or []) if x]
    return (" OR ".join(lics) if lics else None), ""


def read_swiftpm(path):
    data = json.load(open(path))
    pins = data.get("pins") or (data.get("object") or {}).get("pins") or []
    return [{"ecosystem": "swiftpm", "name": p.get("location") or p.get("repositoryURL") or p.get("identity"),
             "version": (p.get("state") or {}).get("version") or (p.get("state") or {}).get("revision", ""),
             "license": None, "scope": "prod", "lockfile": path} for p in pins]


READERS = {"package-lock.json": read_npm, "Gemfile.lock": read_gems, "Package.resolved": read_swiftpm}
SKIP_DIRS = {"node_modules", ".git", "vendor", ".worktrees", "build", "dist", "tmp"}


def discover(root):
    found = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            if f in READERS:
                found.append(os.path.relpath(os.path.join(d, f), root))
    return found


def matches(entry, pkg):
    return entry.get("ecosystem") == pkg["ecosystem"] and entry.get("name") == pkg["name"] and (
        not entry.get("version") or entry["version"] == pkg["version"])


def run(root, lockfiles, policy):
    pkgs = []
    for lf in lockfiles:
        reader = READERS[os.path.basename(lf)]
        cwd = os.getcwd()
        os.chdir(root)
        try:
            pkgs += reader(lf)
        finally:
            os.chdir(cwd)
    results = []
    for p in pkgs:
        note = ""
        if p["ecosystem"] == "rubygems" and p.get("source") == "GEM":
            p["license"], note = gem_license(p["name"], p["version"])
        elif p["ecosystem"] == "rubygems":
            note = f"{p['source']} source: no registry metadata"
        dec = next((d for d in policy.get("declared", []) if matches(d, p)), None)
        if dec and not p["license"]:
            p["license"] = dec["license"]
            note = f"declared: {dec.get('source', '')}".strip()
        cls, why = classify(p["license"])
        exc = next((e for e in policy.get("exceptions", []) if matches(e, p)), None)
        if exc and cls != "allow" and (not exc.get("license") or exc["license"] == (p["license"] or "")):
            cls, why = "except", exc.get("reason", "")
        p.update({"class": cls, "why": "; ".join(x for x in (why, note) if x)})
        results.append(p)
    return results


def summary(results, lockfiles):
    counts = {c: sum(1 for r in results if r["class"] == c) for c in ("allow", "review", "block", "except")}
    lines = ["### Licence check", "",
             f"Lockfiles: {', '.join(f'`{x}`' for x in lockfiles) or 'none found'}", "",
             f"**{len(results)}** packages: {counts['allow']} allowed, {counts['except']} recorded exceptions, "
             f"{counts['review']} to review, {counts['block']} blocked.", ""]
    rows = [r for r in results if r["class"] != "allow"]
    if rows:
        lines += ["| Class | Ecosystem | Package | Version | Licence | Scope | Note |", "|---|---|---|---|---|---|---|"]
        order = {"block": 0, "review": 1, "except": 2}
        for r in sorted(rows, key=lambda r: (order[r["class"]], r["ecosystem"], r["name"], r["version"])):
            lic = (r["license"] or "none").replace("|", "\\|")
            lines.append(f"| {r['class']} | {r['ecosystem']} | `{r['name']}` | {r['version']} | {lic} | "
                         f"{r['scope']} | {r['why'].replace('|', '/')} |")
    lines += ["", "Policy: allow permissive + MPL/OFL/CC-BY (data); review GPL/LGPL/EPL/unknown; "
              "block AGPL/SSPL/BUSL/FSL/Commons Clause/Elastic/PolyForm/noncommercial. "
              "Gradle has no lockfile and is not covered."]
    return "\n".join(lines) + "\n", counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--lockfiles", default="", help="newline/space separated; default: discover")
    ap.add_argument("--policy", default=".github/license-policy.json")
    ap.add_argument("--report", default="", help="write the full JSON result here")
    a = ap.parse_args(argv)
    lockfiles = a.lockfiles.split() or discover(a.root)
    policy_path = os.path.join(a.root, a.policy)
    policy = json.load(open(policy_path)) if os.path.exists(policy_path) else {}
    results = run(a.root, lockfiles, policy)
    text, counts = summary(results, lockfiles)
    sys.stdout.write(text)
    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a") as f:
            f.write(text)
    if os.environ.get("GITHUB_ACTIONS"):
        for r in results:
            if r["class"] in ("review", "block"):
                level = "error" if r["class"] == "block" else "warning"
                print(f"::{level} title=Licence {r['class']}::{r['ecosystem']} {r['name']}@{r['version']}: "
                      f"{r['license'] or 'none'} ({r['why']})")
    if a.report:
        json.dump(results, open(a.report, "w"), indent=1)
    return 1 if counts["block"] else 0


if __name__ == "__main__":
    sys.exit(main())
