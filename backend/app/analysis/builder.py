"""Digital Twin builder: orchestrates scanning, parsing, modelling, metrics and scoring."""
from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Callable

from .. import parsers
from . import checks, duplication, graph as G, history, model, refactor, scoring
from .scanner import scan

ENTRY_LAYERS = {"controller", "config", "page", "entry", "route", "test"}


def build_twin(root: Path, name: str, progress: Callable[[str, float], None] | None = None, with_history: bool = True,
               light: bool = False) -> dict:
    t0 = time.time()
    p = progress or (lambda stage, pct: None)
    root = Path(root).resolve()

    p("Scanning repository", 0.05)
    sc = scan(root)
    files = sc["files"]
    files_by_abs = {f["abs"]: f for f in files}
    java_files = [f["abs"] for f in files if f["ext"] in parsers.JAVA_EXT]
    js_files = [f["abs"] for f in files if f["ext"] in parsers.JS_EXT]
    warnings: list[str] = []

    p(f"Parsing {len(java_files)} Java files (javac AST)", 0.15)
    java_parsed = []
    if java_files:
        try:
            java_parsed = parsers.parse_java(java_files)
        except parsers.AnalyzerError as e:
            warnings.append(str(e))
    p(f"Parsing {len(js_files)} JS/TS files (TypeScript AST)", 0.3)
    js_parsed = []
    if js_files:
        try:
            js_parsed = parsers.parse_js(js_files)
        except parsers.AnalyzerError as e:
            warnings.append(str(e))
    # normalise analyzer paths (Java URIs may differ in form)
    for rec in java_parsed + js_parsed:
        rec["path"] = str(Path(rec["path"]).resolve())
    files_by_abs = {str(Path(k).resolve()): v for k, v in files_by_abs.items()}

    p("Building semantic model", 0.42)
    units, endpoints, tables, libraries = {}, {}, {}, {}
    es = model.EdgeSet()
    model.build_java(java_parsed, files_by_abs, sc["apps"], units, es, endpoints, tables)
    model.build_js(js_parsed, files_by_abs, sc["apps"], root, units, es, endpoints, tables, libraries)
    model.parse_prisma(root, sc["configs"], tables)
    model.link_orm_calls(units, tables, es)
    unmatched_calls = model.match_endpoints(units, endpoints, es)
    edges = es.as_list()

    p("Constructing dependency graph", 0.5)
    g = G.build_graph(units, endpoints, tables, edges)
    h = G.unit_graph(g, include_tests=False)
    h_all = G.unit_graph(g, include_tests=True)
    # bidirectional JPA associations (Order <-> OrderItem) are idiomatic, so entity-only cycles are ignored
    cycles = [c for c in G.find_cycles(h) if not all(units[x]["layer"] in {"entity", "dto"} for x in c)]
    cent = G.centrality(h)
    mod_metrics = G.module_metrics(units, h)
    q = G.modularity_q(units, h)

    hist = {"available": False}
    if with_history and not light:
        p("Mining git history", 0.58)
        hist = history.mine(root)
    churn = hist.get("file_churn", {}) if hist.get("available") else {}

    clones = []
    if not light:
        p("Detecting duplicated code", 0.64)
        clones = duplication.detect(files)

    p("Running architecture, security and performance rules", 0.7)
    issues = checks.run_checks(root, files, sc["configs"], units, edges, cycles, clones, cent)

    p("Computing metrics and risk model", 0.78)
    scoring.unit_metrics(units, g, h, h_all, cent, churn, issues)
    scoring.detect_god_classes(units)
    for u in units.values():
        if u.get("god_class"):
            issues.append({"category": "design", "severity": "high", "title": "God class",
                           "detail": f"{u['name']} has {u['metrics']['methods']} methods, WMC {u['metrics']['wmc']}, depends on "
                                     f"{u['metrics']['fan_out']} components across {len(u['metrics']['domains'])} other domains.",
                           "file": u["file"], "line": u["line"], "unit": u["id"], "principle": "SRP", "rule": "god-class",
                           "id": f"iss-{len(issues)}"})
    issue_count = Counter(i["unit"] for i in issues if i.get("unit"))
    for u in units.values():
        u["metrics"]["issues"] = issue_count.get(u["id"], 0)
    scoring.predict_risk(units, bool(churn))
    scoring.file_metrics(files, units, issues, clones, cycles, churn)

    p("Scoring architecture health", 0.86)
    readme = any(d.lower().endswith("readme.md") for d in sc["docs"])
    health = scoring.health(units, files, issues, cycles, mod_metrics, q, readme)
    debt = scoring.debt_summary(files)
    refactorings = [] if light else refactor.advise(root, units, edges, cycles, clones, issues)

    # endpoints: tests + unused detection
    test_text = ""
    if not light:
        for f in files:
            if f["is_test"] and f.get("analyzed"):
                try:
                    test_text += Path(f["abs"]).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
    for ep in endpoints.values():
        handler_unit = units.get(ep["unit"], {})
        ep["tested"] = bool(handler_unit.get("metrics", {}).get("tested")) or (ep["path"] in test_text)
        ep["unused"] = not ep["consumers"]

    modules = _modules(units, mod_metrics, files)
    summary = _summary(name, sc, units, endpoints, tables, edges, modules, libraries, health, debt, issues)
    p("Finalising digital twin", 0.95)
    twin = {
        "version": 1,
        "name": name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - t0, 2),
        "warnings": warnings,
        "summary": summary,
        "apps": sc["apps"],
        "modules": modules,
        "units": {k: _clean_unit(v) for k, v in units.items()},
        "endpoints": endpoints,
        "tables": tables,
        "edges": edges,
        "cycles": cycles,
        "clones": clones,
        "issues": issues,
        "refactorings": refactorings,
        "health": health,
        "debt": debt,
        "history": {k: v for k, v in hist.items() if k != "file_churn"} | ({"hotspots": _hotspots(files, units)} if churn else {}),
        "files": [{k: v for k, v in f.items() if k not in {"abs"}} for f in files],
        "libraries": {k: sorted(v) for k, v in sorted(libraries.items())},
        "unmatched_api_calls": unmatched_calls,
        "configs": sc["configs"],
        "docs": sc["docs"],
    }
    return twin


