"""Rule-based refactoring advisor.

Each recommendation names the problem, the design principle it violates, a concrete target design
and the evidence (methods / lines) it was derived from. The LLM can later expand any item into a
narrative explanation or code sketch, but the recommendation itself is deterministic.
"""
from __future__ import annotations

import re
from pathlib import Path


def _camel(text: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "extracted"
    return words[0].lower() + "".join(w.capitalize() for w in words[1:])


def _section_comments(root: Path, file: str, start: int, end: int) -> list[tuple[int, str]]:
    try:
        lines = (root / file).read_text(encoding="utf-8", errors="replace").splitlines()[start - 1:end]
    except OSError:
        return []
    out = []
    for i, l in enumerate(lines, start=start):
        m = re.match(r"\s*//\s*([A-Za-z][\w \-/&]{3,40})\s*$", l)
        if m and not re.search(r"TODO|FIXME|wip", m.group(1), re.I):
            out.append((i, m.group(1).strip()))
    return out


def advise(root: Path, units: dict, edges: list[dict], cycles: list[list[str]], clones: list[dict], issues: list[dict]) -> list[dict]:
    recs: list[dict] = []
    by_name = {}
    for u in units.values():
        by_name.setdefault(u["name"], u)

    def add(**kw):
        kw["id"] = f"ref-{len(recs)}"
        recs.append(kw)

    # 1. God classes -> split by responsibility (collaborator domain analysis)
    for u in units.values():
        if not u.get("god_class"):
            continue
        m = u["metrics"]
        domains = m.get("domains", {})
        own = u["module"].split("::")[-1]
        proposed = [{"name": u["name"], "responsibility": f"Core {own} lifecycle", "methods": [x["name"] for x in u["methods"]
                     if not x.get("constructor") and not any(x["name"] in v for v in domains.values())][:8]}]
        notes = []
        for dom, meths in sorted(domains.items(), key=lambda kv: -len(kv[1])):
            svc = next((x for x in units.values() if x["module"].split("::")[-1] == dom and x["layer"] == "service" and not x["is_test"]), None)
            repo_direct = [x for x in units.values() if x["module"].split("::")[-1] == dom and x["layer"] == "repository"
                           and any(c["target"] == x["id"] for mm in u["methods"] for c in mm.get("resolvedCalls", []))]
            target = svc["name"] if svc else dom.capitalize() + "Service"
            resp = {"notification": "Notifications (send via domain events)", "payment": "Payment processing",
                    "inventory": "Inventory updates", "user": "Customer lookup", "product": "Catalogue & pricing",
                    "auth": "Authentication", "cart": "Cart management"}.get(dom, f"{dom.capitalize()} logic")
            proposed.append({"name": target, "responsibility": resp, "methods": sorted(meths), "existing": bool(svc)})
            if repo_direct:
                notes.append(f"{u['name']} reaches into {', '.join(r['name'] for r in repo_direct)} directly — that data belongs to "
                             f"the {dom} module and should only be changed through {target}.")
        add(type="split-class", title=f"Split {u['name']} by responsibility", unit=u["id"], file=u["file"], line=u["line"],
            priority="high", principle="Single Responsibility Principle",
            problem=f"{u['name']} coordinates {len(domains)} other domains ({', '.join(sorted(domains))}) with {m['methods']} methods, "
                    f"WMC {m['wmc']} and {m['fan_out']} direct dependencies. Any change in those domains forces a change here.",
            suggestion=f"Keep {u['name']} focused on its own lifecycle and delegate each foreign responsibility to the owning service. "
                       f"Side effects such as e-mails are best triggered by domain events (e.g. {u['name'].replace('Service', '')}Confirmed) "
                       f"so the core flow does not depend on them.",
            proposed=proposed, notes=notes, effort_hours=max(4, round(m["wmc"] / 6)),
            benefit=f"Fan-out drops from {m['fan_out']} to ~{max(2, m['fan_out'] - len(domains) + 1)}; each domain can evolve and be tested independently.")

    # 2. Complex / long methods -> extract method
    for u in units.values():
        if u["is_test"]:
            continue
        for mth in u["methods"]:
            # Long but branch-free code (route tables, FAQ/data literals) is not worth decomposing.
            if mth.get("constructor") or not (mth["complexity"] > 10 or (mth.get("loc", 0) > 50 and mth["complexity"] > 5)):
                continue
            sections = _section_comments(root, u["file"], mth["line"], mth["endLine"])
            steps = [{"name": _camel(t), "from_line": ln, "responsibility": t, "methods": []} for ln, t in sections]
            if not steps:
                # fall back: group sequential collaborator calls
                seen, groups = [], []
                for c in mth.get("resolvedCalls", []):
                    t = units.get(c["target"])
                    if t and t["id"] != u["id"] and t["name"] not in seen:
                        seen.append(t["name"])
                        groups.append({"name": _camel(f"{'persist' if t['layer'] == 'repository' else 'call'} {t['name'].replace('Service', '').replace('Repository', '')}"),
                                       "from_line": c["line"], "responsibility": f"Interaction with {t['name']}", "methods": []})
                steps = groups[:5]
            add(type="extract-method", title=f"Decompose {u['name']}.{mth['name']}()", unit=u["id"], file=u["file"], line=mth["line"],
                priority="high" if mth["complexity"] > 15 else "medium", principle="Extract Method / Single Level of Abstraction",
                problem=f"{mth['name']}() has cyclomatic complexity {mth['complexity']} over {mth.get('loc', 0)} lines "
                        f"(threshold 10). Each extra path is another case to test and another place for bugs.",
                suggestion="Extract each step into a well-named private method (or a small collaborator) so the main method reads as a "
                           "sequence of intentions. Replace conditional chains on status/codes with polymorphism or lookup tables.",
                proposed=steps, notes=[], effort_hours=max(1, round(mth["complexity"] / 5)),
                benefit=f"Target: no extracted method above CC 6; {mth['name']}() becomes a readable orchestration of {max(2, len(steps))} steps.")

    # 3. Dependency cycles -> invert the weakest edge
    for cyc in cycles[:10]:
        if not all(c in units for c in cyc):
            continue
        names = [units[c]["name"] for c in cyc]
        pairs = []
        for k in range(len(cyc)):
            x, y = units[cyc[k]], units[cyc[(k + 1) % len(cyc)]]
            calls = sorted({c["method"] for m in x["methods"] for c in m.get("resolvedCalls", []) if c["target"] == y["id"]})
            lazy = any("Lazy" in (m.get("annotations") or []) for m in x["methods"]) or "@Lazy" in str(x.get("fields"))
            pairs.append((len(calls), x, y, calls))
        pairs.sort(key=lambda p: p[0])
        _, x, y, calls = pairs[0]
        base = x["name"].replace("Service", "").replace("Controller", "")
        event = f"{base}CompletedEvent"
        add(type="break-cycle", title=f"Break the cycle {' ↔ '.join(names) if len(names) == 2 else ' → '.join(names + [names[0]])}",
            unit=x["id"], file=x["file"], line=x["line"], priority="high", principle="Acyclic Dependencies Principle / Dependency Inversion",
            problem=f"{' → '.join(names + [names[0]])} form a cycle, so none of them can be built, tested or extracted on its own. "
                    f"The weakest link is {x['name']} → {y['name']}" + (f" ({', '.join(c + '()' for c in calls)})." if calls else "."),
            suggestion=f"Remove {x['name']}'s dependency on {y['name']}: let {x['name']} publish an {event} and have {y['name']} react to it "
                       f"(Spring ApplicationEventPublisher / @EventListener), or return the result to {y['name']} and let it update its own state.",
            proposed=[{"name": event, "responsibility": f"Replaces direct calls {x['name']} → {y['name']}", "methods": calls}],
            notes=[], effort_hours=3, benefit="Restores a one-directional dependency, enabling independent testing and future service extraction.")

    # 4. Layer violations
    for i in issues:
        if i["rule"] == "layer-violation" and i["unit"] in units:
            u = units[i["unit"]]
            svc = u["name"].replace("Controller", "") + "Service"
            add(type="introduce-service", title=f"Introduce {svc} between {u['name']} and its repository", unit=u["id"], file=u["file"],
                line=u["line"], priority="medium", principle="Layered architecture / Separation of concerns",
                problem=i["detail"], suggestion=f"Create {svc} that owns the business rules (validation, rating recalculation, transactions); "
                                                f"the controller should only translate HTTP to service calls.",
                proposed=[{"name": svc, "responsibility": "Business logic + transactions", "methods": [m["name"] for m in u["methods"] if not m.get("constructor")]}],
                notes=[], effort_hours=2, benefit="Business rules become reusable and unit-testable without the web layer.")

    # 5. Duplication -> extract/reuse
    done = set()
    for c in clones[:20]:
        key = tuple(sorted([c["a"]["file"], c["b"]["file"]]))
        if key in done or c["lines"] < 8:
            continue
        done.add(key)
        fa, fb = Path(c["a"]["file"]).stem, Path(c["b"]["file"]).stem
        util = next((x for x in (fa, fb) if re.search(r"Util|Helper|Common|format", x, re.I)), None)
        uid = next((u["id"] for u in units.values() if u["file"] == c["a"]["file"]), None)
        title = f"Remove duplicated logic within {fa}" if c["a"]["file"] == c["b"]["file"] else f"Remove duplicated logic in {fa} and {fb}"
        add(type="remove-duplication", title=title, unit=uid, file=c["a"]["file"], line=c["a"]["start"],
            priority="medium" if c["lines"] >= 12 else "low", principle="DRY (Don't Repeat Yourself)",
            problem=f"{c['lines']} near-identical lines in {c['a']['file']}:{c['a']['start']} and {c['b']['file']}:{c['b']['start']}. "
                    f"A bug fixed in one copy will survive in the other.",
            suggestion=(f"Delete the copy and call {util} instead." if util else "Extract the shared logic into one function/utility and call it from both places."),
            proposed=[], notes=[c["snippet"]], effort_hours=1, benefit="Single source of truth for this behaviour.")

    # 6. Stateful singletons
    for i in issues:
        if i["rule"] == "stateful-singleton" and i["unit"] in units:
            u = units[i["unit"]]
            add(type="externalize-state", title=f"Move {u['name']} state out of memory", unit=u["id"], file=u["file"], line=i["line"],
                priority="medium", principle="Stateless services (12-factor)", problem=i["detail"],
                suggestion="Store the state in Redis (TTL-based) or a database table so any instance can serve any request.",
                proposed=[], notes=[], effort_hours=3, benefit="Enables horizontal scaling and zero-downtime deploys.")

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (order[r["priority"]], -(units.get(r.get("unit") or "", {}).get("risk", {}).get("score", 0))))
    for n, r in enumerate(recs):
        r["id"] = f"ref-{n}"
    return recs
