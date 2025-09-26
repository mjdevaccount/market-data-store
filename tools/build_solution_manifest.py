#!/usr/bin/env python3
import hashlib
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INCLUDE_DIRS = ["src", "migrations", "cursorrules"]
EXCLUDE = re.compile(r"(__pycache__|\.pyc$|\.git|\.venv|dist|egg-info|solution_manifest\.json)")


def short_summary(p):
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            head = "".join(f.readlines()[:10])
            line = next((line.strip() for line in head.splitlines() if line.strip()), "")
            return line[:200]
    except Exception:
        return ""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:16]


items = []
for d in INCLUDE_DIRS:
    base = os.path.join(ROOT, d)
    if not os.path.exists(base):
        continue
    for root, _, files in os.walk(base):
        if EXCLUDE.search(root):
            continue
        for fn in files:
            fp = os.path.join(root, fn)
            if EXCLUDE.search(fp):
                continue
            rel = os.path.relpath(fp, ROOT).replace("\\", "/")
            items.append({"path": rel, "sha": sha256(fp), "summary": short_summary(fp)})

manifest = {"repo": "market-data-store", "items": items}
out = os.path.join(ROOT, "cursorrules", "solution_manifest.json")
os.makedirs(os.path.dirname(out), exist_ok=True)

# Check if content has changed to avoid unnecessary writes
new_content = json.dumps(manifest, indent=2) + "\n"
if os.path.exists(out):
    with open(out, "r", encoding="utf-8") as f:
        existing_content = f.read()
    if existing_content == new_content:
        print(f"Solution manifest is up to date with {len(items)} items")
        exit(0)

with open(out, "w", encoding="utf-8") as f:
    f.write(new_content)
print(f"Wrote {out} with {len(items)} items")
