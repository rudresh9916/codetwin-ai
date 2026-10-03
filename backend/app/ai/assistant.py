"""Ask CodeTwin: hybrid assistant = deterministic twin facts + RAG code context + LLM explanation."""
from __future__ import annotations

import json
import re
from typing import Iterator

from ..analysis.impact import TwinGraph, analyze_impact, parse_question, whatif
from .llm import LLMError, get_provider
from .retrieval import Index, embed_query

SYSTEM = """You are CodeTwin, an AI software-architecture assistant connected to the Digital Twin of ONE specific code base.
Answer the developer's question using ONLY the facts and code snippets provided in the context. Rules:
- Ground every claim in the context. Cite snippets inline as [1], [2] … matching the numbered sources.
- Prefer concrete names (classes, methods, endpoints, files) over generic advice.
- Facts marked "Digital Twin facts" were computed by static analysis (AST + dependency graph) — treat them as authoritative.
- If the context is insufficient, say what is missing instead of guessing.
- Format with short paragraphs, bullet lists and `code` formatting. Keep it under ~350 words unless asked for detail.
- When describing a flow, walk through it step by step (Frontend → API → Controller → Service → Repository → Database)."""


def _unit_lookup(twin: dict) -> dict[str, str]:
    look = {}
    for uid, u in twin["units"].items():
        if u["is_test"]:
            continue
        n = u["name"]
        look[n.lower()] = uid
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", n).lower()
        look[spaced] = uid
    return look


def mentioned_units(twin: dict, text: str) -> list[str]:
    look = _unit_lookup(twin)
    t = text.lower()
    found = []
    for key in sorted(look, key=len, reverse=True):
        if len(key) < 3:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", t):
            uid = look[key]
            if uid not in found:
                found.append(uid)
                t = t.replace(key, " ")
    return found[:5]


def _name(twin, nid):
    if nid in twin["units"]:
        return twin["units"][nid]["name"]
    if nid in twin["endpoints"]:
        e = twin["endpoints"][nid]
        return f"{e['method']} {e['path']}"
    if nid in twin["tables"]:
        return "table " + twin["tables"][nid]["name"]
    return nid


def call_flow(twin: dict, uid: str, method: str, depth: int = 0, max_depth: int = 4, seen=None) -> list[str]:
    """Follow resolved method calls to describe a request flow."""
    seen = seen or set()
    u = twin["units"].get(uid)
    if not u or (uid, method) in seen or depth > max_depth:
        return []
    seen.add((uid, method))
    m = next((x for x in u["methods"] if x["name"] == method), None)
    if not m:
        return []
    out = []
    for c in m.get("resolvedCalls", []):
        t = twin["units"].get(c["target"])
        if not t or c["target"] == uid and c["method"] == method:
            continue
        if t["layer"] in {"entity", "dto"}:
            continue
        out.append(f"{'  ' * depth}- {u['name']}.{method}() → {t['name']}.{c['method']}()  (line {c['line']})")
        if t["layer"] == "repository":
            ent = next((e["target"] for e in twin["edges"] if e["source"] == t["id"] and "persists" in e["types"]), None)
            tbl = next((tid for tid, tb in twin["tables"].items() if tb["entity"] == ent), None)
            if tbl:
                out.append(f"{'  ' * (depth + 1)}- {t['name']} → database table `{twin['tables'][tbl]['name']}`")
        else:
            out += call_flow(twin, c["target"], c["method"], depth + 1, max_depth, seen)
        if len(out) > 40:
            break
    return out


