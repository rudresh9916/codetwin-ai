"""Git history mining: churn, authorship, bug-fix density, change coupling and timeline."""
from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

FIX_WORDS = ("fix", "bug", "hotfix", "patch", "issue", "error", "crash", "regression", "npe")


def has_git(root: Path) -> bool:
    return (Path(root) / ".git").exists()


def mine(root: Path, max_commits: int = 3000) -> dict:
    if not has_git(root):
        return {"available": False}
    sep = "\x1e"
    fmt = f"{sep}%H\x1f%an\x1f%ae\x1f%aI\x1f%s"
    try:
        out = subprocess.run(["git", "-C", str(root), "log", f"-n{max_commits}", "--no-merges", "--numstat", f"--format={fmt}"],
                             capture_output=True, text=True, timeout=120, errors="replace").stdout
    except Exception:
        return {"available": False}
    commits = []
    for block in out.split(sep):
        block = block.strip("\n")
        if not block:
            continue
        head, *rest = block.split("\n")
        parts = head.split("\x1f")
        if len(parts) < 5:
            continue
        sha, author, email, date, msg = parts[:5]
        files = []
        for ln in rest:
            cols = ln.split("\t")
            if len(cols) == 3:
                a, d, p = cols
                if "=>" in p:  # rename: src/{a => b}/x
                    p = _rename_target(p)
                files.append({"path": p, "added": int(a) if a.isdigit() else 0, "deleted": int(d) if d.isdigit() else 0})
        commits.append({"sha": sha, "author": author, "email": email, "date": date, "message": msg, "files": files,
                        "fix": any(w in msg.lower() for w in FIX_WORDS)})
    if not commits:
        return {"available": False}
    commits.reverse()  # oldest first
    now = datetime.fromisoformat(commits[-1]["date"]).astimezone(timezone.utc)
    six_months = now - timedelta(days=183)
    churn = defaultdict(lambda: {"commits": 0, "recent_commits": 0, "added": 0, "deleted": 0, "authors": set(), "fixes": 0,
                                 "first": None, "last": None})
    weekly = Counter()
    authors = Counter()
    co_change = Counter()
    for c in commits:
        dt = datetime.fromisoformat(c["date"]).astimezone(timezone.utc)
        week = (dt - timedelta(days=dt.weekday())).date().isoformat()
        weekly[week] += 1
        authors[c["author"]] += 1
        paths = [f["path"] for f in c["files"]]
        for f in c["files"]:
            ch = churn[f["path"]]
            ch["commits"] += 1
            ch["added"] += f["added"]
            ch["deleted"] += f["deleted"]
            ch["authors"].add(c["author"])
            ch["fixes"] += 1 if c["fix"] else 0
            ch["recent_commits"] += 1 if dt >= six_months else 0
            ch["first"] = ch["first"] or c["date"]
            ch["last"] = c["date"]
        code_paths = [p for p in paths if p.endswith((".java", ".ts", ".tsx", ".js", ".jsx"))]
        if 2 <= len(code_paths) <= 12:
            for a, b in combinations(sorted(code_paths), 2):
                co_change[(a, b)] += 1
    file_churn = {p: {**v, "authors": sorted(v["authors"])} for p, v in churn.items()}
    coupling = []
    for (a, b), n in co_change.most_common(40):
        if n < 2:
            break
        denom = min(file_churn[a]["commits"], file_churn[b]["commits"]) or 1
        coupling.append({"a": a, "b": b, "together": n, "degree": round(n / denom, 2)})
    # fill weekly gaps for a smooth timeline
    timeline = []
    if weekly:
        start = datetime.fromisoformat(min(weekly)).date()
        end = datetime.fromisoformat(max(weekly)).date()
        d = start
        while d <= end:
            timeline.append({"week": d.isoformat(), "commits": weekly.get(d.isoformat(), 0)})
            d += timedelta(days=7)
    return {
        "available": True,
        "commits": len(commits),
        "first_commit": commits[0]["date"], "last_commit": commits[-1]["date"],
        "authors": [{"name": a, "commits": n} for a, n in authors.most_common()],
        "timeline": timeline,
        "file_churn": file_churn,
        "change_coupling": coupling,
        "recent": [{k: c[k] for k in ("sha", "author", "date", "message", "fix")} | {"files": len(c["files"])} for c in commits[-40:]][::-1],
        "fix_commits": sum(1 for c in commits if c["fix"]),
    }


def _rename_target(p: str) -> str:
    if "{" in p:
        pre, rest = p.split("{", 1)
        mid, post = rest.split("}", 1)
        new = mid.split("=>")[1].strip()
        return (pre + new + post).replace("//", "/")
    return p.split("=>")[1].strip()


def snapshot_commits(root: Path, n: int = 6) -> list[dict]:
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "--no-merges", "--reverse", "--format=%H\x1f%aI\x1f%s"],
                             capture_output=True, text=True, timeout=60).stdout.strip().splitlines()
    except Exception:
        return []
    rows = [l.split("\x1f") for l in out if l]
    if not rows:
        return []
    if len(rows) <= n:
        idx = list(range(len(rows)))
    else:
        idx = sorted({round(i * (len(rows) - 1) / (n - 1)) for i in range(n)})
    return [{"sha": rows[i][0], "date": rows[i][1], "message": rows[i][2], "index": i + 1} for i in idx]


def export_commit(root: Path, sha: str, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        arch = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", sha], capture_output=True, timeout=120)
        if arch.returncode != 0:
            return False
        subprocess.run(["tar", "-x", "-C", str(dest)], input=arch.stdout, check=True, timeout=120)
        return True
    except Exception:
        return False
