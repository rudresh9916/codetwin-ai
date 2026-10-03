"""Metric aggregation: unit/file metrics, defect-risk prediction, technical debt (SQALE) and architecture health.

All scores are derived from measurable properties of the code; the AI layer only explains them.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from .scanner import maintainability_index

TESTABLE_LAYERS = {"service", "controller", "repository", "component", "util", "api", "hook", "route", "store", "model"}
SEV_POINTS = {"critical": 25, "high": 12, "medium": 6, "low": 2, "info": 0}


def clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


def grade(score: float) -> str:
    return "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"


def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    xs = sorted(values.values())
    n = len(xs)
    out = {}
    for k, v in values.items():
        if xs[-1] == xs[0]:
            out[k] = 0.0 if v == 0 else 0.5
            continue
        below = sum(1 for x in xs if x < v)
        equal = sum(1 for x in xs if x == v)
        out[k] = (below + 0.5 * equal) / n if v > 0 else 0.0
    return out


# ------------------------------------------------------------------------------------------ units
def unit_metrics(units: dict, g, h, h_all, cent: dict, churn: dict, issues: list[dict]):
    tested = set()
    for s, t in h_all.edges():
        if units.get(s, {}).get("is_test"):
            tested.add(t)
    # Spring tests often reference the class under test by name only
    test_names = " ".join(u["name"] for u in units.values() if u["is_test"])
    issue_count = Counter(i["unit"] for i in issues if i.get("unit"))
    for uid, u in units.items():
        ms = [m for m in u["methods"] if not m.get("constructor")]
        ccs = [m["complexity"] for m in ms] or [0]
        public = [m for m in ms if m.get("public")]
        doc_items = [u.get("doc", False)] + [m.get("doc", False) for m in public]
        fan_out = h.out_degree(uid) if uid in h else 0
        fan_in = h.in_degree(uid) if uid in h else 0
        # dependents through the full twin (includes endpoints -> frontend consumers)
        dependents_all = [a for a in _ancestors(g, uid) if g.nodes[a]["kind"] == "unit" and not units[a]["is_test"]] if uid in g else []
        ch = churn.get(u["file"], {})
        foreign_domains = defaultdict(set)
        for m in ms:
            for c in m.get("resolvedCalls", []):
                t = units.get(c["target"])
                if t and t["module"] != u["module"] and not t["is_test"]:
                    foreign_domains[t["module"].split("::")[-1]].add(m["name"])
        logic = sum(m["complexity"] for m in ms if m.get("loc", 1) > 3 or m["complexity"] > 1)
        u["metrics"] = {
            "methods": len(ms), "wmc": sum(ccs), "logic": logic, "max_cc": max(ccs), "avg_cc": round(sum(ccs) / len(ccs), 2) if ms else 0,
            "loc": u["loc"], "fields": len(u["fields"]), "fan_in": fan_in, "fan_out": fan_out,
            "instability": round(fan_out / (fan_in + fan_out), 2) if (fan_in + fan_out) else 0,
            "dependents_transitive": len(dependents_all),
            "dependencies_transitive": cent.get(uid, {}).get("dependencies_transitive", 0),
            "pagerank": round(cent.get(uid, {}).get("pagerank", 0), 4), "betweenness": round(cent.get(uid, {}).get("betweenness", 0), 4),
            "doc_coverage": round(sum(1 for d in doc_items if d) / len(doc_items), 2),
            "tested": uid in tested or (u["name"] + "Test") in test_names or (u["name"] + ".test") in test_names,
            "churn": ch.get("commits", 0), "recent_churn": ch.get("recent_commits", 0), "fixes": ch.get("fixes", 0),
            "authors": len(ch.get("authors", [])), "issues": issue_count.get(uid, 0),
            "domains": {k: sorted(v) for k, v in foreign_domains.items()},
        }
        u["dependents_all"] = dependents_all[:200]


def _ancestors(g, n):
    import networkx as nx
    return nx.ancestors(g, n)


def predict_risk(units: dict, has_history: bool):
    """Defect-proneness risk: complexity × change frequency × centrality (hotspot model)."""
    core = {uid: u for uid, u in units.items() if not u["is_test"] and u["layer"] not in {"dto", "types", "exception"}}
    feats = {
        "wmc": {k: u["metrics"]["logic"] for k, u in core.items()},
        "churn": {k: u["metrics"]["recent_churn"] or u["metrics"]["churn"] for k, u in core.items()},
        "fixes": {k: u["metrics"]["fixes"] for k, u in core.items()},
        "dependents": {k: u["metrics"]["dependents_transitive"] for k, u in core.items()},
        "fan_out": {k: u["metrics"]["fan_out"] for k, u in core.items()},
        "loc": {k: u["metrics"]["loc"] for k, u in core.items()},
    }
    pr = {f: percentile_ranks(v) for f, v in feats.items()}
    weights = {"wmc": 0.27, "churn": 0.2, "fixes": 0.1, "dependents": 0.2, "fan_out": 0.1, "loc": 0.05}
    if not has_history:
        weights = {"wmc": 0.38, "dependents": 0.28, "fan_out": 0.17, "loc": 0.07}
    pr_dep = pr["dependents"]
    pr_rank = percentile_ranks({k: u["metrics"]["pagerank"] for k, u in core.items()})
    for uid, u in units.items():
        if uid in core:
            u["metrics"]["criticality"] = round(0.5 * pr_dep.get(uid, 0) + 0.3 * pr_rank.get(uid, 0) + 0.2 * pr["wmc"].get(uid, 0), 3)
        else:
            u["metrics"]["criticality"] = 0
        if uid not in core:
            u["risk"] = {"score": 0, "level": "low", "reasons": [], "factors": {}}
            continue
        m = u["metrics"]
        factors = {f: round(pr[f].get(uid, 0), 2) for f in weights}
        score = sum(weights[f] * factors[f] for f in weights)
        untested = (u["layer"] in TESTABLE_LAYERS and not m["tested"] and m["logic"] > 4)
        score += 0.08 if untested else 0
        score += min(0.1, 0.03 * m["issues"])
        score = round(min(1.0, score), 3)
        level = "high" if score >= 0.66 and m["logic"] >= 12 else "medium" if score >= 0.45 and m["logic"] >= 4 else "low"
        reasons = []
        if m["max_cc"] > 10 or (factors.get("wmc", 0) >= 0.75 and m["logic"] >= 8):
            reasons.append(f"High complexity (WMC {m['wmc']}, worst method CC {m['max_cc']})")
        if has_history and factors.get("churn", 0) >= 0.7 and m["churn"] >= 3:
            reasons.append(f"Changed frequently ({m['churn']} commits{', ' + str(m['fixes']) + ' bug-fixes' if m['fixes'] else ''})")
        if factors.get("dependents", 0) >= 0.7 and m["dependents_transitive"] >= 3:
            reasons.append(f"{m['dependents_transitive']} components depend on it")
        if m["fan_out"] >= 6:
            reasons.append(f"High coupling: depends on {m['fan_out']} components")
        if untested:
            reasons.append("No tests found")
        if m["issues"]:
            reasons.append(f"{m['issues']} open finding{'s' if m['issues'] > 1 else ''}")
        if m["loc"] >= 250:
            reasons.append(f"Large ({m['loc']} lines)")
        u["risk"] = {"score": score, "level": level, "reasons": reasons, "factors": factors}


# ------------------------------------------------------------------------------------------ files
def file_metrics(files: list[dict], units: dict, issues: list[dict], clones: list[dict], cycles: list[list[str]], churn: dict):
    by_file = defaultdict(list)
    for u in units.values():
        by_file[u["file"]].append(u)
    clone_lines = Counter()
    clone_count = Counter()
    for c in clones:
        for side in ("a", "b"):
            clone_lines[c[side]["file"]] += c["lines"]
            clone_count[c[side]["file"]] += 1
    in_cycle = {units[x]["file"] for cyc in cycles for x in cyc if x in units}
    issues_by_file = defaultdict(list)
    for i in issues:
        issues_by_file[i["file"]].append(i)
    for f in files:
        if not f.get("analyzed"):
            continue
        f["debt"] = {"minutes": 0, "by_category": {}, "ratio": 0, "rating": "A", "score": 0, "level": "low"}
        us = by_file.get(f["path"], [])
        methods = [m for u in us for m in u["methods"]]
        total_cc = sum(m["complexity"] for m in methods) or 1
        f["complexity"] = total_cc
        f["max_cc"] = max([m["complexity"] for m in methods] or [0])
        f["mi"] = maintainability_index(f.get("halstead", {}).get("volume", 0), total_cc, f["sloc"])
        f["units"] = [u["id"] for u in us]
        ch = churn.get(f["path"], {})
        f["churn"] = ch.get("commits", 0)
        f["fixes"] = ch.get("fixes", 0)
        f["authors"] = ch.get("authors", [])
        f["duplicate_lines"] = clone_lines.get(f["path"], 0)
        # ---- SQALE-style remediation cost (minutes)
        cost = Counter()
        reasons = []
        if not f["is_test"]:
            for u in us:
                for m in u["methods"]:
                    if m["complexity"] > 10:
                        cost["complexity"] += 20 + 4 * (m["complexity"] - 10)
                    if m.get("loc", 0) > 60:
                        cost["complexity"] += 20
                if u.get("god_class"):
                    cost["design"] += 240
                if u["layer"] in TESTABLE_LAYERS and not u["metrics"]["tested"] and u["metrics"]["wmc"] > 4:
                    cost["tests"] += 30 + 3 * min(u["metrics"]["wmc"], 40)
                pub = [m for m in u["methods"] if m.get("public") and not m.get("constructor")]
                undocumented = sum(1 for m in pub if not m.get("doc")) + (0 if u.get("doc") else 1)
                cost["documentation"] += min(60, 3 * undocumented)
            if f["sloc"] > 400:
                cost["size"] += 60 if f["sloc"] <= 800 else 120
            if f["path"] in in_cycle:
                cost["design"] += 60
            for c in clones:
                if c["a"]["file"] == f["path"] or c["b"]["file"] == f["path"]:
                    cost["duplication"] += 10 + 1.5 * c["lines"]
            for i in issues_by_file.get(f["path"], []):
                if i["rule"] in {"duplication", "cycle"}:
                    continue
                cat = "security" if i["category"] == "security" else "performance" if i["category"] in {"performance", "scalability"} else "design"
                cost[cat] += {"critical": 120, "high": 90, "medium": 45, "low": 15}.get(i["severity"], 10)
        minutes = round(sum(cost.values()))
        dev_cost = max(1, f["sloc"]) * 30
        ratio = minutes / dev_cost
        f["debt"].update({"minutes": minutes, "by_category": {k: round(v) for k, v in cost.items() if v}, "ratio": round(ratio, 3),
                          "rating": "A" if ratio <= 0.05 else "B" if ratio <= 0.1 else "C" if ratio <= 0.2 else "D" if ratio <= 0.5 else "E"})
        if f["max_cc"] > 10:
            reasons.append(f"Method with cyclomatic complexity {f['max_cc']}")
        if f["sloc"] > 300:
            reasons.append(f"Large file ({f['sloc']} source lines)")
        if any(u.get("god_class") for u in us):
            reasons.append("God class – too many responsibilities")
        if f["duplicate_lines"]:
            reasons.append(f"{f['duplicate_lines']} duplicated lines")
        if f["path"] in in_cycle:
            reasons.append("Part of a circular dependency")
        fan_out = max([u["metrics"]["fan_out"] for u in us] or [0])
        if fan_out >= 6:
            reasons.append(f"High coupling ({fan_out} dependencies)")
        sec = [i for i in issues_by_file.get(f["path"], []) if i["category"] == "security"]
        if sec:
            reasons.append(f"{len(sec)} security finding{'s' if len(sec) > 1 else ''}")
        if f["churn"] >= 6:
            reasons.append(f"Changed in {f['churn']} commits")
        if any(u["layer"] in TESTABLE_LAYERS and not u["metrics"]["tested"] and u["metrics"]["wmc"] > 4 for u in us):
            reasons.append("Untested logic")
        if not any(u.get("doc") for u in us) and us and not f["is_test"]:
            reasons.append("Limited documentation")
        f["debt_reasons"] = reasons
    # risk level per file (relative, from minutes + complexity + churn)
    analyzed = [f for f in files if f.get("analyzed") and not f["is_test"]]
    pr_debt = percentile_ranks({f["path"]: f["debt"]["minutes"] for f in analyzed})
    pr_cc = percentile_ranks({f["path"]: f["complexity"] for f in analyzed})
    pr_ch = percentile_ranks({f["path"]: f["churn"] for f in analyzed})
    for f in analyzed:
        s = 0.5 * pr_debt.get(f["path"], 0) + 0.3 * pr_cc.get(f["path"], 0) + 0.2 * pr_ch.get(f["path"], 0)
        f["debt"]["score"] = round(s, 3)
        f["debt"]["level"] = "high" if s >= 0.7 and f["debt"]["minutes"] >= 180 else "medium" if s >= 0.45 and f["debt"]["minutes"] >= 45 else "low"


def detect_god_classes(units: dict):
    for u in units.values():
        m = u["metrics"]
        domains = m.get("domains", {})
        big = m["wmc"] >= 35 or m["loc"] >= 300 or m["methods"] >= 20
        u["god_class"] = bool(not u["is_test"] and u["layer"] in {"service", "controller", "component", "model", "api", "page"}
                              and ((big and len(domains) >= 3) or m["fan_out"] >= 8))


# ------------------------------------------------------------------------------------------ health
def health(units, files, issues, cycles, mod_metrics, q, readme: bool) -> dict:
    core = [u for u in units.values() if not u["is_test"]]
    code_units = [u for u in core if u["layer"] not in {"dto", "types", "exception", "entity", "enum"}]
    methods = [m for u in core for m in u["methods"] if not m.get("constructor")]
    out = {}

    # Modularity
    cyc_units = {x for c in cycles for x in c}
    dists = [m["distance"] for m in mod_metrics.values() if m["units"] >= 2]
    avg_d = sum(dists) / len(dists) if dists else 0
    s = clamp(50 + 110 * q) - min(30, 10 * len(cycles)) - 20 * max(0, avg_d - 0.6)
    out["modularity"] = _dim(s, f"Newman modularity Q = {q:.2f} across {len(mod_metrics)} modules; {len(cycles)} dependency cycle(s) "
                               f"involving {len(cyc_units)} components.",
                             {"modularity_q": q, "cycles": len(cycles), "units_in_cycles": len(cyc_units), "modules": len(mod_metrics),
                              "avg_main_sequence_distance": round(avg_d, 2)})
    # Coupling
    fo = [u["metrics"]["fan_out"] for u in code_units] or [0]
    avg_fo = sum(fo) / len(fo)
    high_fo = [u for u in code_units if u["metrics"]["fan_out"] >= 7]
    # Widely reused helpers, hooks, contexts and data types are meant to have high fan-in (stable dependencies).
    max_fi = max([u["metrics"]["fan_in"] for u in code_units
                  if u["layer"] not in {"util", "hook", "context", "entity", "dto", "interface", "config"}] or [0])
    s = 100 - 9 * max(0, avg_fo - 2.5) - 150 * (len(high_fo) / max(1, len(code_units))) - 2 * max(0, max_fi - 10)
    out["coupling"] = _dim(s, f"Average fan-out {avg_fo:.1f}; {len(high_fo)} component(s) depend on 7+ others; max fan-in {max_fi}.",
                           {"avg_fan_out": round(avg_fo, 2), "high_fan_out": [u["name"] for u in high_fo], "max_fan_in": max_fi})
    # Complexity
    nontrivial = [m for m in methods if m["complexity"] >= 1]
    over10 = [m for m in nontrivial if m["complexity"] > 10]
    over20 = [m for m in nontrivial if m["complexity"] > 20]
    avg_cc = sum(m["complexity"] for m in nontrivial) / len(nontrivial) if nontrivial else 0
    worst = max(nontrivial, key=lambda m: m["complexity"], default=None)
    s = 100 - 300 * (len(over10) / max(1, len(nontrivial))) - 400 * (len(over20) / max(1, len(nontrivial))) - 8 * max(0, avg_cc - 2.5)
    out["complexity"] = _dim(s, f"Average cyclomatic complexity {avg_cc:.1f}; {len(over10)} of {len(nontrivial)} methods exceed 10.",
                             {"avg_cc": round(avg_cc, 2), "methods_over_10": len(over10), "methods_over_20": len(over20),
                              "worst": worst["complexity"] if worst else 0})
    # Maintainability
    af = [f for f in files if f.get("analyzed") and not f["is_test"] and f["sloc"] > 0]
    tot = sum(f["sloc"] for f in af) or 1
    mi = sum(f["mi"] * f["sloc"] for f in af) / tot if af else 100
    gods = [u for u in core if u.get("god_class")]
    dup = sum(f.get("duplicate_lines", 0) for f in af) / 2
    dup_ratio = dup / tot
    s = clamp((mi - 10) * 2.1) - min(30, 12 * len(gods)) - min(20, 200 * dup_ratio)
    out["maintainability"] = _dim(s, f"LOC-weighted Maintainability Index {mi:.0f}/100; {len(gods)} god class(es); "
                                     f"{dup_ratio * 100:.1f}% duplicated code.",
                                  {"maintainability_index": round(mi, 1), "god_classes": [u["name"] for u in gods],
                                   "duplication_ratio": round(dup_ratio, 3)})
    # Documentation
    items = []
    for u in core:
        if u["layer"] in {"dto", "types"}:
            continue
        items.append(bool(u.get("doc")))
        items += [bool(m.get("doc")) for m in u["methods"] if m.get("public") and not m.get("constructor") and m["loc"] > 3]
    cov = sum(items) / len(items) if items else 0
    s = 85 * min(1, cov / 0.6) + (15 if readme else 0)
    out["documentation"] = _dim(s, f"{cov * 100:.0f}% of public types/methods carry doc comments; README {'present' if readme else 'missing'}.",
                                {"doc_coverage": round(cov, 2), "readme": readme})
    # Testability
    testable = [u for u in core if u["layer"] in TESTABLE_LAYERS and u["metrics"]["wmc"] > 2]
    tested = [u for u in testable if u["metrics"]["tested"]]
    test_loc = sum(f["sloc"] for f in files if f.get("analyzed") and f["is_test"])
    ratio = test_loc / tot
    s = 65 * (len(tested) / max(1, len(testable))) + 25 * min(1, ratio / 0.5) + 10
    out["testability"] = _dim(s, f"{len(tested)}/{len(testable)} testable components have tests; test-to-code ratio {ratio:.2f}.",
                              {"tested": len(tested), "testable": len(testable), "test_code_ratio": round(ratio, 2),
                               "untested": [u["name"] for u in testable if not u["metrics"]["tested"]][:15]})
    # Security
    sec = [i for i in issues if i["category"] == "security"]
    s = 100 - sum(SEV_POINTS[i["severity"]] for i in sec)
    out["security"] = _dim(s, f"{len(sec)} security finding(s): " + ", ".join(f"{n} {k}" for k, n in Counter(i['severity'] for i in sec).most_common()) if sec
                           else "No security findings from static rules.", {"findings": len(sec), "by_severity": dict(Counter(i["severity"] for i in sec))})
    # Performance & scalability
    perf = [i for i in issues if i["category"] in {"performance", "scalability"}]
    pts = {"n-plus-one": 8, "unbounded-query": 4, "stateful-singleton": 10}
    s = 100 - sum(pts.get(i["rule"], 3) for i in perf)
    out["performance"] = _dim(s, f"{len(perf)} performance/scalability finding(s) (N+1 queries, unbounded queries, stateful singletons).",
                              {"findings": len(perf), "by_rule": dict(Counter(i["rule"] for i in perf))})
    weights = {"modularity": .14, "coupling": .14, "complexity": .15, "maintainability": .15, "documentation": .08, "testability": .12,
               "security": .12, "performance": .10}
    overall = round(sum(out[k]["score"] * w for k, w in weights.items()))
    return {"overall": overall, "grade": grade(overall), "dimensions": out, "weights": weights}


def _dim(score, summary, metrics):
    s = round(clamp(score))
    return {"score": s, "grade": grade(s), "summary": summary, "metrics": metrics}


def debt_summary(files: list[dict]) -> dict:
    af = [f for f in files if f.get("analyzed") and not f["is_test"]]
    minutes = sum(f["debt"]["minutes"] for f in af)
    sloc = sum(f["sloc"] for f in af) or 1
    ratio = minutes / (sloc * 30)
    by_cat = Counter()
    for f in af:
        for k, v in f["debt"]["by_category"].items():
            by_cat[k] += v
    rating = "A" if ratio <= 0.05 else "B" if ratio <= 0.1 else "C" if ratio <= 0.2 else "D" if ratio <= 0.5 else "E"
    level = {"A": "Low", "B": "Low", "C": "Medium", "D": "High", "E": "Very high"}[rating]
    return {"minutes": round(minutes), "hours": round(minutes / 60, 1), "days": round(minutes / 480, 1), "ratio": round(ratio, 3),
            "rating": rating, "level": level, "by_category": {k: round(v) for k, v in by_cat.most_common()},
            "files": sorted([{"path": f["path"], "minutes": f["debt"]["minutes"], "level": f["debt"]["level"], "score": f["debt"]["score"],
                              "rating": f["debt"]["rating"], "reasons": f["debt_reasons"], "sloc": f["sloc"], "complexity": f["complexity"],
                              "churn": f["churn"]} for f in af], key=lambda x: -x["score"])}
