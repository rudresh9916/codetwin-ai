"""CodeTwin AI — REST API (FastAPI).

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from . import projects
from .ai import assistant, docs as docs_gen
from .ai.llm import ai_status
from .analysis import impact as impact_mod
from .config import ACCESS_PASSWORD, MAX_UPLOAD_BYTES, PUBLIC_MODE, load_settings, public_settings, save_settings, tool_status

app = FastAPI(title="CodeTwin AI", version="1.0.0",
              description="Intelligent Software Engineering Digital Twin — understand, predict and improve software before problems happen.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CODETWIN_CORS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Optional shared password (HTTP Basic, any username) for public deployments. The health check stays open."""
    if ACCESS_PASSWORD and request.url.path != "/api/health":
        import base64
        import hmac
        auth = request.headers.get("authorization", "")
        ok = False
        if auth.lower().startswith("basic "):
            try:
                ok = hmac.compare_digest(base64.b64decode(auth[6:]).decode().partition(":")[2], ACCESS_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return PlainTextResponse("Password required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="CodeTwin AI"'})
    return await call_next(request)


@app.on_event("startup")
def seed_demo():
    """On a fresh public server, build the ShopVerse sample so visitors land on a working twin."""
    if PUBLIC_MODE and not projects.list_projects():
        try:
            projects.create_from_sample("shopverse")
        except projects.ProjectError:
            pass


def _locked(what: str):
    if PUBLIC_MODE:
        _err(PermissionError(f"{what} is disabled on this public demo."), 403)


FRONTEND_DIST = Path(os.environ.get("CODETWIN_FRONTEND_DIST") or Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")


def _err(e: Exception, code: int = 400):
    raise HTTPException(status_code=code, detail=str(e))


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _get(pid: str) -> dict:
    try:
        return projects.load(pid)
    except projects.ProjectError as e:
        _err(e, 404)


def _sse(gen):
    def wrap():
        try:
            for ev in gen:
                yield "data: " + json.dumps(ev, default=str) + "\n\n"
        except Exception as e:  # noqa
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
    return StreamingResponse(wrap(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============================================================================== system
@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0.0", "public": PUBLIC_MODE, "tools": tool_status(), "ai": ai_status()}


@app.get("/api/settings")
def get_settings():
    return {**public_settings(), "ai": ai_status(), "locked": PUBLIC_MODE}


@app.put("/api/settings")
async def put_settings(request: Request):
    _locked("Changing settings")
    body = await _json(request)
    save_settings(body)
    return {**public_settings(), "ai": ai_status()}


@app.post("/api/settings/test")
def test_settings():
    _locked("Testing the AI connection")
    from .ai.llm import get_provider, LLMError
    p = get_provider()
    if not p.available():
        return {"ok": False, "message": "No provider configured or reachable."}
    try:
        t0 = time.time()
        out = p.complete("Reply with exactly: CodeTwin ready.", [{"role": "user", "content": "ping"}], max_tokens=20)
        return {"ok": True, "message": out.strip()[:120], "latency_ms": round((time.time() - t0) * 1000), "provider": p.name, "model": p.model}
    except LLMError as e:
        return {"ok": False, "message": str(e)}


# ============================================================================== projects
@app.get("/api/projects")
def list_projects():
    return projects.list_projects()


@app.post("/api/projects/upload")
async def upload(request: Request):
    form = await request.form()
    f = form.get("file")
    if f is None or not getattr(f, "filename", None):
        _err(ValueError("Attach a .zip file in the 'file' field"))
    if not f.filename.lower().endswith(".zip"):
        _err(ValueError("Only .zip archives are supported"))
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    size = 0
    try:
        while True:
            chunk = await f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                _err(ValueError("Upload too large"), 413)
            tmp.write(chunk)
        tmp.close()
        pid = projects.create_from_zip(f.filename, Path(tmp.name))
    except projects.ProjectError as e:
        _err(e)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return projects.read_meta(pid)


@app.post("/api/projects/git")
async def import_git(request: Request):
    body = await _json(request)
    try:
        pid = projects.create_from_git(body.get("url", ""), body.get("branch") or None)
    except projects.ProjectError as e:
        _err(e)
    return projects.read_meta(pid)


@app.post("/api/projects/sample")
async def import_sample(request: Request):
    body = await _json(request)
    try:
        pid = projects.create_from_sample(body.get("sample", "shopverse"))
    except projects.ProjectError as e:
        _err(e)
    return projects.read_meta(pid)


@app.post("/api/projects/local")
async def import_local(request: Request):
    if PUBLIC_MODE or os.environ.get("CODETWIN_ALLOW_LOCAL", "1") != "1":
        _err(PermissionError("Local folder import is disabled"), 403)
    body = await _json(request)
    try:
        pid = projects.create_from_path(body.get("path", ""))
    except projects.ProjectError as e:
        _err(e)
    return projects.read_meta(pid)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    try:
        return projects.read_meta(pid)
    except projects.ProjectError as e:
        _err(e, 404)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    _locked("Deleting projects")
    try:
        projects.delete_project(pid)
    except projects.ProjectError as e:
        _err(e, 404)
    return {"ok": True}


@app.post("/api/projects/{pid}/reanalyze")
def reanalyze(pid: str):
    try:
        projects.read_meta(pid)
        projects.start_analysis(pid)
    except projects.ProjectError as e:
        _err(e, 404)
    return projects.read_meta(pid)


@app.get("/api/projects/{pid}/twin")
def get_twin(pid: str):
    return _get(pid)["twin"]


@app.get("/api/projects/{pid}/source")
def get_source(pid: str, path: str = ""):
    try:
        text = projects.read_source(pid, path)
    except projects.ProjectError as e:
        _err(e, 404)
    return {"path": path, "content": text}


@app.get("/api/projects/{pid}/search")
def search(pid: str, q: str = "", k: int = 20, kind: str = ""):
    c = _get(pid)
    if not c["index"] or not q.strip():
        return {"query": q, "results": []}
    kinds = set(kind.split(",")) if kind else None
    settings = load_settings()
    from .ai.retrieval import embed_query
    qv = embed_query(q, settings) if c["index"].vectors is not None else None
    hits = c["index"].search(q, k=min(50, k), kinds=kinds, boost_units=set(assistant.mentioned_units(c["twin"], q)), query_vec=qv)
    for h in hits:
        h["snippet"] = h.pop("text", "")[:600]
    return {"query": q, "results": hits, "semantic": qv is not None}


# ============================================================================== analysis
@app.post("/api/projects/{pid}/impact")
async def impact(pid: str, request: Request):
    body = await _json(request)
    c = _get(pid)
    tg = c["graph"]
    target = tg.resolve(body.get("target", ""))
    if not target:
        _err(ValueError(f"Unknown component '{body.get('target')}'"), 404)
    return impact_mod.analyze_impact(tg, target, body.get("change", "modify"), body.get("method") or None)


@app.post("/api/projects/{pid}/whatif")
async def whatif(pid: str, request: Request):
    body = await _json(request)
    c = _get(pid)
    tg = c["graph"]
    scenario = body.get("scenario", "remove")
    target = body.get("target")
    if scenario in {"remove", "replace"}:
        target = tg.resolve(target or "")
        if not target or target not in tg.units:
            _err(ValueError("Choose a component"), 404)
    try:
        return impact_mod.whatif(tg, scenario, target, body.get("members"), float(body.get("resolution", 1.0)))
    except (KeyError, ValueError) as e:
        _err(e)


@app.post("/api/projects/{pid}/explain")
async def explain(pid: str, request: Request):
    """Stream an AI explanation of any analysis result (health, impact, whatif, refactoring)."""
    body = await _json(request)
    _get(pid)
    kind = body.get("kind", "health")
    payload = body.get("payload") or {}
    settings = load_settings()

    def gen():
        yield {"type": "meta", "mode": ai_status()["provider"] if ai_status()["available"] else "offline"}
        for tok in assistant.explain(kind, payload, settings):
            yield {"type": "token", "text": tok}
        yield {"type": "done"}
    return _sse(gen())


@app.get("/api/projects/{pid}/evolution")
def get_evolution(pid: str):
    _get(pid)
    return projects.evolution(pid)


@app.post("/api/projects/{pid}/evolution")
def run_evolution(pid: str, snapshots: int = 6):
    _get(pid)
    return projects.start_evolution(pid, max(2, min(10, snapshots)))


# ============================================================================== AI assistant
@app.get("/api/projects/{pid}/chat")
def get_chat(pid: str):
    _get(pid)
    return projects.chat_history(pid)


@app.delete("/api/projects/{pid}/chat")
def clear_chat(pid: str):
    projects.save_chat(pid, [])
    return {"ok": True}


@app.post("/api/projects/{pid}/chat")
async def chat(pid: str, request: Request):
    body = await _json(request)
    question = (body.get("message") or "").strip()
    if not question:
        _err(ValueError("Empty question"))
    c = _get(pid)
    settings = load_settings()
    history = projects.chat_history(pid)

    def gen():
        answer, meta = [], {}
        for ev in assistant.stream_answer(c["twin"], c["graph"], c["index"], question, history, settings):
            if ev["type"] == "meta":
                meta = ev
            elif ev["type"] == "token":
                answer.append(ev["text"])
            yield ev
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        history.append({"role": "user", "content": question, "ts": now})
        history.append({"role": "assistant", "content": "".join(answer), "ts": now, "sources": meta.get("sources", []),
                        "mode": meta.get("mode"), "facts": meta.get("facts", [])})
        projects.save_chat(pid, history)
    return _sse(gen())


# ============================================================================== docs
@app.get("/api/projects/{pid}/docs")
def get_docs(pid: str, ai: int = 0, refresh: int = 0):
    c = _get(pid)
    path = projects.pdir(pid) / "docs.json"
    if path.exists() and not refresh:
        d = json.loads(path.read_text())
        if not ai or d.get("ai"):
            return d
    d = docs_gen.generate(c["twin"], load_settings(), use_ai=bool(ai))
    path.write_text(json.dumps(d))
    return d


@app.get("/api/projects/{pid}/docs/export")
def export_docs(pid: str):
    c = _get(pid)
    path = projects.pdir(pid) / "docs.json"
    d = json.loads(path.read_text()) if path.exists() else docs_gen.generate(c["twin"], load_settings())
    name = c["twin"]["name"].replace(" ", "_")
    return PlainTextResponse(d["markdown"], headers={"Content-Disposition": f'attachment; filename="{name}_ARCHITECTURE.md"'})


@app.get("/api/projects/{pid}/report")
def export_report(pid: str):
    """Full twin as downloadable JSON (for reports / external tooling)."""
    c = _get(pid)
    return JSONResponse(c["twin"], headers={"Content-Disposition": f'attachment; filename="{c["twin"]["name"]}_twin.json"'})


# ============================================================================== static frontend (production build)
if FRONTEND_DIST.exists():
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = (FRONTEND_DIST / full_path).resolve()
        if full_path and f.is_relative_to(FRONTEND_DIST.resolve()) and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
