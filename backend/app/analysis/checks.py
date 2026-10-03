"""Static rule checks: security, performance/scalability and architecture/design smells.

Every issue is evidence-based (file + line) so scores can be traced back to code.
"""
from __future__ import annotations

import re
from pathlib import Path

SEV_WEIGHT = {"critical": 25, "high": 12, "medium": 5, "low": 2, "info": 0}

SECRET_NAME = re.compile(r"(secret|passw(or)?d|api[_-]?key|access[_-]?key|private[_-]?key|token|credential)", re.I)
SECRET_VALUE = [
    (re.compile(r"sk_live_[0-9A-Za-z]{10,}"), "Stripe live secret key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"), "Private key"),
    (re.compile(r"ghp_[0-9A-Za-z]{30,}"), "GitHub token"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
]
LINE_RULES = [
    # (regex, languages, category, severity, title, detail, principle)
    (re.compile(r"csrf\s*\(\s*\w+\s*->\s*\w+\.disable\(\)\)|\.csrf\(\)\s*\.disable\(\)"), {"Java"}, "security", "medium",
     "CSRF protection disabled", "CSRF is disabled globally. Acceptable only for purely stateless token APIs — verify no cookie-based auth is used.", "OWASP A01"),
    (re.compile(r"allowedOrigins\(\s*\"\*\"\s*\)|origin\s*:\s*['\"]\*['\"]|Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]\*"),
     {"Java", "JavaScript", "TypeScript"}, "security", "medium", "CORS allows any origin",
     "Wildcard CORS lets any website call this API from a browser.", "OWASP A05"),
    (re.compile(r"dangerouslySetInnerHTML"), {"JavaScript", "TypeScript"}, "security", "high", "Unsanitised HTML rendering (XSS)",
     "dangerouslySetInnerHTML renders raw HTML; if the content is user-controlled this enables stored XSS. Sanitise with DOMPurify.", "OWASP A03"),
    (re.compile(r"\.innerHTML\s*="), {"JavaScript", "TypeScript"}, "security", "medium", "Direct innerHTML assignment",
     "Assigning to innerHTML can introduce XSS.", "OWASP A03"),
    (re.compile(r"(?<![\w.])eval\s*\(|new Function\s*\("), {"JavaScript", "TypeScript"}, "security", "high", "Dynamic code execution",
     "eval / new Function executes arbitrary strings as code.", "OWASP A03"),
    (re.compile(r"getInstance\(\s*\"(MD5|SHA-?1)\"\s*\)|createHash\(\s*['\"](md5|sha1)['\"]\s*\)", re.I), {"Java", "JavaScript", "TypeScript"},
     "security", "medium", "Weak hash algorithm", "MD5/SHA-1 are broken for security purposes; use SHA-256+ or bcrypt/argon2 for passwords.", "OWASP A02"),
    (re.compile(r"localStorage\.setItem\(\s*['\"](token|jwt|access_?token|auth)", re.I), {"JavaScript", "TypeScript"}, "security", "low",
     "Auth token stored in localStorage", "Tokens in localStorage are readable by any injected script. Prefer httpOnly cookies.", "OWASP A07"),
    (re.compile(r"new\s+Random\s*\(\s*\)"), {"Java"}, "security", "low", "Non-cryptographic random",
     "java.util.Random is predictable; use SecureRandom for tokens or secrets.", "OWASP A02"),
    (re.compile(r"printStackTrace\s*\(\s*\)"), {"Java"}, "design", "low", "Stack trace printed",
     "printStackTrace leaks internals and bypasses logging; use a logger.", None),
    (re.compile(r"catch\s*\(\s*(Exception|Throwable)\s+\w+\s*\)\s*\{\s*(return\s+false;|\})"), {"Java"}, "design", "low", "Swallowed exception",
     "A broad exception is caught and ignored, hiding failures.", None),
]
# A SQL keyword alone is not SQL ("Select ${item.name}" is a UI label): require statement structure.
_SQL_STMT = r"(?:SELECT\b[^\"`]*?\bFROM|INSERT\s+INTO|UPDATE\s+[\w.\"`\[\]]+\s+SET|DELETE\s+FROM|WITH\s+\w+\s+AS)\b"
SQL_CONCAT = re.compile(r"\"\s*" + _SQL_STMT + r"[^\"]*\"\s*\+|\+\s*\"[^\"]*\b(WHERE|AND|OR|VALUES|SET)\b[^\"]*'\s*\"?\s*\+", re.I)
SQL_TEMPLATE = re.compile(r"`\s*" + _SQL_STMT + r"[^`]*\$\{", re.I)


