"""Bridges to the language analyzers.

* Java  -> analyzers/java/JavaAnalyzer.java  (JDK compiler tree API, launched as a single-file program)
* JS/TS -> analyzers/js/analyzer.js          (TypeScript compiler API on Node.js)

Both analyzers emit JSON which is consumed by app.analysis.builder.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import JAVA_ANALYZER, JS_ANALYZER, BACKEND_DIR

JAVA_EXT = {".java"}
JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


class AnalyzerError(RuntimeError):
    pass


def find_java() -> str | None:
    home = os.environ.get("JAVA_HOME")
    if home:
        found = shutil.which("java", path=str(Path(home) / "bin"))  # resolves java.exe on Windows
        if found:
            return found
    found = shutil.which("java")
    if found:
        return found
    # JDK installed but not (yet) on this process's PATH, e.g. right after an installer ran.
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
            if not root:
                continue
            for vendor in ("Eclipse Adoptium", "Java", "Microsoft", "Zulu", "Amazon Corretto"):
                for jdk in sorted(Path(root, vendor).glob("jdk*"), reverse=True):
                    exe = jdk / "bin" / "java.exe"
                    if exe.exists():
                        return str(exe)
    return None


def find_node() -> str | None:
    return shutil.which("node") or shutil.which("nodejs")


def find_typescript() -> str | None:
    candidates = [os.environ.get("CODETWIN_TS_PATH"), str(BACKEND_DIR / "analyzers" / "js" / "node_modules" / "typescript")]
    for c in candidates:
        if c and Path(c, "package.json").exists():
            return c
    node = find_node()
    if node:
        try:
            r = subprocess.run([node, "-e", "console.log(require.resolve('typescript'))"], capture_output=True, text=True, timeout=10,
                               cwd=str(JS_ANALYZER.parent))
            if r.returncode == 0 and r.stdout.strip():
                return str(Path(r.stdout.strip()).parent.parent)
        except Exception:
            pass
    return None


def _run(cmd: list[str], files: list[str], timeout: int, env: dict | None = None) -> list[dict]:
    if not files:
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(files))
        list_path = fh.name
    try:
        proc = subprocess.run(cmd + [list_path], capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise AnalyzerError(f"Analyzer timed out: {' '.join(cmd[:2])}") from e
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or not out:
        err = proc.stderr.decode("utf-8", errors="replace")
        err = "\n".join(l for l in err.splitlines() if "JAVA_TOOL_OPTIONS" not in l)[-1500:]
        raise AnalyzerError(f"Analyzer failed ({proc.returncode}): {err}")
    return json.loads(out)


def parse_java(files: list[str]) -> list[dict]:
    java = find_java()
    if not java:
        raise AnalyzerError("Java (JDK 17+) is required to analyze .java files but was not found on PATH.")
    env = dict(os.environ)
    results: list[dict] = []
    # One JVM handles batches internally; split very large repos to keep runtimes bounded.
    step = 1500
    for i in range(0, len(files), step):
        results += _run([java, "-Xss4m", str(JAVA_ANALYZER)], files[i:i + step], timeout=600, env=env)
    return results


def parse_js(files: list[str]) -> list[dict]:
    node = find_node()
    if not node:
        raise AnalyzerError("Node.js is required to analyze JS/TS files but was not found on PATH.")
    env = dict(os.environ)
    ts = find_typescript()
    if ts:
        env["CODETWIN_TS_PATH"] = ts
    results: list[dict] = []
    step = 800
    for i in range(0, len(files), step):
        results += _run([node, "--max-old-space-size=4096", str(JS_ANALYZER)], files[i:i + step], timeout=600, env=env)
    return results
