"""Change-impact analysis and "What-If" architecture simulation on top of the Digital Twin graph."""
from __future__ import annotations

import re
from collections import Counter, defaultdict, deque

import networkx as nx

from . import graph as G


class TwinGraph:
    """In-memory graph view of a stored twin (rebuilt from twin.json)."""

    def __init__(self, twin: dict):
        self.twin = twin
        self.units = twin["units"]
        self.endpoints = twin["endpoints"]
        self.tables = twin["tables"]
        self.g = G.build_graph(self.units, self.endpoints, self.tables, twin["edges"])
        self.h = G.unit_graph(self.g, include_tests=False)
        self.implements = defaultdict(list)  # impl -> [interfaces]
        for e in twin["edges"]:
            if set(e["types"]) & {"implements", "inherits"}:
                self.implements[e["source"]].append(e["target"])

    def node(self, nid: str) -> dict:
        if nid in self.units:
            u = self.units[nid]
            return {"id": nid, "name": u["name"], "kind": "unit", "layer": u["layer"], "module": u["module"], "file": u["file"],
                    "line": u["line"], "language": u["language"], "test": u["is_test"], "risk": u.get("risk", {}).get("level", "low")}
        if nid in self.endpoints:
            e = self.endpoints[nid]
            return {"id": nid, "name": f"{e['method']} {e['path']}", "kind": "endpoint", "layer": "endpoint", "module": None,
                    "file": e["file"], "line": e["line"], "test": False, "risk": "low"}
        if nid in self.tables:
            t = self.tables[nid]
            return {"id": nid, "name": t["name"], "kind": "table", "layer": "table", "module": None, "file": None, "line": None,
                    "test": False, "risk": "low"}
        return {"id": nid, "name": nid, "kind": "unknown", "layer": "unknown"}

    def resolve(self, query: str) -> str | None:
        """Find a node by id, name, file or fuzzy name."""
        if not query:
            return None
        if query in self.g:
            return query
        q = query.strip().lower().replace("()", "")
        for uid, u in self.units.items():
            if u["name"].lower() == q or u["file"].lower() == q or u["file"].lower().endswith("/" + q):
                return uid
        for eid, e in self.endpoints.items():
            if q in (f"{e['method']} {e['path']}".lower(), e["path"].lower()):
                return eid
        for tid, t in self.tables.items():
            if t["name"].lower() == q:
                return tid
        cands = [uid for uid, u in self.units.items() if q in u["name"].lower() and not u["is_test"]]
        cands.sort(key=lambda x: len(self.units[x]["name"]))
        return cands[0] if cands else None