def gather_facts(twin: dict, tg: TwinGraph, question: str, mentioned: list[str], index: Index | None) -> tuple[list[str], dict]:
    q = question.lower()
    s = twin["summary"]
    facts: list[str] = []
    extra: dict = {}
    units = twin["units"]

    if re.search(r"explain (this|the) (project|app|application|system|codebase)|what does (this|the) (project|app|system) do|overview|summar|architecture of", q) or q.strip() in {"explain", "explain this"}:
        c = s["counts"]
        facts.append(f"Project {s['name']}: architecture style = {s['architecture']}. Languages: {', '.join(f'{k} ({v} files)' for k, v in s['languages'].items())}. "
                     f"Frameworks: {', '.join(f['name'] for f in s['frameworks'])}. Databases: {', '.join(s['databases']) or 'none detected'}.")
        facts.append(f"Size: {c['files']} source files, {c['loc']} lines of code, {c['units']} components, {c['functions']} functions, {c['modules']} modules, "
                     f"{c['endpoints']} REST endpoints, {c['tables']} database tables, {c['dependencies']} internal dependencies.")
        mods = sorted(twin["modules"], key=lambda m: -m["loc"])
        facts.append("Modules: " + "; ".join(f"{m['name']} ({m['app'] or 'root'}, {len(m['units'])} components: "
                                             f"{', '.join(units[u]['name'] for u in m['units'][:5])})" for m in mods[:14]))
        facts.append(f"Architecture health {twin['health']['overall']}/100 (grade {twin['health']['grade']}); technical debt {twin['debt']['level']} "
                     f"(~{twin['debt']['hours']} h); {s['counts']['high_risk']} high-risk components.")
        if s["entry_points"]:
            facts.append("Entry points: " + ", ".join(_name(twin, e) for e in s["entry_points"]))
    if re.search(r"most (critical|important|central)|critical (module|component|service)|core (module|component)", q):
        rows = []
        for uid in s["critical"]:
            u = units[uid]
            m = u["metrics"]
            rows.append(f"{u['name']} ({u['layer']}): {m['dependents_transitive']} transitive dependents, fan-in {m['fan_in']}, PageRank {m['pagerank']}, "
                        f"WMC {m['wmc']}, risk {u['risk']['level']}")
        facts.append("Most critical components (ranked by transitive dependents + PageRank centrality + complexity): " + " | ".join(rows))
        mods = sorted(twin["modules"], key=lambda m: -(m["metrics"].get("ca", 0) * 2 + m["wmc"] / 10))
        facts.append("Most depended-upon modules (afferent coupling Ca): " + ", ".join(f"{m['name']} (Ca={m['metrics'].get('ca', 0)}, "
                                                                                    f"I={m['metrics'].get('instability', 0)})" for m in mods[:5]))
    if re.search(r"(most|highest) complex|complexity|hardest to (read|understand|maintain)", q):
        top = sorted([u for u in units.values() if not u["is_test"]], key=lambda u: -u["metrics"]["logic"])[:6]
        facts.append("Most complex components (weighted method complexity): " + "; ".join(
            f"{u['name']} WMC {u['metrics']['wmc']} (worst method CC {u['metrics']['max_cc']}, {u['metrics']['methods']} methods)" for u in top))
        meths = sorted([(u, m) for u in units.values() if not u["is_test"] for m in u["methods"]], key=lambda x: -x[1]["complexity"])[:5]
        facts.append("Most complex methods: " + "; ".join(f"{u['name']}.{m['name']}() CC {m['complexity']}" for u, m in meths))
    if re.search(r"risk|bug|fragile|hotspot|likely to (break|fail)|danger", q):
        hr = [units[x] for x in s["high_risk"]] or sorted([u for u in units.values() if not u["is_test"]], key=lambda u: -u["risk"]["score"])[:5]
        facts.append("Highest defect-risk components (complexity × change frequency × centrality model): " + " | ".join(
            f"{u['name']} risk {u['risk']['score']:.2f} – {'; '.join(u['risk']['reasons'][:3])}" for u in hr[:6]))
    if re.search(r"unused|dead|never (called|used)|orphan", q):
        if re.search(r"api|endpoint|route", q) or not re.search(r"class|code|component", q):
            ue = [twin["endpoints"][e] for e in s["unused_endpoints"]]
            facts.append("Endpoints with no detected frontend consumer and no test: " + (", ".join(f"{e['method']} {e['path']} "
                         f"({units[e['unit']]['name']}.{e['handler']})" for e in ue) or "none"))
        if s["possibly_dead"]:
            facts.append("Components nothing depends on (possible dead code): " + ", ".join(units[x]["name"] for x in s["possibly_dead"]))
    if re.search(r"health|quality|score|maintainab|technical debt|\bdebt\b", q):
        h = twin["health"]
        facts.append(f"Architecture health {h['overall']}/100: " + "; ".join(f"{k} {v['score']} ({v['summary']})" for k, v in h["dimensions"].items()))
        d = twin["debt"]
        facts.append(f"Technical debt: {d['hours']} hours remediation, debt ratio {d['ratio'] * 100:.1f}% (rating {d['rating']}). Top files: " +
                     "; ".join(f"{f['path'].split('/')[-1]} ({f['minutes']} min: {', '.join(f['reasons'][:2])})" for f in d["files"][:5]))
    if re.search(r"secur|vulnerab|owasp|secret|inject|xss", q):
        sec = [i for i in twin["issues"] if i["category"] == "security"]
        facts.append("Security findings: " + (" | ".join(f"[{i['severity']}] {i['title']} at {i['file']}:{i['line']} – {i['detail']}" for i in sec[:10]) or "none"))
    if re.search(r"(list|all|which|show).*(endpoints|apis|routes)", q):
        eps = list(twin["endpoints"].values())
        facts.append(f"{len(eps)} endpoints: " + "; ".join(f"{e['method']} {e['path']} → {units[e['unit']]['name']}.{e['handler']}" for e in eps[:40]))

    # impact / dependency questions
    pq = parse_question(question)
    tgt = mentioned[0] if mentioned else (tg.resolve(pq["target"]) if pq else None)
    if tgt and (pq or re.search(r"depend|affect|break|impact|calls?|uses?|who", q)):
        if pq and pq["change"] in {"remove"}:
            w = whatif(tg, "remove", tgt)
            extra["whatif"] = w
            facts.append(f"What-if remove {units[tgt]['name']}: verdict {w['verdict']}. " + " | ".join(w["consequences"]))
        imp = analyze_impact(tg, tgt, "modify")
        extra["impact"] = {"target": tgt, "risk": imp["risk"], "stats": imp["stats"]}
        facts.append(f"Impact analysis for changing {units[tgt]['name']}: {imp['summary']} Risk {imp['risk']['level']} ({imp['risk']['score']}/100) because "
                     + "; ".join(imp["risk"]["reasons"]) + ".")
        facts.append("Direct dependents: " + (", ".join(f"{a['name']} ({a['via']})" for a in imp["affected"] if a["distance"] == 1) or "none"))
        if imp["chains"]:
            facts.append("Propagation chains: " + " | ".join(" → ".join(x["name"] for x in ch) for ch in imp["chains"][:4]))
        if imp["data"]:
            facts.append("Data touched: " + ", ".join(f"{d['name']} via {' → '.join(_name(twin, x) for x in d['path'])}" for d in imp["data"]))
        if imp["tests"]:
            facts.append("Tests to re-run: " + ", ".join(t["name"] for t in imp["tests"]))
        deps = [_name(twin, d["id"]) for d in imp["downstream"]]
        facts.append(f"{units[tgt]['name']} itself depends on: {', '.join(deps) or 'nothing'}")
    elif mentioned:
        for uid in mentioned[:2]:
            u = units[uid]
            m = u["metrics"]
            facts.append(f"{u['name']} is a {u['layer']} in {u['file']} (lines {u['line']}-{u['endLine']}); {m['methods']} methods, WMC {m['wmc']}, "
                         f"fan-in {m['fan_in']}, fan-out {m['fan_out']}, {m['dependents_transitive']} transitive dependents, risk {u['risk']['level']}, "
                         f"tests: {'yes' if m['tested'] else 'none found'}.")
            eps = [e for e in twin["endpoints"].values() if e["unit"] == uid]
            if eps:
                facts.append(f"{u['name']} exposes: " + ", ".join(f"{e['method']} {e['path']}" for e in eps))

    # request flow for "how does X work / what happens when"
    if re.search(r"how does|how do|what happens when|flow|workflow|process|step", q) and index:
        hits = index.search(question, k=3, kinds={"api"})
        for h in hits[:2]:
            ep = twin["endpoints"].get(h["id"])
            if not ep:
                continue
            flow = call_flow(twin, ep["unit"], ep["handler"])
            cons = [units[c]["name"] for c in ep.get("consumers", []) if c in units]
            facts.append(f"Request flow for {ep['method']} {ep['path']}" + (f" (called by frontend {', '.join(cons)})" if cons else "") + ":\n"
                         + "\n".join(flow[:25]))
    return facts, extra


