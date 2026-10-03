"""Documentation generator: README-style overview, architecture, API reference, data model,
UML class & sequence diagrams (Mermaid) and a developer-onboarding guide."""
from __future__ import annotations

import json
import re
from collections import defaultdict

from .assistant import call_flow
from .llm import LLMError, get_provider


def _mid(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _ep_score(twin, ep):
    u = twin["units"].get(ep["unit"], {})
    return len(ep.get("consumers", [])) * 3 + u.get("metrics", {}).get("wmc", 0) / 5 + (3 if ep["method"] == "POST" else 0)


def architecture_mermaid(twin) -> str:
    mods = {m["id"]: m for m in twin["modules"]}
    units = twin["units"]
    lines = ["flowchart TB"]
    by_app = defaultdict(list)
    for m in twin["modules"]:
        by_app[m["app"] or "root"].append(m)
    for app, ms in by_app.items():
        lines.append(f'  subgraph {_mid("app_" + app)}["{app}"]')
        for m in ms:
            lines.append(f'    {_mid(m["id"])}["{m["name"]}<br/><small>{len(m["units"])} components</small>"]')
        lines.append("  end")
    if twin["tables"]:
        lines.append('  subgraph DB["Database"]')
        for t in twin["tables"].values():
            lines.append(f'    {_mid(t["id"])}[("{t["name"]}")]')
        lines.append("  end")
    seen = set()
    for e in twin["edges"]:
        s, t = e["source"], e["target"]
        sm = units[s]["module"] if s in units else None
        if t in units:
            tm = units[t]["module"]
        elif t in twin["endpoints"]:
            tm = units.get(twin["endpoints"][t]["unit"], {}).get("module")
        else:
            tm = None
        if s in units and units[s]["is_test"]:
            continue
        if sm and tm and sm != tm and sm in mods and tm in mods and (sm, tm) not in seen:
            seen.add((sm, tm))
            arrow = "-. HTTP .->" if "http" in e["types"] else "-->"
            lines.append(f"  {_mid(sm)} {arrow} {_mid(tm)}")
        if sm and t in twin["tables"] and "maps" in e["types"] and (sm, t) not in seen:
            seen.add((sm, t))
            lines.append(f"  {_mid(sm)} --- {_mid(t)}")
    return "\n".join(lines)


def er_mermaid(twin) -> str:
    units = twin["units"]
    lines = ["erDiagram"]
    for t in twin["tables"].values():
        cols = [c for c in t["columns"] if not c.get("relation")][:10]
        lines.append(f"  {_mid(t['name']).upper()} {{")
        for c in cols:
            typ = re.sub(r"[^A-Za-z0-9]", "", c["type"]) or "field"
            lines.append(f"    {typ} {_mid(c['name'])}{' PK' if c.get('id') else ''}")
        lines.append("  }")
    tbl_of = {t["entity"]: t["name"] for t in twin["tables"].values()}
    done = set()
    for t in twin["tables"].values():
        for r in t.get("relations", []):
            other = tbl_of.get(r["target"])
            if not other:
                continue
            key = tuple(sorted([t["name"], other]))
            if key in done:
                continue
            done.add(key)
            card = {"ManyToOne": "}o--||", "OneToMany": "||--o{", "OneToOne": "||--||", "ManyToMany": "}o--o{"}[r["kind"]]
            lines.append(f"  {_mid(t['name']).upper()} {card} {_mid(other).upper()} : {r['field']}")
    return "\n".join(lines)


def class_mermaid(twin, layers=("controller", "service", "repository", "entity", "interface"), limit=16) -> str:
    units = twin["units"]
    core = [u for u in units.values() if not u["is_test"] and u["layer"] in layers and u["language"] == "Java"]
    core.sort(key=lambda u: -u["metrics"].get("criticality", 0))
    core = core[:limit]
    ids = {u["id"] for u in core}
    lines = ["classDiagram"]
    for u in core:
        lines.append(f"  class {_mid(u['name'])} {{")
        stereo = {"controller": "Controller", "service": "Service", "repository": "Repository", "entity": "Entity", "interface": "interface"}
        lines.append(f"    <<{stereo.get(u['layer'], u['layer'])}>>")
        for m in [m for m in u["methods"] if not m.get("constructor") and m.get("public")][:6]:
            ret = re.sub(r"[<>,\[\] ]", "", (m.get("returnType") or "void"))[:18]
            lines.append(f"    +{_mid(m['name'])}() {ret}")
        lines.append("  }")
    for e in twin["edges"]:
        if e["source"] in ids and e["target"] in ids:
            a, b = _mid(units[e["source"]]["name"]), _mid(units[e["target"]]["name"])
            if "implements" in e["types"]:
                lines.append(f"  {b} <|.. {a}")
            elif "inherits" in e["types"]:
                lines.append(f"  {b} <|-- {a}")
            elif "injects" in e["types"] or "calls" in e["types"]:
                lines.append(f"  {a} --> {b}")
            elif "persists" in e["types"]:
                lines.append(f"  {a} ..> {b} : persists")
    return "\n".join(lines)


def sequence_mermaid(twin, ep) -> str:
    units = twin["units"]
    lines = ["sequenceDiagram", "  autonumber"]
    parts = []

    def part(name, kind="participant"):
        if name not in parts:
            parts.append(name)
            lines.insert(2 + len(parts) - 1, f"  {kind} {_mid(name)} as {name}")
        return _mid(name)

    cons = [units[c]["name"] for c in ep.get("consumers", []) if c in units]
    caller = part(cons[0] if cons else "Client", "actor" if not cons else "participant")
    ctrl = units[ep["unit"]]
    c = part(ctrl["name"])
    lines.append(f"  {caller}->>+{c}: {ep['method']} {ep['path']}")
    steps = []

    def walk(uid, method, depth):
        u = units.get(uid)
        if not u or depth > 3 or len(steps) > 22:
            return
        m = next((x for x in u["methods"] if x["name"] == method), None)
        if not m:
            return
        seen_local = set()
        for call in m.get("resolvedCalls", []):
            t = units.get(call["target"])
            if not t or t["layer"] in {"entity", "dto"} or call["target"] == uid:
                continue
            key = (call["target"], call["method"])
            if key in seen_local:
                continue
            seen_local.add(key)
            a, b = part(u["name"]), part(t["name"])
            loop = call.get("inLoop")
            if loop:
                steps.append(f"  loop each item")
            steps.append(f"  {a}->>+{b}: {call['method']}()")
            if t["layer"] == "repository":
                ent = next((e["target"] for e in twin["edges"] if e["source"] == t["id"] and "persists" in e["types"]), None)
                tbl = next((tb["name"] for tb in twin["tables"].values() if tb["entity"] == ent), None)
                if tbl:
                    d = part("Database")
                    steps.append(f"  {b}->>{d}: SQL on {tbl}")
            else:
                walk(call["target"], call["method"], depth + 1)
            steps.append(f"  {b}-->>-{a}: result")
            if loop:
                steps.append("  end")

    walk(ep["unit"], ep["handler"], 0)
    lines += steps
    lines.append(f"  {c}-->>-{caller}: HTTP response")
    return "\n".join(lines)


def generate(twin: dict, settings: dict, use_ai: bool = False) -> dict:
    s = twin["summary"]
    units = twin["units"]
    c = s["counts"]
    ai_text = {}
    provider = get_provider(settings)
    ai_used = False
    if use_ai and provider.available():
        try:
            ai_text = _ai_descriptions(twin, provider)
            ai_used = True
        except Exception:
            ai_text = {}
    sections = []

    overview = ai_text.get("overview") or (
        f"**{s['name']}** follows a {s['architecture']} architecture written in "
        f"{', '.join(l for l in s['languages'] if l in ('Java', 'TypeScript', 'JavaScript', 'Kotlin', 'Python', 'Go', 'C#'))}. "
        f"It is built with {', '.join(f['name'] for f in s['frameworks'][:8])} and stores data in {', '.join(s['databases']) or 'no detected database'}. "
        f"The code base contains {c['files']} source files ({c['loc']:,} lines), {c['units']} components across {c['modules']} modules, "
        f"{c['endpoints']} REST endpoints and {c['tables']} database tables.")
    sections.append({"id": "overview", "title": "Project Overview", "markdown": overview + "\n\n" + "\n".join([
        f"| Metric | Value |", "|---|---|", f"| Architecture | {s['architecture']} |",
        f"| Health | {twin['health']['overall']}/100 ({twin['health']['grade']}) |", f"| Technical debt | {twin['debt']['level']} (~{twin['debt']['hours']} h) |",
        f"| High-risk components | {c['high_risk']} |", f"| Tests | {c['tests']} test classes |"])})

    stack = "\n".join(f"- **{f['name']}** — {f['category']}" for f in s["frameworks"])
    stack += "\n" + "\n".join(f"- **{d}** — database" for d in s["databases"])
    libs = twin.get("libraries", {})
    if libs:
        stack += "\n\n**Frontend packages in use:** " + ", ".join(f"`{k}`" for k in list(libs)[:20])
    sections.append({"id": "stack", "title": "Technology Stack", "markdown": stack})

    arch = (f"The system follows a **{s['architecture']}** style. Arrows show compile-time dependencies between modules; dotted "
            f"arrows are HTTP calls from the frontend to backend endpoints.\n\n```mermaid\n{architecture_mermaid(twin)}\n```")
    layer_order = ["page", "component", "hook", "context", "api", "controller", "service", "repository", "entity"]
    present = [l for l in layer_order if s["layers"].get(l)]
    if present:
        arch += "\n\n**Layers (request direction):** " + " → ".join(f"{l} ({s['layers'][l]})" for l in present)
    sections.append({"id": "architecture", "title": "Architecture", "markdown": arch})

    rows = ["| Module | App | Components | LOC | Responsibility | Depends on |", "|---|---|---|---|---|---|"]
    for m in sorted(twin["modules"], key=lambda m: (m["app"], -m["loc"])):
        desc = ai_text.get("modules", {}).get(m["name"]) or ", ".join(f"{n} {k}" for k, n in sorted(m["layers"].items(), key=lambda kv: -kv[1]))
        deps = ", ".join(d.split("::")[-1] for d in m["metrics"].get("depends_on", [])[:6]) or "—"
        rows.append(f"| **{m['name']}** | {m['app'] or 'root'} | {', '.join(units[u]['name'] for u in m['units'][:5])}"
                    f"{'…' if len(m['units']) > 5 else ''} | {m['loc']} | {desc} | {deps} |")
    sections.append({"id": "modules", "title": "Modules", "markdown": "\n".join(rows)})

    api = []
    by_unit = defaultdict(list)
    for ep in twin["endpoints"].values():
        by_unit[ep["unit"]].append(ep)
    for uid, eps in sorted(by_unit.items(), key=lambda kv: units[kv[0]]["name"]):
        u = units[uid]
        api.append(f"### {u['name']}\n`{u['file']}`\n")
        api.append("| Method | Path | Handler | Parameters | Used by |\n|---|---|---|---|---|")
        for ep in sorted(eps, key=lambda e: e["path"]):
            params = ", ".join(f"{p['name']} ({p['in']})" for p in ep.get("params", [])) or "—"
            cons = ", ".join(units[c]["name"] for c in ep.get("consumers", []) if c in units) or ("*unused*" if ep.get("unused") else "—")
            api.append(f"| `{ep['method']}` | `{ep['path']}` | {ep['handler']}() | {params} | {cons} |")
        api.append("")
    sections.append({"id": "api", "title": "API Reference", "markdown": "\n".join(api) or "_No HTTP endpoints detected._"})

    if twin["tables"]:
        dm = f"```mermaid\n{er_mermaid(twin)}\n```\n\n"
        dm += "\n".join(f"- **{t['name']}** ← `{units[t['entity']]['name'] if t['entity'] in units else t['entity']}` ({t['source']}), "
                        f"{len(t['columns'])} fields" for t in twin["tables"].values())
        sections.append({"id": "data", "title": "Data Model", "markdown": dm})

    cm = class_mermaid(twin)
    if cm.count("\n") > 2:
        sections.append({"id": "uml", "title": "UML Class Diagram", "markdown": "Core backend classes (most critical first).\n\n```mermaid\n" + cm + "\n```"})

    top_eps = sorted(twin["endpoints"].values(), key=lambda e: -_ep_score(twin, e))[:3]
    if top_eps:
        seq = []
        for ep in top_eps:
            seq.append(f"### {ep['method']} {ep['path']}\n\n```mermaid\n{sequence_mermaid(twin, ep)}\n```\n")
        sections.append({"id": "sequence", "title": "Sequence Diagrams", "markdown": "Generated from the resolved call graph.\n\n" + "\n".join(seq)})

    onboarding = ["**Start here**"]
    for e in s["entry_points"]:
        onboarding.append(f"- `{units[e]['file']}` — entry point ({units[e]['name']})")
    onboarding.append("\n**Suggested reading order**")
    for i, l in enumerate(["entity", "repository", "service", "controller", "api", "context", "hook", "page"], start=1):
        us = [u for u in units.values() if u["layer"] == l and not u["is_test"]]
        if us:
            us.sort(key=lambda u: -u["metrics"].get("criticality", 0))
            names = ", ".join("`" + u["name"] + "`" for u in us[:3])
            onboarding.append(f"{i}. **{l.capitalize()}s** — begin with {names}")
    if s["high_risk"]:
        onboarding.append("\n**Handle with care** (high defect risk):")
        for x in s["high_risk"][:5]:
            onboarding.append(f"- `{units[x]['name']}` — {'; '.join(units[x]['risk']['reasons'][:2])}")
    runs = []
    for a in twin.get("apps", []):
        if a["kind"] == "java":
            runs.append(f"- **{a['name']}**: `cd {a['dir'] or '.'} && mvn spring-boot:run`" if a["manifest"].endswith("pom.xml")
                        else f"- **{a['name']}**: `cd {a['dir'] or '.'} && ./gradlew bootRun`")
        elif a.get("scripts"):
            script = "dev" if "dev" in a["scripts"] else "start" if "start" in a["scripts"] else a["scripts"][0]
            runs.append(f"- **{a['name']}**: `cd {a['dir'] or '.'} && npm install && npm run {script}`")
    if runs:
        onboarding.append("\n**Run locally**\n" + "\n".join(runs))
    sections.append({"id": "onboarding", "title": "Developer Onboarding", "markdown": "\n".join(onboarding)})

    md = f"# {s['name']} — Technical Documentation\n\n_Generated by CodeTwin AI on {twin['generated_at'][:10]}._\n\n"
    md += "\n\n".join(f"## {sec['title']}\n\n{sec['markdown']}" for sec in sections)
    return {"sections": sections, "markdown": md, "ai": ai_used}


def _ai_descriptions(twin, provider) -> dict:
    units = twin["units"]
    mods = []
    for m in twin["modules"]:
        mods.append({"name": m["name"], "app": m["app"], "components": [
            {"name": units[u]["name"], "layer": units[u]["layer"], "methods": [x["name"] for x in units[u]["methods"][:8]]} for u in m["units"][:8]]})
    eps = [f"{e['method']} {e['path']}" for e in list(twin["endpoints"].values())[:40]]
    prompt = ("Given this structural model of a code base, write JSON with keys: overview (3-4 sentence description of what the application does "
              "for its users and how it is built) and modules (object mapping module name to a one-sentence responsibility).\n\n"
              f"Summary: {json.dumps({k: twin['summary'][k] for k in ('name', 'architecture', 'frameworks', 'databases')})}\n"
              f"Modules: {json.dumps(mods)[:9000]}\nEndpoints: {eps}\nRespond with JSON only.")
    txt = provider.complete("You are a precise technical writer. Output valid JSON only.", [{"role": "user", "content": prompt}], max_tokens=1200)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise LLMError("no json")
    return json.loads(m.group(0))