# ===================================================================================== impact
def analyze_impact(tg: TwinGraph, target: str, change: str = "modify", method: str | None = None, max_depth: int = 6) -> dict:
    g, units = tg.g, tg.units
    if target not in g:
        raise KeyError(target)
    dist: dict[str, int] = {target: 0}
    parent: dict[str, str | None] = {target: None}
    via: dict[str, str] = {}
    q = deque([target])

    seeds = None
    if change == "signature" and method and target in units:
        # Only direct callers of this method break at compile time
        seeds = [uid for uid, u in units.items() for m in u["methods"] for c in m.get("resolvedCalls", [])
                 if c["target"] == target and c["method"] == method and uid != target]
        q = deque()
        for s in dict.fromkeys(seeds):
            dist[s], parent[s], via[s] = 1, target, f"calls {method}()"
            q.append(s)
        # controllers' endpoints using this method are also direct
    while q:
        n = q.popleft()
        if dist[n] >= max_depth:
            continue
        preds = list(g.predecessors(n))
        # runtime polymorphism: dependents of an interface reach its implementations
        for iface in tg.implements.get(n, []):
            for p in g.predecessors(iface):
                if p != n:
                    preds.append(p)
                    via.setdefault(p, f"via interface {tg.node(iface)['name']}")
        for p in preds:
            if p in dist:
                continue
            ed = g.get_edge_data(p, n)
            dist[p] = dist[n] + 1
            parent[p] = n
            if p not in via:
                via[p] = ", ".join(ed["types"]) if ed else "depends"
            q.append(p)

    affected, endpoints, frontend, tests = [], [], [], []
    for nid, d in sorted(dist.items(), key=lambda kv: kv[1]):
        if nid == target:
            continue
        info = tg.node(nid)
        likelihood = "direct" if d == 1 else "indirect" if d == 2 else "transitive"
        if change == "signature" and d >= 2:
            likelihood = "possible"
        path = _path(parent, nid)
        row = {**info, "distance": d, "likelihood": likelihood, "via": via.get(nid, ""), "path": path}
        if info.get("test"):
            tests.append(row)
        elif info["kind"] == "endpoint":
            endpoints.append(row)
        else:
            affected.append(row)
            if info.get("language") in ("TypeScript", "JavaScript") and info["layer"] in {"page", "component", "hook", "api", "context", "entry", "store"}:
                frontend.append(row)
    # data touched downstream (what the target reads/writes): target -> repository -> entity -> table
    data, downstream = [], []
    if target in units or target in tg.endpoints:
        downstream = [tg.node(d) for d in g.successors(target)]
        seen = set()
        for tid, path in _data_paths(tg, target):
            if tid not in seen:
                seen.add(tid)
                data.append({**tg.node(tid), "path": path})
    risk = _impact_risk(tg, target, affected, endpoints, frontend, tests, change)
    chains = _chains(tg, parent, dist, target, endpoints, frontend)
    modules = sorted({a["module"] for a in affected if a.get("module")})
    return {
        "target": tg.node(target), "change": change, "method": method,
        "risk": risk,
        "summary": _impact_sentence(tg, target, affected, endpoints, frontend, data, change, method),
        "affected": affected, "endpoints": endpoints, "frontend": frontend, "tests": tests,
        "data": data, "downstream": downstream, "modules": modules, "chains": chains,
        "stats": {"affected": len(affected), "direct": sum(1 for a in affected if a["distance"] == 1), "endpoints": len(endpoints),
                  "frontend": len(frontend), "tests": len(tests), "modules": len(modules), "tables": len(data)},
    }


def _table_of(tg, entity_id):
    return next((tid for tid, t in tg.tables.items() if t["entity"] == entity_id), None)


def _data_paths(tg, start):
    """Tables a component reads/writes directly or through the repositories it uses."""
    units, g = tg.units, tg.g
    out = []
    frontier = [(start, [start])]
    if start in tg.endpoints:
        frontier = [(s, [start, s]) for s in g.successors(start)]
    for node, path in frontier:
        if node in tg.tables:
            out.append((node, path))
            continue
        u = units.get(node, {})
        if u.get("layer") == "repository":
            for ent in g.successors(node):
                if units.get(ent, {}).get("layer") == "entity" and _table_of(tg, ent):
                    out.append((_table_of(tg, ent), path + [ent, _table_of(tg, ent)]))
        if u.get("layer") == "entity" and _table_of(tg, node):
            out.append((_table_of(tg, node), path + [_table_of(tg, node)]))
        for s in g.successors(node):
            su = units.get(s, {})
            if su.get("layer") == "repository" and not su.get("is_test"):
                for ent in g.successors(s):
                    if units.get(ent, {}).get("layer") == "entity" and _table_of(tg, ent):
                        out.append((_table_of(tg, ent), path + [s, ent, _table_of(tg, ent)]))
            elif s in tg.tables:
                out.append((s, path + [s]))
            elif su.get("layer") == "controller" or (start in tg.endpoints and su.get("layer") in {"service", "route"}):
                pass
        if start in tg.endpoints and u.get("layer") in {"controller", "route"}:
            for s in g.successors(node):
                if units.get(s, {}).get("layer") == "service":
                    for tid, p2 in _data_paths(tg, s):
                        out.append((tid, path + p2))
    return out


def _path(parent, nid):
    out = [nid]
    while parent.get(out[-1]) is not None:
        out.append(parent[out[-1]])
    return out  # affected -> ... -> target


def _forward_path(g, src, dst):
    try:
        return nx.shortest_path(g, src, dst)
    except Exception:
        return [src, dst]