def _issue(category, severity, title, detail, file, line, unit=None, principle=None, rule=None):
    return {"category": category, "severity": severity, "title": title, "detail": detail, "file": file, "line": line,
            "unit": unit, "principle": principle, "rule": rule or title.lower().replace(" ", "-")}


def unit_at(units_by_file: dict, file: str, line: int):
    best = None
    for u in units_by_file.get(file, []):
        if u["line"] <= line <= u["endLine"]:
            if best is None or u["line"] >= best["line"]:
                best = u
    return best["id"] if best else (units_by_file.get(file, [{}])[0].get("id") if units_by_file.get(file) else None)


def run_checks(root: Path, files: list[dict], configs: list[str], units: dict, edges: list[dict], cycles: list[list[str]],
               clones: list[dict], centrality: dict) -> list[dict]:
    issues: list[dict] = []
    units_by_file: dict[str, list] = {}
    for u in units.values():
        units_by_file.setdefault(u["file"], []).append(u)

    # ---- line-based rules over source
    for f in files:
        if not f.get("analyzed") or f.get("is_test"):
            continue
        try:
            text = Path(f["abs"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith(("//", "*", "/*")):
                continue
            for rx, langs, cat, sev, title, detail, principle in LINE_RULES:
                if f["language"] in langs and rx.search(line):
                    issues.append(_issue(cat, sev, title, detail, f["path"], i, unit_at(units_by_file, f["path"], i), principle))
            for rx, label in SECRET_VALUE:
                if rx.search(line):
                    issues.append(_issue("security", "critical", f"Hard-coded {label}",
                                         "A live credential is committed to source control. Rotate it and load it from a secret manager / env var.",
                                         f["path"], i, unit_at(units_by_file, f["path"], i), "OWASP A02", "hardcoded-secret"))
            m = re.search(r"(?:final\s+|const\s+|let\s+|var\s+|static\s+)[\w<>\[\], ]*?\b(\w+)\s*[:=]\s*[\"'`]([^\"'`]{8,})[\"'`]", line)
            if m and SECRET_NAME.search(m.group(1)) and not re.search(r"(?i)header|bearer |prefix|name|label|key_?name|placeholder|url|path|endpoint", m.group(1)) \
                    and not any(rx.search(line) for rx, _ in SECRET_VALUE):
                issues.append(_issue("security", "high", "Hard-coded secret",
                                     f"`{m.group(1)}` holds a literal credential. Move it to configuration / environment variables.",
                                     f["path"], i, unit_at(units_by_file, f["path"], i), "OWASP A02", "hardcoded-secret"))
            if (f["language"] == "Java" and SQL_CONCAT.search(line)) or (f["language"] != "Java" and SQL_TEMPLATE.search(line)):
                issues.append(_issue("security", "high", "SQL built by string concatenation",
                                     "User input concatenated into SQL enables SQL injection. Use bind parameters (?) / named parameters.",
                                     f["path"], i, unit_at(units_by_file, f["path"], i), "OWASP A03", "sql-injection"))

    # ---- config files (plain-text passwords)
    for c in configs:
        if not re.search(r"\.(properties|ya?ml)$|\.env", c):
            continue
        try:
            for i, line in enumerate((root / c).read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                m = re.match(r"\s*([\w.\-]*(password|secret|api[-_]?key)[\w.\-]*)\s*[:=]\s*(\S+)", line, re.I)
                if m and not m.group(3).startswith("${") and len(m.group(3)) >= 4:
                    issues.append(_issue("security", "medium", "Plain-text credential in config",
                                         f"`{m.group(1)}` is stored in {c}. Use environment variables or a vault.", c, i, None, "OWASP A05",
                                         "config-secret"))
        except OSError:
            pass

    # ---- unit-level performance / scalability / design rules
    id_by_name = {}
    for u in units.values():
        id_by_name.setdefault(u["name"], u["id"])
    for u in units.values():
        if u["is_test"]:
            continue
        for m in u["methods"]:
            for c in m.get("resolvedCalls", []):
                tgt = units.get(c["target"])
                if c.get("inLoop") and tgt and tgt["layer"] in {"repository", "api"}:
                    issues.append(_issue("performance", "medium", "Database / remote call inside a loop (N+1)",
                                         f"{u['name']}.{m['name']}() calls {tgt['name']}.{c['method']}() inside a loop. Batch the work "
                                         f"(e.g. findAllById / an IN query / one bulk request) to avoid N+1 round-trips.",
                                         u["file"], c["line"], u["id"], None, "n-plus-one"))
                if c["method"] == "findAll" and tgt and tgt["layer"] == "repository" and u["layer"] in {"service", "controller"}:
                    issues.append(_issue("performance", "low", "Unbounded query (findAll without paging)",
                                         f"{u['name']}.{m['name']}() loads every row of {tgt['name']}. Use pagination or an aggregate query.",
                                         u["file"], c["line"], u["id"], None, "unbounded-query"))
            if m.get("maxNesting", 0) >= 4:
                issues.append(_issue("design", "low", "Deeply nested logic", f"{u['name']}.{m['name']}() nests {m['maxNesting']} levels deep.",
                                     u["file"], m["line"], u["id"], "Readability", "deep-nesting"))
        # stateful singleton (horizontal scaling blocker)
        if u["language"] == "Java" and set(u["annotations"]) & {"Service", "Component", "RestController", "Controller"}:
            for fl in u["fields"]:
                if re.search(r"\b(Map|HashMap|List|ArrayList|Set|HashSet|ConcurrentHashMap)\b", fl["type"]) and fl.get("init") and \
                        "static" not in fl["modifiers"]:
                    issues.append(_issue("scalability", "medium", "Stateful singleton",
                                         f"{u['name']} keeps mutable state in `{fl['name']}` ({fl['type']}). State is lost on restart and not shared "
                                         f"between instances, which blocks horizontal scaling. Move it to Redis or the database.",
                                         u["file"], fl.get("line") or u["line"], u["id"], "Scalability", "stateful-singleton"))
        # layer violations
        if u["layer"] == "controller":
            for e in edges:
                if e["source"] == u["id"] and units.get(e["target"], {}).get("layer") == "repository":
                    issues.append(_issue("design", "medium", "Layer violation: controller → repository",
                                         f"{u['name']} talks to {units[e['target']]['name']} directly, bypassing the service layer. Business rules end up "
                                         f"in controllers and cannot be reused.", u["file"], u["line"], u["id"], "Layered architecture", "layer-violation"))
        if u["layer"] == "entity":
            for e in edges:
                if e["source"] == u["id"] and units.get(e["target"], {}).get("layer") in {"service", "controller"}:
                    issues.append(_issue("design", "medium", "Domain model depends on service layer",
                                         f"Entity {u['name']} depends on {units[e['target']]['name']}.", u["file"], u["line"], u["id"], "DIP",
                                         "layer-violation"))
        if u["language"] == "Java":
            ctor = [m for m in u["methods"] if m.get("constructor")]
            if ctor and len(ctor[0]["params"]) >= 6:
                issues.append(_issue("design", "medium", "Too many collaborators",
                                     f"{u['name']} receives {len(ctor[0]['params'])} dependencies through its constructor — a sign it has too many "
                                     f"responsibilities.", u["file"], ctor[0]["line"], u["id"], "SRP", "constructor-overinjection"))

    for cyc in cycles:
        names = [units[c]["name"] for c in cyc if c in units]
        first = units.get(cyc[0])
        if first:
            issues.append(_issue("design", "high" if len(cyc) == 2 else "medium", "Circular dependency",
                                 " → ".join(names + [names[0]]) + ". Cycles make components impossible to change, test or deploy independently.",
                                 first["file"], first["line"], first["id"], "Acyclic Dependencies Principle", "cycle"))
    for cl in clones[:60]:
        issues.append(_issue("design", "low" if cl["lines"] < 12 else "medium", "Duplicated code",
                             f"{cl['lines']} similar lines also appear in {cl['b']['file']}:{cl['b']['start']}.", cl["a"]["file"], cl["a"]["start"],
                             unit_at(units_by_file, cl["a"]["file"], cl["a"]["start"]), "DRY", "duplication"))
    # de-duplicate
    seen, out = set(), []
    for i in issues:
        k = (i["rule"], i["file"], i["line"], i["title"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    out.sort(key=lambda x: (sev_order[x["severity"]], x["category"], x["file"], x["line"]))
    for n, i in enumerate(out):
        i["id"] = f"iss-{n}"
    return out
