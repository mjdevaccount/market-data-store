#!/usr/bin/env python3
import hashlib, json, os, re, sys, textwrap
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INCLUDE_DIRS = ["src", "migrations", "cursorrules"]
EXCLUDE = re.compile(r"(__pycache__|\.pyc$|\.git|\.venv|dist|egg-info)")
def short_summary(p):
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            head = "".join(f.readlines()[:10])
            line = next((l.strip() for l in head.splitlines() if l.strip()), "")
            return line[:200]
    except Exception:
        return ""
def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f: h.update(f.read())
    return h.hexdigest()[:16]
items=[]
for d in INCLUDE_DIRS:
    base = os.path.join(ROOT, d)
    if not os.path.exists(base): continue
    for root,_,files in os.walk(base):
        if EXCLUDE.search(root): continue
        for fn in files:
            fp = os.path.join(root, fn)
            if EXCLUDE.search(fp): continue
            rel = os.path.relpath(fp, ROOT).replace("\\","/")
            items.append({"path": rel, "sha": sha256(fp), "summary": short_summary(fp)})
manifest = {"repo":"market-data-store","items":items}
out = os.path.join(ROOT,"cursorrules","solution_manifest.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out,"w",encoding="utf-8") as f: json.dump(manifest,f,indent=2)
print(f"Wrote {out} with {len(items)} items")