def build_context(twin, tg, index, question, settings) -> dict:
    mentioned = mentioned_units(twin, question)
    facts, extra = gather_facts(twin, tg, question, mentioned, index)
    sources = []
    if index:
        qv = embed_query(question, settings) if settings.get("embeddings") != "none" and index.vectors is not None else None
        hits = index.search(question, k=8, boost_units=set(mentioned), query_vec=qv)
        # make sure headers of explicitly mentioned components are present
        for uid in mentioned[:2]:
            hdr = next((c for c in index.chunks if c["id"] == f"{uid}#header"), None)
            if hdr and all(h["id"] != hdr["id"] for h in hits):
                hits.insert(0, {**{k: v for k, v in hdr.items() if k != "search_text"}, "score": 0})
        for n, h in enumerate(hits[:9], start=1):
            sources.append({"n": n, "id": h["id"], "name": h["name"], "kind": h["kind"], "file": h["file"], "start": h["start"],
                            "end": h["end"], "unit": h.get("unit"), "meta": h.get("meta", ""), "text": h["text"]})
    return {"facts": facts, "sources": sources, "mentioned": mentioned, "extra": extra}


def render_prompt(ctx: dict, question: str) -> str:
    parts = []
    if ctx["facts"]:
        parts.append("## Digital Twin facts (static analysis)\n" + "\n".join(f"- {f}" for f in ctx["facts"]))
    if ctx["sources"]:
        parts.append("## Code context")
        for s in ctx["sources"]:
            parts.append(f"[{s['n']}] {s['name']} — {s['file']}:{s['start']}-{s['end']} ({s['kind']})\n{s['meta']}\n```\n{s['text'][:1800]}\n```")
    parts.append(f"## Question\n{question}")
    return "\n\n".join(parts)


