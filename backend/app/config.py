"""Runtime configuration and persisted user settings."""
from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("CODETWIN_DATA_DIR", BACKEND_DIR / "data")).resolve()
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_FILE = DATA_DIR / "settings.json"
SAMPLES_DIR = Path(os.environ.get("CODETWIN_SAMPLES_DIR", ROOT_DIR / "samples")).resolve()

JAVA_ANALYZER = BACKEND_DIR / "analyzers" / "java" / "JavaAnalyzer.java"
JS_ANALYZER = BACKEND_DIR / "analyzers" / "js" / "analyzer.js"

# Public deployment: no local-folder import, read-only settings, no deletes, public Git hosts only, size/concurrency caps.
PUBLIC_MODE = os.environ.get("CODETWIN_PUBLIC", "0") == "1"
ACCESS_PASSWORD = os.environ.get("CODETWIN_PASSWORD", "")
MAX_REPO_MB = int(os.environ.get("CODETWIN_MAX_REPO_MB", 250 if PUBLIC_MODE else 0))  # 0 = unlimited
MAX_CONCURRENT_JOBS = int(os.environ.get("CODETWIN_MAX_JOBS", 2 if PUBLIC_MODE else 0))  # 0 = unlimited

MAX_FILE_BYTES = int(os.environ.get("CODETWIN_MAX_FILE_BYTES", 600_000))
MAX_UPLOAD_BYTES = int(os.environ.get("CODETWIN_MAX_UPLOAD_MB", 200)) * 1024 * 1024

IGNORED_DIRS = {
    ".git", "node_modules", "target", "build", "dist", "out", ".next", ".nuxt", "coverage", ".gradle", ".idea",
    ".vscode", "vendor", "__pycache__", ".venv", "venv", ".mvn", "bin", "obj", ".turbo", ".cache", "storybook-static",
    ".svelte-kit", "generated", "public/static",
}

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "provider": os.environ.get("CODETWIN_LLM_PROVIDER", "anthropic"),  # anthropic | openai | ollama | none
    "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    "anthropic_model": os.environ.get("CODETWIN_ANTHROPIC_MODEL", "claude-opus-5-5"),
    "anthropic_effort": os.environ.get("CODETWIN_ANTHROPIC_EFFORT", "medium"),  # low | medium | high | xhigh | max
    "anthropic_base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
    "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    "openai_model": os.environ.get("CODETWIN_OPENAI_MODEL", "gpt-4o-mini"),
    "openai_base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    "ollama_model": os.environ.get("CODETWIN_OLLAMA_MODEL", "llama3.1"),
    "embeddings": os.environ.get("CODETWIN_EMBEDDINGS", "auto"),  # auto | none | openai | ollama
    "ollama_embed_model": "nomic-embed-text",
}
SECRET_KEYS = ("anthropic_api_key", "openai_api_key")
_lock = threading.Lock()


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
            for k, v in saved.items():
                if k in s and (v not in ("", None) or k not in SECRET_KEYS):
                    s[k] = v
        except Exception:
            pass
    return s


def save_settings(update: dict) -> dict:
    with _lock:
        current = {}
        if SETTINGS_FILE.exists():
            try:
                current = json.loads(SETTINGS_FILE.read_text())
            except Exception:
                current = {}
        for k, v in update.items():
            if k not in DEFAULT_SETTINGS:
                continue
            if k in SECRET_KEYS and isinstance(v, str) and v.startswith("••"):
                continue  # masked value sent back unchanged
            current[k] = v
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(current, indent=2))
    return load_settings()


def public_settings() -> dict:
    s = load_settings()
    for k in SECRET_KEYS:
        v = s.get(k) or ""
        s[k] = ("••••" + v[-4:]) if v else ""
        s[k + "_set"] = bool(v)
    return s


def tool_status() -> dict:
    """Which external toolchains are available for analysis."""
    from .parsers import find_java, find_node, find_typescript
    java = find_java()
    node = find_node()
    if PUBLIC_MODE:  # don't reveal server filesystem paths
        java, node = java and "available", node and "available"
    return {
        "java": bool(java), "java_path": java,
        "node": bool(node), "node_path": node,
        "typescript": bool(find_typescript()),
        "git": bool(shutil.which("git")),
    }