def _clean_unit(u: dict) -> dict:
    u = dict(u)
    u.pop("_local_from", None)
    u.pop("annotationArgs", None) if not u.get("annotationArgs") else None
    ms = []
    for m in u["methods"]:
        m = {k: v for k, v in m.items() if not k.startswith("_") and k not in {"calls", "strings", "instantiations"}}
        ms.append(m)
    u["methods"] = ms
    return u


def _modules(units, mod_metrics, files) -> list[dict]:
    out = {}
    sloc_by_file = {f["path"]: f["sloc"] for f in files}
    for u in units.values():
        mid = u["module"]
        if mid not in out:
            app, name = mid.split("::", 1)
            out[mid] = {"id": mid, "name": name, "app": "" if app == "." else app, "units": [], "files": set(), "loc": 0,
                        "layers": Counter(), "language": u["language"], "tests": 0, "risk": 0.0, "wmc": 0}
        m = out[mid]
        if u["is_test"]:
            m["tests"] += 1
            continue
        m["units"].append(u["id"])
        if u["file"] not in m["files"]:
            m["files"].add(u["file"])
            m["loc"] += sloc_by_file.get(u["file"], 0)
        m["layers"][u["layer"]] += 1
        m["risk"] = max(m["risk"], u.get("risk", {}).get("score", 0))
        m["wmc"] += u["metrics"]["wmc"]
    res = []
    for mid, m in out.items():
        if not m["units"]:
            continue
        res.append({**{k: v for k, v in m.items() if k not in {"files", "layers"}}, "files": len(m["files"]),
                    "layers": dict(m["layers"]), "metrics": mod_metrics.get(mid, {})})
    res.sort(key=lambda m: (m["app"], m["name"]))
    return res