def offline_answer(ctx: dict, question: str) -> str:
    out = ["*Offline mode — no LLM is configured, so this answer is assembled directly from the Digital Twin. "
           "Add an API key in Settings for natural-language explanations.*\n"]
    if ctx["facts"]:
        out.append("**What the Digital Twin knows**\n")
        for f in ctx["facts"]:
            if "\n" in f:
                head, rest = f.split("\n", 1)
                out.append(f"- {head}\n{rest}")
            else:
                out.append(f"- {f}")
    if ctx["sources"]:
        out.append("\n**Most relevant code**\n")
        for s in ctx["sources"][:6]:
            out.append(f"- [{s['n']}] `{s['name']}` — {s['file']}:{s['start']} · {s['meta'][:160]}")
    if not ctx["facts"] and not ctx["sources"]:
        out.append("I couldn't find anything related in this project. Try naming a class, endpoint or feature.")
    return "\n".join(out)


def stream_answer(twin: dict, tg: TwinGraph, index: Index | None, question: str, history: list[dict], settings: dict) -> Iterator[dict]:
    ctx = build_context(twin, tg, index, question, settings)
    provider = get_provider(settings)
    mode = provider.name if provider.available() else "offline"
    yield {"type": "meta", "mode": mode, "model": provider.model, "facts": ctx["facts"], "mentioned": ctx["mentioned"],
           "sources": [{k: v for k, v in s.items() if k != "text"} | {"snippet": s["text"][:900]} for s in ctx["sources"]],
           "extra": ctx["extra"]}
    if mode == "offline":
        yield {"type": "token", "text": offline_answer(ctx, question)}
        yield {"type": "done"}
        return
    msgs = []
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"][:4000]})
    msgs.append({"role": "user", "content": render_prompt(ctx, question)})
    try:
        for tok in provider.stream(SYSTEM, msgs, max_tokens=1400):
            yield {"type": "token", "text": tok}
    except LLMError as e:
        yield {"type": "token", "text": f"\n\n> LLM error: {e}\n\n" + offline_answer(ctx, question)}
    yield {"type": "done"}


