"""Project storage, ingestion (ZIP / Git / sample / local folder) and background analysis jobs."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from .config import IGNORED_DIRS, MAX_CONCURRENT_JOBS, MAX_REPO_MB, PROJECTS_DIR, PUBLIC_MODE, SAMPLES_DIR, load_settings
from .analysis.builder import build_twin
from .analysis.impact import TwinGraph
from .ai import retrieval

_locks: dict[str, threading.Lock] = {}
_cache: dict[str, dict] = {}
_jobs: dict[str, threading.Thread] = {}


class ProjectError(Exception):
    pass


def pdir(pid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{6,40}", pid or ""):
        raise ProjectError("invalid project id")
    return PROJECTS_DIR / pid


def _write_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, default=list))
    tmp.replace(path)


def read_meta(pid: str) -> dict:
    p = pdir(pid) / "meta.json"
    if not p.exists():
        raise ProjectError("project not found")
    return json.loads(p.read_text())


def update_meta(pid: str, **kw) -> dict:
    lock = _locks.setdefault(pid, threading.Lock())
    with lock:
        m = read_meta(pid)
        m.update(kw)
        m["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json(pdir(pid) / "meta.json", m)
        return m


def list_projects() -> list[dict]:
    out = []
    for d in PROJECTS_DIR.iterdir() if PROJECTS_DIR.exists() else []:
        if (d / "meta.json").exists():
            try:
                out.append(json.loads((d / "meta.json").read_text()))
            except Exception:
                pass
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def _check_capacity():
    if MAX_CONCURRENT_JOBS and sum(t.is_alive() for t in _jobs.values()) >= MAX_CONCURRENT_JOBS:
        raise ProjectError("The server is busy analysing other projects. Try again in a minute.")


def _dir_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1_048_576


def _new_project(name: str, source: dict) -> str:
    _check_capacity()
    pid = uuid.uuid4().hex[:12]
    d = PROJECTS_DIR / pid
    d.mkdir(parents=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(d / "meta.json", {"id": pid, "name": name, "source": source, "status": "queued", "stage": "Queued", "progress": 0,
                                  "created_at": now, "updated_at": now, "error": None})
    return pid


def _force_remove(func, path, *_):
    # Git marks object files read-only; on Windows they must be made writable before they can be deleted.
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def delete_project(pid: str):
    d = pdir(pid)
    _cache.pop(pid, None)
    if d.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(d, onexc=_force_remove)
        else:
            shutil.rmtree(d, onerror=_force_remove)


# ------------------------------------------------------------------------------------------ ingestion
def _ignore(dirpath, names):
    return [n for n in names if n in IGNORED_DIRS and n != ".git"]


def create_from_zip(filename: str, data_path: Path) -> str:
    name = re.sub(r"\.zip$", "", Path(filename).name, flags=re.I) or "project"
    pid = _new_project(name, {"type": "zip", "file": Path(filename).name})
    src = pdir(pid) / "src"
    try:
        with zipfile.ZipFile(data_path) as z:
            total = 0
            for info in z.infolist():
                total += info.file_size
                if total > 2_000_000_000:
                    raise ProjectError("archive too large when extracted")
                target = (src / info.filename).resolve()
                if not target.is_relative_to(src.resolve()):
                    raise ProjectError("unsafe path in archive")
                parts = Path(info.filename).parts
                if any(p in IGNORED_DIRS and p != ".git" for p in parts):
                    continue
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as fsrc, open(target, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
    except zipfile.BadZipFile as e:
        delete_project(pid)
        raise ProjectError("not a valid ZIP archive") from e
    except ProjectError:
        delete_project(pid)
        raise
    _flatten_single_dir(src)
    start_analysis(pid)
    return pid


def _flatten_single_dir(src: Path):
    entries = [p for p in src.iterdir() if p.name not in {"__MACOSX", ".DS_Store"}]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        tmp = src.parent / "src_tmp"
        inner.rename(tmp)
        shutil.rmtree(src)
        tmp.rename(src)


GIT_URL = re.compile(r"^(https?://[\w.\-]+(:\d+)?/[\w.\-~/%]+?)(\.git)?/?$|^git@[\w.\-]+:[\w.\-/]+(\.git)?$")


def create_from_git(url: str, branch: str | None = None) -> str:
    url = url.strip()
    m = re.match(r"^https?://github\.com/([\w.\-]+)/([\w.\-]+)(/tree/([\w.\-/]+))?", url)
    if m and m.group(4):
        branch = branch or m.group(4)
        url = f"https://github.com/{m.group(1)}/{m.group(2)}"
    if not GIT_URL.match(url):
        raise ProjectError("Enter a valid Git URL, e.g. https://github.com/owner/repo")
    if PUBLIC_MODE and not re.match(r"^https://(github\.com|gitlab\.com|bitbucket\.org)/", url):
        raise ProjectError("This public demo imports from github.com, gitlab.com or bitbucket.org only.")
    name = re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    pid = _new_project(name, {"type": "git", "url": url, "branch": branch})

    def job():
        try:
            update_meta(pid, status="cloning", stage="Cloning repository", progress=0.02)
            cmd = ["git", "clone", "--depth", "400", "--single-branch"]
            if branch:
                cmd += ["--branch", branch]
            cmd += [url, str(pdir(pid) / "src")]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"})
            if r.returncode != 0:
                raise ProjectError("git clone failed: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1])
            if MAX_REPO_MB and _dir_mb(pdir(pid) / "src") > MAX_REPO_MB:
                shutil.rmtree(pdir(pid) / "src", onerror=_force_remove)
                raise ProjectError(f"Repository is larger than {MAX_REPO_MB} MB, the limit on this server.")
            _analyze(pid)
        except Exception as e:  # noqa
            update_meta(pid, status="error", stage="Failed", error=str(e))

    t = threading.Thread(target=job, daemon=True)
    _jobs[pid] = t
    t.start()
    return pid


def create_from_sample(sample: str = "shopverse") -> str:
    src_dir = SAMPLES_DIR / sample
    if not src_dir.exists():
        raise ProjectError(f"sample '{sample}' not found")
    pid = _new_project({"shopverse": "ShopVerse (sample)"}.get(sample, sample), {"type": "sample", "sample": sample})
    dst = pdir(pid) / "src"
    shutil.copytree(src_dir, dst, ignore=_ignore, symlinks=False)
    builder = SAMPLES_DIR / "build_sample_history.py"
    if sample == "shopverse" and not (dst / ".git").exists() and builder.exists():
        # The sample's demo history is generated rather than stored in the repository (nested .git dirs don't survive git push).
        subprocess.run([sys.executable, str(builder), str(dst)], capture_output=True, timeout=300)
    start_analysis(pid)
    return pid


def create_from_path(path: str) -> str:
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise ProjectError("folder not found")
    pid = _new_project(p.name, {"type": "local", "path": str(p)})
    shutil.copytree(p, pdir(pid) / "src", ignore=_ignore, symlinks=False)
    start_analysis(pid)
    return pid


# ------------------------------------------------------------------------------------------ analysis
def start_analysis(pid: str):
    t = threading.Thread(target=_safe_analyze, args=(pid,), daemon=True)
    _jobs[pid] = t
    t.start()


def _safe_analyze(pid):
    try:
        _analyze(pid)
    except Exception as e:  # noqa
        import traceback
        traceback.print_exc()
        update_meta(pid, status="error", stage="Failed", error=str(e))


def _analyze(pid: str):
    meta = update_meta(pid, status="analyzing", stage="Starting", progress=0.03, error=None)
    root = pdir(pid) / "src"

    def prog(stage, pct):
        update_meta(pid, stage=stage, progress=round(pct, 3))

    twin = build_twin(root, meta["name"], progress=prog)
    twin["project_id"] = pid
    _write_json(pdir(pid) / "twin.json", twin)
    prog("Indexing code for AI search", 0.97)
    chunks = retrieval.build_chunks(root, twin)
    vectors = retrieval.maybe_embed(chunks, load_settings())
    retrieval.save_index(pdir(pid) / "index.json", chunks, vectors)
    (pdir(pid) / "docs.json").unlink(missing_ok=True)
    (pdir(pid) / "evolution.json").unlink(missing_ok=True)
    _cache.pop(pid, None)
    s = twin["summary"]
    update_meta(pid, status="ready", stage="Ready", progress=1.0,
                summary={"counts": s["counts"], "health": twin["health"]["overall"], "grade": twin["health"]["grade"],
                         "architecture": s["architecture"], "languages": s["languages"], "debt": twin["debt"]["level"],
                         "frameworks": [f["name"] for f in s["frameworks"]][:6]},
                warnings=twin["warnings"], analyzed_at=twin["generated_at"])


def load(pid: str) -> dict:
    """Return cached {twin, graph, index} for a ready project."""
    path = pdir(pid) / "twin.json"
    if not path.exists():
        raise ProjectError("project has not been analysed yet")
    mtime = path.stat().st_mtime
    c = _cache.get(pid)
    if c and c["mtime"] == mtime:
        return c
    twin = json.loads(path.read_text())
    c = {"mtime": mtime, "twin": twin, "graph": TwinGraph(twin), "index": retrieval.load_index(pdir(pid) / "index.json")}
    _cache[pid] = c
    if len(_cache) > 6:
        _cache.pop(next(iter(_cache)))
    return c


def source_root(pid: str) -> Path:
    return pdir(pid) / "src"


def read_source(pid: str, rel: str) -> str:
    root = source_root(pid).resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise ProjectError("file not found")
    if p.stat().st_size > 1_500_000:
        raise ProjectError("file too large to display")
    return p.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------------------------------ chat history
def chat_history(pid: str) -> list[dict]:
    p = pdir(pid) / "chat.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_chat(pid: str, messages: list[dict]):
    _write_json(pdir(pid) / "chat.json", messages[-200:])


# ------------------------------------------------------------------------------------------ evolution
def evolution(pid: str) -> dict:
    p = pdir(pid) / "evolution.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"status": "not_started"}


def start_evolution(pid: str, snapshots: int = 6) -> dict:
    p = pdir(pid) / "evolution.json"
    cur = evolution(pid)
    if cur.get("status") == "running":
        return cur
    _write_json(p, {"status": "running", "progress": 0, "snapshots": []})

    def job():
        from .analysis import history
        root = source_root(pid)
        commits = history.snapshot_commits(root, snapshots)
        results = []
        try:
            for i, c in enumerate(commits):
                with tempfile.TemporaryDirectory() as tmp:
                    dest = Path(tmp) / "snap"
                    if not history.export_commit(root, c["sha"], dest):
                        continue
                    tw = build_twin(dest, "snapshot", with_history=False, light=True)
                    units = tw["units"]
                    mod_edges = {}
                    for e in tw["edges"]:
                        s, t = e["source"], e["target"]
                        sm = units[s]["module"] if s in units else None
                        tm = units[t]["module"] if t in units else (units.get(tw["endpoints"].get(t, {}).get("unit", ""), {}).get("module"))
                        if sm and tm and sm != tm and not units[s]["is_test"]:
                            mod_edges[f"{sm}|{tm}"] = mod_edges.get(f"{sm}|{tm}", 0) + 1
                    results.append({**c, "counts": tw["summary"]["counts"], "health": tw["health"]["overall"],
                                    "architecture": tw["summary"]["architecture"], "layers": tw["summary"]["layers"],
                                    "modules": [{"id": m["id"], "name": m["name"], "app": m["app"], "units": len(m["units"]), "loc": m["loc"]}
                                                for m in tw["modules"]],
                                    "module_edges": [{"source": k.split("|")[0], "target": k.split("|")[1], "weight": v} for k, v in mod_edges.items()],
                                    "tables": len(tw["tables"]), "debt_hours": tw["debt"]["hours"]})
                    _write_json(p, {"status": "running", "progress": round((i + 1) / max(1, len(commits)), 2), "snapshots": results})
            _write_json(p, {"status": "done", "progress": 1, "snapshots": results})
        except Exception as e:  # noqa
            _write_json(p, {"status": "error", "error": str(e), "snapshots": results})

    threading.Thread(target=job, daemon=True).start()
    return {"status": "running", "progress": 0, "snapshots": []}