def _summary(name, sc, units, endpoints, tables, edges, modules, libraries, health, debt, issues) -> dict:
    core = [u for u in units.values() if not u["is_test"]]
    layers = Counter(u["layer"] for u in core)
    classes = sum(1 for u in core if u["language"] == "Java" or u["kind"] == "class")
    components = sum(1 for u in core if u["kind"] in {"component"} or u["layer"] == "page")
    functions = sum(len([m for m in u["methods"] if not m.get("constructor")]) for u in core)
    has_layers = layers["controller"] and layers["service"] and layers["repository"]
    fe = any(a["kind"] == "frontend" for a in sc["apps"])
    be_apps = [a for a in sc["apps"] if a["kind"] in {"java", "node-backend"}]
    if len(be_apps) >= 3:
        style = "Microservices"
    elif has_layers:
        style = "Layered / MVC (Controller → Service → Repository)"
    elif layers["controller"] and layers["repository"]:
        style = "MVC (Controller → Repository)"
    elif layers["route"]:
        style = "REST API (route handlers)"
    elif fe:
        style = "Single-page application"
    else:
        style = "Modular monolith"
    if fe and (has_layers or layers["route"]):
        style += " + SPA frontend"
    critical = sorted([u for u in core if u["layer"] not in {"dto", "types", "exception", "entity", "entry"}],
                      key=lambda u: -u["metrics"].get("criticality", 0))[:6]
    high_risk = [u for u in core if u["risk"]["level"] == "high"]
    entry = [u["id"] for u in core if "SpringBootApplication" in u.get("annotations", []) or u["layer"] == "entry"]
    dead = [u["id"] for u in core if u["metrics"]["fan_in"] == 0 and u["layer"] not in ENTRY_LAYERS and u["id"] not in entry
            and not any(e["target"] == u["id"] and e["source"].startswith("ep:") for e in edges)
            and u["layer"] not in {"dto", "exception", "types"} and u["kind"] != "interface"
            and not any(e["source"] == u["id"] and set(e["types"]) & {"implements", "inherits"} and units.get(e["target"], {}).get("metrics", {}).get("fan_in", 0)
                        for e in edges)]
    unit_edges = [e for e in edges if e["source"] in units and e["target"] in units]
    return {
        "name": name,
        "architecture": style,
        "languages": sc["languages"],
        "language_loc": sc["language_loc"],
        "frameworks": sc["frameworks"],
        "databases": sc["databases"],
        "counts": {
            "files": sum(1 for f in sc["files"] if f.get("analyzed")), "all_files": len(sc["files"]),
            "loc": sum(f["sloc"] for f in sc["files"] if f.get("analyzed")),
            "units": len(core), "classes": classes, "components": components, "functions": functions,
            "modules": len(modules), "endpoints": len(endpoints), "tables": len(tables), "dependencies": len(unit_edges),
            "edges": len(edges), "libraries": len(libraries), "tests": sum(1 for u in units.values() if u["is_test"]),
            "issues": len(issues), "high_risk": len(high_risk),
        },
        "layers": dict(layers),
        "critical": [u["id"] for u in critical],
        "high_risk": [u["id"] for u in sorted(high_risk, key=lambda u: -u["risk"]["score"])],
        "entry_points": entry,
        "unused_endpoints": [e["id"] for e in endpoints.values() if e["unused"] and not e["tested"]],
        "possibly_dead": dead[:30],
        "health": health["overall"],
        "debt_level": debt["level"],
        "debt_hours": debt["hours"],
    }


def _hotspots(files: list[dict], units: dict) -> list[dict]:
    rows = []
    for f in files:
        if not f.get("analyzed") or f["is_test"] or not f.get("churn"):
            continue
        rows.append({"path": f["path"], "churn": f["churn"], "fixes": f.get("fixes", 0), "complexity": f.get("complexity", 0),
                     "sloc": f["sloc"], "authors": len(f.get("authors", [])), "score": f["churn"] * f.get("complexity", 0)})
    rows.sort(key=lambda r: -r["score"])
    mx = rows[0]["score"] if rows else 1
    for r in rows:
        r["score_norm"] = round(r["score"] / mx, 3) if mx else 0
    return rows[:40]