def _chains(tg, parent, dist, target, endpoints, frontend):
    """Most informative propagation chains, rendered target-first (Target → … → consumer)."""
    leaves = [f["id"] for f in frontend] or [e["id"] for e in endpoints]
    if not leaves:
        leaves = [n for n, d in dist.items() if d == max(dist.values())]
    chains, seen = [], set()
    for leaf in sorted(leaves, key=lambda x: -dist.get(x, 0)):
        p = list(reversed(_path(parent, leaf)))
        key = tuple(p)
        if key in seen or len(p) < 2:
            continue
        seen.add(key)
        chains.append([{"id": x, "name": tg.node(x)["name"], "layer": tg.node(x)["layer"]} for x in p])
        if len(chains) >= 6:
            break
    return chains


def _impact_risk(tg, target, affected, endpoints, frontend, tests, change):
    u = tg.units.get(target, {})
    m = u.get("metrics", {})
    direct = sum(1 for a in affected if a["distance"] == 1)
    score = 0.0
    score += min(30, 4 * direct)
    score += min(20, 1.2 * len(affected))
    score += min(15, 2.5 * len(endpoints))
    score += min(10, 2 * len(frontend))
    score += 12 * u.get("risk", {}).get("score", 0)
    score += 8 if not m.get("tested", True) else 0
    in_cycle = any(target in c for c in tg.twin.get("cycles", []))
    score += 7 if in_cycle else 0
    if change == "remove":
        score += 10
    if change == "signature":
        score *= 0.8
    score = round(min(100, score))
    level = "HIGH" if score >= 60 else "MEDIUM" if score >= 32 else "LOW"
    reasons = []
    if direct:
        reasons.append(f"{direct} component(s) depend on it directly")
    if len(affected) > direct:
        reasons.append(f"{len(affected) - direct} more are affected transitively")
    if endpoints:
        reasons.append(f"{len(endpoints)} public API endpoint(s) sit on the propagation path")
    if frontend:
        reasons.append(f"{len(frontend)} frontend module(s) consume those APIs")
    if not m.get("tested", True) and target in tg.units:
        reasons.append("the component has no tests to catch regressions")
    if in_cycle:
        reasons.append("it is part of a dependency cycle")
    if m.get("max_cc", 0) > 10:
        reasons.append(f"it contains complex logic (max CC {m['max_cc']})")
    if tests:
        reasons.append(f"{len(tests)} existing test(s) cover the affected area — run them")
    return {"score": score, "level": level, "reasons": reasons}


def _impact_sentence(tg, target, affected, endpoints, frontend, data, change, method):
    name = tg.node(target)["name"]
    verb = {"modify": "Changing", "signature": f"Changing the signature of {method}() in", "remove": "Removing"}.get(change, "Changing")
    parts = [f"{verb} {name} can affect {len(affected)} component(s)"]
    if endpoints:
        parts.append(f"{len(endpoints)} API endpoint(s)")
    if frontend:
        parts.append(f"{len(frontend)} frontend module(s)")
    s = ", ".join(parts)
    if data:
        s += f"; it reads/writes {', '.join(d['name'] for d in data[:4])}"
    return s + "."