EXPLAIN_SYSTEM = """You are CodeTwin, a senior software architect. You receive the deterministic output of a static-analysis engine
(metrics, graphs, simulations) for one code base. Explain it to a developer: what it means, why it matters, and what to do next.
Never invent numbers – only use the ones provided. Be specific (name classes, files, methods). Use short markdown sections and bullets; max ~300 words."""


def explain(kind: str, payload: dict, settings: dict) -> Iterator[str]:
    provider = get_provider(settings)
    data = json.dumps(payload, default=str)[:14000]
    if not provider.available():
        yield offline_explain(kind, payload)
        return
    prompt = f"Analysis type: {kind}\n\nEngine output (JSON):\n```json\n{data}\n```\n\nExplain this result."
    try:
        yield from provider.stream(EXPLAIN_SYSTEM, [{"role": "user", "content": prompt}], max_tokens=900)
    except LLMError as e:
        yield f"> LLM error: {e}\n\n" + offline_explain(kind, payload)


def offline_explain(kind: str, p: dict) -> str:
    if kind == "health":
        dims = p.get("dimensions", {})
        worst = sorted(dims.items(), key=lambda kv: kv[1]["score"])[:3]
        best = sorted(dims.items(), key=lambda kv: -kv[1]["score"])[:2]
        strongest = ", ".join(f"{k} ({v['score']})" for k, v in best)
        return (f"**Overall {p.get('overall')}/100 (grade {p.get('grade')}).**\n\n"
                f"Strongest areas: {strongest}.\n\n"
                f"Weakest areas — fix these first:\n" + "\n".join(f"- **{k} {v['score']}** — {v['summary']}" for k, v in worst) +
                "\n\n*Scores are computed from measured metrics (complexity, coupling, cycles, Maintainability Index, test and doc coverage, rule findings).*")
    if kind == "impact":
        r = p.get("risk", {})
        return (f"**Risk {r.get('level')} ({r.get('score')}/100).** {p.get('summary', '')}\n\n" + "\n".join(f"- {x}" for x in r.get("reasons", [])) +
                "\n\n**Before merging:** review the direct dependents, run the listed tests and smoke-test the affected endpoints.")
    if kind == "whatif":
        return ("**Verdict: " + str(p.get("verdict", p.get("readiness", ""))) + "**\n\n" +
                ("**Benefits**\n" + "\n".join(f"- {b}" for b in p.get("benefits", [])) + "\n\n" if p.get("benefits") else "") +
                ("**Risks**\n" + "\n".join(f"- {b}" for b in p.get("risks", [])) + "\n\n" if p.get("risks") else "") +
                ("**Consequences**\n" + "\n".join(f"- {b}" for b in p.get("consequences", [])) if p.get("consequences") else ""))
    if kind == "refactoring":
        return (f"**{p.get('title')}**\n\n**Problem.** {p.get('problem')}\n\n**Principle.** {p.get('principle')}\n\n"
                f"**Suggested design.** {p.get('suggestion')}\n\n" +
                "\n".join(f"- `{x.get('name')}` — {x.get('responsibility', '')}" for x in p.get("proposed", [])) +
                f"\n\n**Benefit.** {p.get('benefit')}\n\n*Estimated effort: ~{p.get('effort_hours')} h.*")
    return "```json\n" + json.dumps(p, indent=2, default=str)[:3000] + "\n```"
