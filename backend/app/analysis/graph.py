"""Graph algorithms over the Digital Twin (NetworkX)."""
from __future__ import annotations

from collections import defaultdict

import networkx as nx
from networkx.algorithms import community as nx_comm

STRUCTURAL = {"inherits", "implements", "injects", "calls", "uses", "imports", "renders", "persists"}


def build_graph(units: dict, endpoints: dict, tables: dict, edges: list[dict]) -> nx.DiGraph:
    g = nx.DiGraph()
    for uid, u in units.items():
        g.add_node(uid, kind="unit", layer=u["layer"], module=u["module"], test=u["is_test"])
    for eid in endpoints:
        g.add_node(eid, kind="endpoint", layer="endpoint", module=None, test=False)
    for tid in tables:
        g.add_node(tid, kind="table", layer="table", module=None, test=False)
    for e in edges:
        if e["source"] in g and e["target"] in g:
            g.add_edge(e["source"], e["target"], types=e["types"], type=e["type"], weight=e["weight"])
    return g


def unit_graph(g: nx.DiGraph, include_tests: bool = False) -> nx.DiGraph:
    """Code-level dependency graph: units only, structural edges only."""
    nodes = [n for n, d in g.nodes(data=True) if d["kind"] == "unit" and (include_tests or not d["test"])]
    h = nx.DiGraph()
    h.add_nodes_from((n, g.nodes[n]) for n in nodes)
    for s, t, d in g.edges(data=True):
        if s in h and t in h and set(d["types"]) & STRUCTURAL:
            h.add_edge(s, t, **d)
    return h


def find_cycles(h: nx.DiGraph, limit: int = 40, max_len: int = 8) -> list[list[str]]:
    cycles = []
    for scc in nx.strongly_connected_components(h):
        if len(scc) < 2:
            continue
        sub = h.subgraph(scc)
        try:
            for c in nx.simple_cycles(sub, length_bound=max_len):
                cycles.append(c)
                if len(cycles) >= limit:
                    break
        except TypeError:  # older networkx without length_bound
            for c in nx.simple_cycles(sub):
                if len(c) <= max_len:
                    cycles.append(c)
                if len(cycles) >= limit:
                    break
        if len(cycles) >= limit:
            break
    # dedupe rotations
    seen, out = set(), []
    for c in cycles:
        key = frozenset(c), len(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    out.sort(key=len)
    return out


def centrality(h: nx.DiGraph) -> dict[str, dict]:
    if h.number_of_nodes() == 0:
        return {}
    try:
        pr = nx.pagerank(h, alpha=0.85, max_iter=200)  # edge s->t = s depends on t, so rank flows to depended-upon nodes
    except Exception:
        pr = {n: 0 for n in h}
    k = min(200, h.number_of_nodes())
    try:
        bt = nx.betweenness_centrality(h, k=k if k < h.number_of_nodes() else None, seed=7)
    except Exception:
        bt = {n: 0 for n in h}
    out = {}
    for n in h:
        anc = nx.ancestors(h, n)  # everything that (transitively) depends on n
        desc = nx.descendants(h, n)
        out[n] = {"pagerank": pr.get(n, 0), "betweenness": bt.get(n, 0), "dependents_transitive": len(anc),
                  "dependencies_transitive": len(desc)}
    return out


def module_metrics(units: dict, h: nx.DiGraph) -> dict[str, dict]:
    """Robert C. Martin package metrics: Ca, Ce, Instability, Abstractness, Distance."""
    mods: dict[str, dict] = defaultdict(lambda: {"units": [], "ca": set(), "ce": set(), "abstract": 0})
    for uid, u in units.items():
        if u["is_test"]:
            continue
        m = mods[u["module"]]
        m["units"].append(uid)
        if u.get("abstract"):
            m["abstract"] += 1
    for s, t in h.edges():
        ms, mt = units[s]["module"], units[t]["module"]
        if ms != mt:
            mods[ms]["ce"].add(mt)
            mods[mt]["ca"].add(ms)
    out = {}
    for mid, m in mods.items():
        ca, ce = len(m["ca"]), len(m["ce"])
        inst = ce / (ca + ce) if (ca + ce) else 0.0
        abst = m["abstract"] / len(m["units"]) if m["units"] else 0.0
        out[mid] = {"ca": ca, "ce": ce, "instability": round(inst, 2), "abstractness": round(abst, 2),
                    "distance": round(abs(abst + inst - 1), 2), "units": len(m["units"]),
                    "depends_on": sorted(m["ce"]), "used_by": sorted(m["ca"])}
    return out


def modularity_q(units: dict, h: nx.DiGraph) -> float:
    ug = h.to_undirected()
    ug.remove_nodes_from([n for n in list(ug) if ug.degree(n) == 0])
    if ug.number_of_edges() == 0:
        return 0.0
    parts = defaultdict(set)
    for n in ug:
        parts[units[n]["module"]].add(n)
    try:
        return round(nx_comm.modularity(ug, list(parts.values())), 3)
    except Exception:
        return 0.0


def louvain(h: nx.DiGraph, resolution: float = 1.0, seed: int = 7) -> list[set]:
    ug = h.to_undirected()
    if ug.number_of_nodes() == 0:
        return []
    try:
        return [set(c) for c in nx_comm.louvain_communities(ug, weight="weight", resolution=resolution, seed=seed)]
    except Exception:
        return [set(c) for c in nx_comm.greedy_modularity_communities(ug)]