# ===================================================================================== what-if
def feature_name(ep: dict) -> str:
    segs = [s for s in ep["path"].strip("/").split("/") if s and not s.startswith("{") and s != "api"]
    if not segs:
        return ep["path"]
    words = " ".join(segs[-2:]).replace("-", " ")
    verb = {"GET": "view", "POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "update"}.get(ep["method"], "")
    if len(segs) >= 2 and segs[-1] in {"login", "register", "cancel", "ship", "search", "dashboard", "total", "forgot-password", "items"}:
        return f"{segs[-2]}: {segs[-1].replace('-', ' ')}"
    return f"{segs[0]}: {verb} {words if len(segs) > 1 else ''}".strip()


def whatif_remove(tg: TwinGraph, target: str) -> dict:
    imp = analyze_impact(tg, target, "remove")
    units = tg.units
    broken = [a for a in imp["affected"] if a["distance"] == 1]
    orphans = []
    if target in tg.h:
        for d in tg.h.successors(target):
            others = [p for p in tg.h.predecessors(d) if p != target]
            if not others and units[d]["layer"] not in {"entity", "config"}:
                orphans.append(tg.node(d))
    features = defaultdict(list)
    for e in imp["endpoints"]:
        ep = tg.endpoints[e["id"]]
        features[feature_name(ep)].append(f"{ep['method']} {ep['path']}")
    pages = [f["name"] for f in imp["frontend"] if f["layer"] in {"page", "component", "entry"}]
    consequences = []
    if broken:
        consequences.append(f"Compilation/import errors in {len(broken)} component(s): {', '.join(b['name'] for b in broken[:8])}")
    for feat, eps in sorted(features.items()):
        consequences.append(f"Feature affected — {feat} ({', '.join(eps[:3])})")
    if pages:
        consequences.append(f"Frontend screens affected: {', '.join(sorted(set(pages))[:10])}")
    if orphans:
        consequences.append(f"Becomes dead code (only used by {tg.node(target)['name']}): {', '.join(o['name'] for o in orphans)}")
    if imp["data"]:
        consequences.append(f"No longer accessed through this path: {', '.join(d['name'] for d in imp['data'])}")
    return {"scenario": "remove", "target": imp["target"], "impact": imp, "broken": broken, "orphans": orphans,
            "features": [{"name": k, "endpoints": v} for k, v in sorted(features.items())], "consequences": consequences,
            "verdict": "Unsafe without replacement" if broken else "Safe to remove"}


def whatif_replace(tg: TwinGraph, target: str) -> dict:
    u = tg.units[target]
    contract = defaultdict(lambda: {"callers": set(), "signature": None})
    for uid, other in tg.units.items():
        if uid == target:
            continue
        for m in other["methods"]:
            for c in m.get("resolvedCalls", []):
                if c["target"] == target:
                    contract[c["method"]]["callers"].add(other["name"])
    sigs = {m["name"]: m for m in u["methods"]}
    rows = []
    for name, info in sorted(contract.items(), key=lambda kv: -len(kv[1]["callers"])):
        m = sigs.get(name)
        sig = f"{m.get('returnType') or ''} {name}({', '.join(m.get('params', []))})".strip() if m else f"{name}(…)"
        rows.append({"method": name, "signature": sig, "callers": sorted(info["callers"])})
    eps = [e for e in tg.endpoints.values() if e["unit"] == target]
    imp = analyze_impact(tg, target, "modify")
    unused = [m["name"] for m in u["methods"] if m.get("public") and not m.get("constructor") and m["name"] not in contract]
    return {"scenario": "replace", "target": tg.node(target), "contract": rows,
            "interfaces": [tg.node(i)["name"] for i in tg.implements.get(target, [])],
            "endpoints": [f"{e['method']} {e['path']}" for e in eps], "unused_public_methods": unused,
            "impact": imp,
            "consequences": [f"A replacement must implement {len(rows)} method(s) used by {len({c for r in rows for c in r['callers']})} caller(s)."]
            + ([f"It must keep {len(eps)} HTTP endpoint(s) stable for clients."] if eps else [])
            + ([f"Implementing {', '.join(tg.implements.get(target, []) and [tg.node(i)['name'] for i in tg.implements[target]])} keeps callers unchanged (swap the bean)."]
               if tg.implements.get(target) else [])
            + ([f"{len(unused)} public method(s) are never called and need not be ported: {', '.join(unused[:6])}"] if unused else [])}


def _boundary(tg: TwinGraph, members: set[str]) -> dict:
    units = tg.units
    inbound, outbound = defaultdict(set), defaultdict(set)
    inbound_edges, outbound_edges, internal = 0, 0, 0
    for s, t, d in tg.h.edges(data=True):
        if s in members and t in members:
            internal += 1
        elif t in members:
            inbound_edges += 1
            calls = [c["method"] for m in units[s]["methods"] for c in m.get("resolvedCalls", []) if c["target"] == t]
            for c in calls or ["(type reference)"]:
                inbound[f"{units[t]['name']}.{c}" if not c.startswith("(") else f"{units[t]['name']} {c}"].add(units[s]["name"])
        elif s in members:
            outbound_edges += 1
            calls = [c["method"] for m in units[s]["methods"] for c in m.get("resolvedCalls", []) if c["target"] == t]
            for c in calls or ["(type reference)"]:
                outbound[f"{units[t]['name']}.{c}" if not c.startswith("(") else f"{units[t]['name']} {c}"].add(units[s]["name"])
    # data ownership: a table is accessed by its repository and by whoever calls that repository
    owned_tables, shared_tables = [], []
    for tid, t in tg.tables.items():
        repos = [r for r, u in units.items() if u["layer"] == "repository" and t["entity"] in tg.g and tg.g.has_edge(r, t["entity"])]
        users = set(repos)
        for r in repos:
            users |= {p for p in tg.g.predecessors(r) if p in units and not units[p]["is_test"]}
        if t["entity"] in units and units[t["entity"]]["language"] != "Java":
            users.add(t["entity"])
        if not users & members and t["entity"] not in members:
            continue
        outside = {x for x in users if x not in members}
        row = {"table": t["name"], "used_outside_by": sorted(units[x]["name"] for x in outside)}
        (shared_tables if outside else owned_tables).append(row)
    # distributed transactions: @Transactional methods outside that call into members
    dtx = []
    for uid, u in units.items():
        if uid in members or u["is_test"]:
            continue
        for m in u["methods"]:
            if "Transactional" in (m.get("annotations") or []) and any(c["target"] in members for c in m.get("resolvedCalls", [])):
                dtx.append(f"{u['name']}.{m['name']}()")
    cyc = [c for c in tg.twin.get("cycles", []) if set(c) & members and set(c) - members]
    cohesion = internal / max(1, internal + inbound_edges + outbound_edges)
    return {"inbound": {k: sorted(v) for k, v in inbound.items()}, "outbound": {k: sorted(v) for k, v in outbound.items()},
            "inbound_edges": inbound_edges, "outbound_edges": outbound_edges, "internal_edges": internal,
            "owned_tables": owned_tables, "shared_tables": shared_tables, "distributed_transactions": dtx,
            "crossing_cycles": [[units[x]["name"] for x in c] for c in cyc], "cohesion": round(cohesion, 2)}


def whatif_extract(tg: TwinGraph, members: set[str], name: str | None = None) -> dict:
    units = tg.units
    members = {m for m in members if m in units and not units[m]["is_test"]}
    b = _boundary(tg, members)
    files = {units[m]["file"] for m in members}
    file_rows = {f["path"]: f for f in tg.twin["files"]}
    loc = sum(file_rows.get(f, {}).get("sloc", 0) for f in files)
    total_loc = tg.twin["summary"]["counts"]["loc"] or 1
    churn = sum(file_rows.get(f, {}).get("churn", 0) for f in files)
    total_churn = sum(f.get("churn", 0) for f in tg.twin["files"]) or 1
    eps = [e for e in tg.endpoints.values() if e["unit"] in members]
    new_api = len(b["inbound"])
    remote_out = len(b["outbound"])
    readiness = 100 - 5 * new_api - 4 * remote_out - 12 * len(b["shared_tables"]) - 10 * len(b["distributed_transactions"]) \
        - 15 * len(b["crossing_cycles"]) + 20 * b["cohesion"]
    readiness = max(0, min(100, round(readiness)))
    latency = 4 * (min(new_api, 10) + min(remote_out, 10))  # ~4 ms per synchronous in-DC hop on hot paths (assumption)
    benefits = [f"Independent deployment of {loc} LOC ({loc * 100 // total_loc}% of the codebase)."]
    if churn:
        benefits.append(f"Isolates {churn * 100 // total_churn}% of historical change activity — releases of this area stop blocking others.")
    if eps:
        benefits.append(f"Can scale its {len(eps)} endpoint(s) independently of the rest of the system.")
    if b["cohesion"] >= 0.5:
        benefits.append(f"High cohesion ({b['cohesion']:.0%} of its dependencies are internal).")
    risks = []
    if b["shared_tables"]:
        risks.append(f"Shared data: {', '.join(t['table'] for t in b['shared_tables'])} also used by "
                     f"{', '.join(sorted({x for t in b['shared_tables'] for x in t['used_outside_by']}))} — needs an API or data replication.")
    if b["distributed_transactions"]:
        risks.append(f"{len(b['distributed_transactions'])} transaction(s) would span services ({', '.join(b['distributed_transactions'][:3])}) — "
                     f"requires the Saga pattern or eventual consistency.")
    if b["crossing_cycles"]:
        risks.append("Dependency cycle across the boundary (" + "; ".join(" ↔ ".join(c) for c in b["crossing_cycles"]) + ") — would become a "
                     "chatty, tightly-coupled service pair.")
    if new_api > 6:
        risks.append(f"Chatty interface: {new_api} operations are called from outside.")
    if not risks:
        risks.append("Few blockers detected; main cost is operational (another deployable, monitoring, network failures).")
    return {
        "scenario": "extract", "name": name or _name_for(units, members), "members": [tg.node(m) for m in sorted(members)],
        "boundary": b, "loc": loc, "endpoints": [f"{e['method']} {e['path']}" for e in eps],
        "estimates": {
            "new_remote_operations": new_api, "outbound_remote_calls": remote_out,
            "added_latency_ms": latency, "deployables_delta": 1, "databases_delta": 1 if b["owned_tables"] else 0,
            "monthly_cost_usd": [25 + (15 if b["owned_tables"] else 0), 60 + (40 if b["owned_tables"] else 0)],
            "deployment_complexity": "High" if readiness < 45 else "Medium" if readiness < 70 else "Low",
        },
        "readiness": readiness, "benefits": benefits, "risks": risks,
        "assumptions": ["~4 ms per synchronous call between services in the same region", "one small container (0.5 vCPU / 1 GB) per service",
                        "a managed database instance only when the service owns tables"],
    }


def _name_for(units, members):
    mods = Counter(units[m]["module"].split("::")[-1] for m in members)
    top = mods.most_common(1)[0][0] if mods else "new"
    return f"{top}-service"


def module_members(tg: TwinGraph, module_or_unit: str) -> set[str]:
    if module_or_unit in tg.units:
        u = tg.units[module_or_unit]
        return {x for x, v in tg.units.items() if v["module"] == u["module"] and not v["is_test"]}
    return {x for x, v in tg.units.items() if v["module"] == module_or_unit and not v["is_test"]}


def whatif_split(tg: TwinGraph, resolution: float = 1.0) -> dict:
    """Propose microservice boundaries with Louvain community detection on the backend dependency graph."""
    units = tg.units
    backend = {uid for uid, u in units.items() if not u["is_test"] and u["language"] in ("Java",) or
               (not u["is_test"] and u["layer"] in {"route", "model"} and u["language"] != "Java")}
    backend = {b for b in backend if units[b]["layer"] not in {"config", "dto", "exception", "util", "entry"}}
    if not backend:
        backend = {uid for uid, u in units.items() if not u["is_test"]}
    sub = tg.h.subgraph(backend).copy()
    comms = G.louvain(sub, resolution=resolution)
    comms = [c for c in comms if c]
    services = []
    for c in sorted(comms, key=lambda c: -len(c)):
        ext = whatif_extract(tg, set(c))
        layers = Counter(units[m]["layer"] for m in c)
        services.append({"name": ext["name"], "members": ext["members"], "loc": ext["loc"], "endpoints": ext["endpoints"],
                         "tables": [t["table"] for t in ext["boundary"]["owned_tables"] + ext["boundary"]["shared_tables"]],
                         "inbound": ext["boundary"]["inbound_edges"], "outbound": ext["boundary"]["outbound_edges"],
                         "cohesion": ext["boundary"]["cohesion"], "layers": dict(layers), "readiness": ext["readiness"]})
    # de-duplicate names
    seen = Counter()
    for s in services:
        seen[s["name"]] += 1
        if seen[s["name"]] > 1:
            s["name"] = f"{s['name']}-{seen[s['name']]}"
    member_svc = {m["id"]: s["name"] for s in services for m in s["members"]}
    cross = Counter()
    for s, t in sub.edges():
        if member_svc.get(s) != member_svc.get(t):
            cross[(member_svc.get(s), member_svc.get(t))] += 1
    table_users = defaultdict(set)
    for s in services:
        for t in s["tables"]:
            table_users[t].add(s["name"])
    shared = {t: sorted(v) for t, v in table_users.items() if len(v) > 1}
    # agreement with the existing package structure
    agree = 0
    for s in services:
        mods = Counter(m["module"] for m in s["members"])
        agree += mods.most_common(1)[0][1] if mods else 0
    alignment = round(agree / max(1, sum(len(s["members"]) for s in services)), 2)
    n = len(services)
    cross_calls = sum(cross.values())
    latency = 4 * min(cross_calls, 25)
    cost = [n * 25 + len([s for s in services if s["tables"]]) * 15 + 30, n * 60 + len([s for s in services if s["tables"]]) * 40 + 80]
    perf = "Slower" if cross_calls > 2 * n else "Similar"
    complexity = "Very high" if n >= 7 else "High" if n >= 4 else "Medium"
    benefits = [f"{n} independently deployable services aligned to {alignment:.0%} with your current package structure.",
                "Teams can own and release services independently; failures are isolated per service.",
                "Hot services (e.g. catalogue reads) can be scaled without scaling the whole monolith."]
    risks = [f"{cross_calls} in-process dependencies become network calls (~{latency} ms added on the worst request path, plus partial-failure handling).",
             f"{len(shared)} table(s) are shared between proposed services: {', '.join(shared) or 'none'} — data ownership must be split first.",
             f"Operational overhead: {n} pipelines, {n} deployables, distributed tracing, service discovery and an API gateway."]
    cyc = tg.twin.get("cycles", [])
    if cyc:
        risks.append("Existing dependency cycles (" + "; ".join(" ↔ ".join(units[x]["name"] for x in c) for c in cyc[:3]) +
                     ") must be broken first or they become chatty service pairs.")
    verdict = "Not recommended yet" if (shared and len(shared) >= 2) or cyc else "Feasible with preparation" if n <= 6 else "High effort"
    return {"scenario": "split", "services": services, "cross_service": [{"from": a, "to": b, "dependencies": n_} for (a, b), n_ in cross.most_common()],
            "shared_tables": shared, "alignment": alignment,
            "estimates": {"services": n, "cross_service_dependencies": cross_calls, "added_latency_ms": latency, "monthly_cost_usd": cost,
                          "performance": perf, "deployment_complexity": complexity},
            "benefits": benefits, "risks": risks, "verdict": verdict,
            "recommended_first_steps": _first_steps(tg, cyc, shared, services),
            "assumptions": ["Louvain community detection on the static dependency graph (weights = number of references)",
                            "~4 ms per synchronous hop", "small containers at typical cloud list prices; managed DB per data-owning service"]}


def _first_steps(tg, cyc, shared, services):
    steps = []
    if cyc:
        steps.append("Break dependency cycles using domain events (see Refactoring Advisor).")
    if shared:
        steps.append(f"Give each table a single owner; expose others through APIs ({', '.join(list(shared)[:3])}).")
    best = max(services, key=lambda s: s["readiness"], default=None)
    if best:
        steps.append(f"Start with the most independent candidate: {best['name']} (readiness {best['readiness']}/100) using the Strangler Fig pattern.")
    steps.append("Introduce an API gateway and centralised logging/tracing before the second extraction.")
    return steps


def whatif(tg: TwinGraph, scenario: str, target: str | None = None, members: list[str] | None = None, resolution: float = 1.0) -> dict:
    if scenario == "remove":
        return whatif_remove(tg, target)
    if scenario == "replace":
        return whatif_replace(tg, target)
    if scenario == "extract":
        mem = set(members or []) or module_members(tg, target)
        return whatif_extract(tg, mem)
    if scenario == "split":
        return whatif_split(tg, resolution)
    raise ValueError(f"Unknown scenario {scenario}")


def parse_question(text: str) -> dict | None:
    """Very small intent parser used by the assistant for impact/what-if questions."""
    t = text.lower()
    m = re.search(r"(?:if i|if we|when i|what happens if i|what could be affected if i|what will break if i)\s+(modify|change|update|edit|touch|refactor|remove|delete|replace|split|extract)\s+(?:the\s+)?([\w./-]+)", t)
    if m:
        verb, obj = m.group(1), m.group(2)
        change = "remove" if verb in {"remove", "delete"} else "replace" if verb == "replace" else "extract" if verb in {"split", "extract"} else "modify"
        return {"change": change, "target": obj}
    m = re.search(r"(?:affected by|impact of|depends? on|dependents of|uses)\s+(?:the\s+)?([\w./-]+)", t)
    if m:
        return {"change": "modify", "target": m.group(1)}
    return None
