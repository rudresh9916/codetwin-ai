"""Turns raw parser output into the Digital Twin's semantic model.

Produces *units* (classes / components / modules), *endpoints* (REST routes), *tables*
(persistent data stores) and typed, directed *edges* (source depends on target).
"""
from __future__ import annotations

import posixpath
import re
from collections import defaultdict
from pathlib import Path

from .scanner import app_for

HTTP_ANN = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT", "DeleteMapping": "DELETE", "PatchMapping": "PATCH"}
JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def norm_path(p: str) -> str:
    p = p.split("?")[0].split("#")[0]
    p = re.sub(r"\{[^}]*\}|:[A-Za-z_]\w*|\*\*?", "{param}", p)
    p = "/" + "/".join(s for s in p.split("/") if s)
    return p


def join_url(*parts: str) -> str:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + joined


class EdgeSet:
    def __init__(self):
        self.edges: dict[tuple[str, str], dict] = {}

    def add(self, s: str, t: str, etype: str, detail: str | None = None, weight: float = 1.0):
        if not s or not t or s == t:
            return
        e = self.edges.get((s, t))
        if not e:
            e = self.edges[(s, t)] = {"source": s, "target": t, "types": [], "details": [], "weight": 0.0}
        if etype not in e["types"]:
            e["types"].append(etype)
        if detail and detail not in e["details"] and len(e["details"]) < 25:
            e["details"].append(detail)
        e["weight"] += weight

    def as_list(self) -> list[dict]:
        out = []
        for e in self.edges.values():
            e = dict(e)
            e["type"] = _primary_type(e["types"])
            e["weight"] = round(e["weight"], 2)
            out.append(e)
        return out


_TYPE_PRIORITY = ["inherits", "implements", "injects", "calls", "http", "handles", "persists", "maps", "renders", "imports", "uses"]


def _primary_type(types: list[str]) -> str:
    for t in _TYPE_PRIORITY:
        if t in types:
            return t
    return types[0]


# ===================================================================================== Java
def classify_java(t: dict, rel: str, is_test: bool) -> str:
    anns = {a["name"] for a in t.get("annotations", [])}
    n = t["simpleName"]
    ext = " ".join(t.get("extends", []))
    if is_test:
        return "test"
    if anns & {"RestController", "Controller", "ControllerAdvice", "RestControllerAdvice"} or n.endswith(("Controller", "Resource")):
        return "controller"
    if anns & {"Repository"} or re.search(r"(Jpa|Crud|PagingAndSorting|Mongo|Reactive\w*)Repository", ext) or n.endswith(("Repository", "Dao", "DAO")):
        return "repository"
    if anns & {"Entity", "Document", "Table", "MappedSuperclass", "Embeddable"}:
        return "entity"
    if anns & {"Service"} or n.endswith(("Service", "ServiceImpl", "Manager", "UseCase", "Facade")):
        return "service"
    if anns & {"Configuration", "SpringBootApplication", "EnableWebSecurity", "EnableAutoConfiguration"} or n.endswith(("Config", "Configuration", "Application")):
        return "config"
    if n.endswith(("Exception", "Error")) or "Exception" in ext:
        return "exception"
    if re.search(r"(Dto|DTO|Request|Response|Payload|Command|Event|Form|Vo|VO)$", n) or (t["kind"] == "record" and not anns):
        return "dto"
    if re.search(r"(Filter|Interceptor|Provider|Handler|Advice|Aspect)$", n) or anns & {"Component"}:
        return "component"
    if re.search(r"(Utils?|Helper|Helpers|Constants|Mapper|Converter)$", n):
        return "util"
    if t["kind"] == "interface":
        return "interface"
    if t["kind"] == "enum":
        return "enum"
    return "model"


def build_java(parsed: list[dict], files_by_abs: dict, apps: list[dict], units: dict, edges: EdgeSet, endpoints: dict, tables: dict):
    # Common root package per app (for module naming)
    pkgs_by_app = defaultdict(list)
    for cu in parsed:
        f = files_by_abs.get(cu["path"])
        if not f or f["is_test"]:
            continue
        a = app_for(f["path"], apps)
        pkgs_by_app[a["dir"] if a else ""].append(cu.get("package") or "")
    roots = {}
    for app_dir, pkgs in pkgs_by_app.items():
        parts = [p.split(".") for p in pkgs if p]
        prefix = []
        if parts:
            for seg in zip(*parts):
                if len(set(seg)) == 1:
                    prefix.append(seg[0])
                else:
                    break
        # If every class lives in the same package, keep its last segment as the module name
        if parts and len({".".join(p) for p in parts}) == 1:
            prefix = prefix[:-1]
        roots[app_dir] = ".".join(prefix)

    fqn_index: dict[str, str] = {}
    simple_index: dict[str, list[str]] = defaultdict(list)
    pkg_index: dict[str, list[str]] = defaultdict(list)
    raw: dict[str, dict] = {}

    for cu in parsed:
        f = files_by_abs.get(cu["path"])
        if not f:
            continue
        rel = f["path"]
        pkg = cu.get("package") or ""
        a = app_for(rel, apps)
        app_dir = a["dir"] if a else ""
        root = roots.get(app_dir, "")
        sub = pkg[len(root):].lstrip(".") if root and pkg.startswith(root) else pkg
        module_name = sub or (pkg.split(".")[-1] if pkg else (a["name"] if a else "root"))
        module_id = f"{app_dir or '.'}::{module_name}"
        top_types = [t for t in cu.get("types", []) if not t.get("outer")]
        nested = [t for t in cu.get("types", []) if t.get("outer")]
        for t in top_types:
            fqn = f"{pkg}.{t['name']}" if pkg else t["name"]
            uid = "java:" + fqn
            layer = classify_java(t, rel, f["is_test"])
            methods = []
            for m in t.get("methods", []):
                methods.append({
                    "name": m["name"], "line": m["line"], "endLine": m["endLine"], "loc": max(1, m["endLine"] - m["line"] + 1),
                    "complexity": m["complexity"], "maxNesting": m.get("maxNesting", 0), "statements": m.get("statements", 0),
                    "params": [p["type"] + " " + p["name"] for p in m.get("params", [])], "returnType": m.get("returnType"),
                    "annotations": [x["name"] for x in m.get("annotations", [])], "doc": m.get("doc", False),
                    "constructor": m.get("constructor", False), "abstract": m.get("abstract", False),
                    "public": "public" in m.get("modifiers", []), "calls": m.get("calls", []),
                    "instantiations": m.get("instantiations", []), "strings": m.get("strings", []), "_ann": m.get("annotations", []),
                    "_params": m.get("params", []),
                })
            type_refs = set(t.get("typeRefs", []))
            fields = [{"name": fl["name"], "type": fl["type"], "annotations": [x["name"] for x in fl.get("annotations", [])],
                       "modifiers": fl.get("modifiers", []), "init": fl.get("init"), "line": fl.get("line")} for fl in t.get("fields", [])]
            # merge nested types into their top-level owner (OrderRequest.Line -> OrderRequest)
            for nt in nested:
                if nt["name"].split(".")[0] == t["name"]:
                    type_refs |= set(nt.get("typeRefs", []))
                    for m in nt.get("methods", []):
                        methods.append({"name": nt["simpleName"] + "." + m["name"], "line": m["line"], "endLine": m["endLine"],
                                        "loc": max(1, m["endLine"] - m["line"] + 1), "complexity": m["complexity"],
                                        "maxNesting": m.get("maxNesting", 0), "statements": m.get("statements", 0),
                                        "params": [p["type"] + " " + p["name"] for p in m.get("params", [])],
                                        "returnType": m.get("returnType"), "annotations": [], "doc": m.get("doc", False),
                                        "constructor": m.get("constructor", False), "abstract": m.get("abstract", False),
                                        "public": "public" in m.get("modifiers", []), "calls": m.get("calls", []),
                                        "instantiations": m.get("instantiations", []), "strings": [], "_ann": [], "_params": []})
            unit = {
                "id": uid, "name": t["name"], "fqn": fqn, "kind": t["kind"], "layer": layer, "language": "Java",
                "file": rel, "line": t["line"], "endLine": t["endLine"], "loc": max(1, t["endLine"] - t["line"] + 1),
                "module": module_id, "app": app_dir, "package": pkg,
                "annotations": [x["name"] for x in t.get("annotations", [])],
                "annotationArgs": {x["name"]: x.get("args", {}) for x in t.get("annotations", [])},
                "doc": t.get("doc", False), "extends": t.get("extends", []), "implements": t.get("implements", []),
                "fields": fields, "methods": methods, "is_test": f["is_test"],
                "abstract": t["kind"] == "interface" or "abstract" in t.get("modifiers", []),
                "public": "public" in t.get("modifiers", []),
            }
            units[uid] = unit
            raw[uid] = {"imports": cu.get("imports", []), "typeRefs": type_refs, "package": pkg}
            fqn_index[fqn] = uid
            simple_index[t["name"]].append(uid)
            pkg_index[pkg].append(uid)

    def resolve(name: str, uid: str) -> str | None:
        """Resolve a simple/qualified type name as seen from unit uid."""
        if not name:
            return None
        name = re.sub(r"<.*>", "", name).replace("[]", "").replace("...", "").strip()
        if "." in name:
            if name in fqn_index:
                return fqn_index[name]
            name = name.split(".")[0] if name.split(".")[0][:1].isupper() else name.split(".")[-1]
        r = raw[uid]
        for imp in r["imports"]:
            if imp["static"]:
                continue
            iname = imp["name"]
            if not imp["wildcard"] and iname.split(".")[-1] == name:
                return fqn_index.get(iname)
        cand = fqn_index.get(f"{r['package']}.{name}" if r["package"] else name)
        if cand:
            return cand
        for imp in r["imports"]:
            if imp["wildcard"] and not imp["static"]:
                c = fqn_index.get(imp["name"][:-2] + "." + name)
                if c:
                    return c
        return None

    for uid, u in units.items():
        if u["language"] != "Java":
            continue
        r = raw[uid]
        for e in u["extends"]:
            tgt = resolve(e, uid)
            if tgt:
                edges.add(uid, tgt, "inherits", f"extends {units[tgt]['name']}")
        for i in u["implements"]:
            tgt = resolve(i, uid)
            if tgt:
                edges.add(uid, tgt, "implements", f"implements {units[tgt]['name']}")
        field_types: dict[str, str] = {}
        for fl in u["fields"]:
            tgt = None
            for tname in re.findall(r"[A-Z][A-Za-z0-9_]*", fl["type"]):
                t2 = resolve(tname, uid)
                if t2:
                    tgt = t2
                    field_types.setdefault(fl["name"], t2)
                    break
            if tgt:
                inj = "final" in fl["modifiers"] or bool(set(fl["annotations"]) & {"Autowired", "Inject", "Resource"})
                lay = units[tgt]["layer"]
                etype = "injects" if inj and lay in {"service", "repository", "component", "interface", "config", "controller", "util"} else "uses"
                edges.add(uid, tgt, etype, f"field {fl['name']}")
        # constructor params count as injection
        for m in u["methods"]:
            if m["constructor"]:
                for p in m["_params"]:
                    for tname in re.findall(r"[A-Z][A-Za-z0-9_]*", p["type"]):
                        t2 = resolve(tname, uid)
                        if t2:
                            field_types.setdefault(p["name"], t2)
                            edges.add(uid, t2, "injects", f"constructor param {p['name']}")
                            break
        # method invocations
        for m in u["methods"]:
            resolved_calls = []
            for c in m["calls"]:
                root = c.get("root") or ""
                recv = c.get("receiver") or ""
                tgt = None
                if root in field_types:
                    # only attribute the call to the collaborator when it is invoked directly on the field
                    # (repo.findById(id).orElseThrow() -> findById belongs to repo, orElseThrow does not)
                    if recv in (root, f"this.{root}"):
                        tgt = field_types[root]
                elif root and root[:1].isupper() and not root.startswith("new ") and recv == root:
                    tgt = resolve(root, uid)
                elif root.startswith("new "):
                    tgt = resolve(root[4:], uid)
                elif root == "this" and not c.get("receiver"):
                    tgt = uid
                if tgt:
                    resolved_calls.append({"target": tgt, "method": c["name"], "line": c["line"], "inLoop": c.get("inLoop", False)})
                    if tgt != uid:
                        edges.add(uid, tgt, "calls", f"{m['name']} → {units[tgt]['name']}.{c['name']}()")
            m["resolvedCalls"] = resolved_calls
            for nt in m["instantiations"]:
                tgt = resolve(nt, uid)
                if tgt:
                    edges.add(uid, tgt, "uses", f"new {nt}() in {m['name']}")
        # any other referenced type (generics, locals, casts, static refs)
        for tname in r["typeRefs"]:
            tgt = resolve(tname, uid)
            if tgt and (uid, tgt) not in edges.edges:
                edges.add(uid, tgt, "uses", f"references {tname}")

    # ---------------- endpoints (Spring MVC / JAX-RS)
    for uid, u in units.items():
        if u["language"] != "Java" or u["layer"] != "controller":
            continue
        base = ""
        args = u["annotationArgs"]
        for key in ("RequestMapping", "Path"):
            if key in args:
                base = args[key].get("value") or args[key].get("path") or ""
        for m in u["methods"]:
            for a in m["_ann"]:
                method, sub = None, None
                if a["name"] in HTTP_ANN:
                    method = HTTP_ANN[a["name"]]
                    sub = a["args"].get("value") or a["args"].get("path") or ""
                elif a["name"] == "RequestMapping":
                    mm = a["args"].get("method", "")
                    method = (re.findall(r"(GET|POST|PUT|DELETE|PATCH)", mm) or ["ANY"])[0]
                    sub = a["args"].get("value") or a["args"].get("path") or ""
                elif a["name"] in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    method = a["name"]
                    sub = next((x["args"].get("value", "") for x in m["_ann"] if x["name"] == "Path"), "")
                if not method:
                    continue
                for s in (sub or "").split(",") or [""]:
                    path = join_url(base, s.strip())
                    eid = f"ep:{method} {path}"
                    params = []
                    for p in m["_params"]:
                        pa = [x["name"] for x in p.get("annotations", [])]
                        kind = "path" if "PathVariable" in pa else "query" if "RequestParam" in pa else "body" if "RequestBody" in pa else None
                        if kind:
                            params.append({"name": p["name"], "type": p["type"], "in": kind})
                    endpoints[eid] = {"id": eid, "method": method, "path": path, "norm": norm_path(path), "unit": uid,
                                      "handler": m["name"], "file": u["file"], "line": m["line"], "framework": "Spring",
                                      "params": params, "returns": m.get("returnType"), "consumers": [], "tests": []}
                    edges.add(eid, uid, "handles", f"{u['name']}.{m['name']}()")

    # ---------------- persistence: entities -> tables, repositories -> entities
    for uid, u in units.items():
        if u["language"] != "Java":
            continue
        if u["layer"] == "entity":
            tname = (u["annotationArgs"].get("Table", {}) or {}).get("name") or (u["annotationArgs"].get("Document", {}) or {}).get("collection") \
                or (u["annotationArgs"].get("Document", {}) or {}).get("value") or camel_to_snake(u["name"])
            tid = "db:" + tname
            tables.setdefault(tid, {"id": tid, "name": tname, "entity": uid, "columns": [], "relations": [], "source": "JPA"})
            cols = []
            for fl in u["fields"]:
                if "static" in fl["modifiers"]:
                    continue
                rel = next((a for a in fl["annotations"] if a in {"ManyToOne", "OneToMany", "OneToOne", "ManyToMany"}), None)
                cols.append({"name": fl["name"], "type": fl["type"], "id": "Id" in fl["annotations"], "relation": rel})
            tables[tid]["columns"] = cols
            edges.add(uid, tid, "maps", f"@Entity → {tname}")
    for uid, u in units.items():
        if u["language"] == "Java" and u["layer"] == "repository":
            for e in u["extends"]:
                m = re.search(r"<\s*([A-Z]\w*)", e)
                if m:
                    ent = resolve(m.group(1), uid)
                    if ent and units[ent]["layer"] == "entity":
                        edges.add(uid, ent, "persists", f"{u['name']} manages {units[ent]['name']}")
            u["queries"] = [m["name"] for m in u["methods"]]
    # entity relations (ManyToOne etc.) between tables
    for tid, t in tables.items():
        ent = units.get(t["entity"])
        if not ent:
            continue
        for fl in ent["fields"]:
            if any(a in fl["annotations"] for a in ("ManyToOne", "OneToMany", "OneToOne", "ManyToMany")):
                for tname in re.findall(r"[A-Z][A-Za-z0-9_]*", fl["type"]):
                    other = resolve(tname, ent["id"])
                    if other and units[other]["layer"] == "entity":
                        ann = next(a for a in fl["annotations"] if a in ("ManyToOne", "OneToMany", "OneToOne", "ManyToMany"))
                        t["relations"].append({"field": fl["name"], "kind": ann, "target": other})


# ===================================================================================== JS / TS
def classify_js(f: dict, rec: dict) -> tuple[str, str]:
    """Return (kind, layer) for a JS/TS file-level unit."""
    p = f["path"].lower()
    name = Path(f["path"]).stem
    members = rec.get("members", [])
    kinds = {m["kind"] for m in members}
    main = next((m for m in members if m["name"] == rec.get("defaultExport")), None) or \
        next((m for m in members if m.get("exported") and m["kind"] in {"component", "hook", "class", "function"}), None)
    main_kind = main["kind"] if main else None
    if f["is_test"]:
        return "test", "test"
    if rec.get("routes"):
        return "module", "route"
    if rec.get("dbModels"):
        return "module", "model"
    if re.search(r"(^|/)(pages|views|screens|routes)/", p) or re.search(r"(^|/)app/(.+/)?page\.[jt]sx?$", p):
        if "component" in kinds or main_kind == "component":
            return "component", "page"
    if re.search(r"(^|/)(store|stores|slices|redux|state)/", p) or re.search(r"(slice|store)\.[jt]sx?$", p):
        return "module", "store"
    if re.search(r"(^|/)contexts?/", p) or re.search(r"context\.[jt]sx?$", p):
        return "module", "context"
    if rec.get("httpClients") or rec.get("apiCalls") or re.search(r"(^|/)(api|services?|clients?|http)/", p):
        return "module", "api"
    if main_kind == "hook" or re.search(r"(^|/)hooks/", p):
        return "hook", "hook"
    if re.search(r"(^|/)(utils?|lib|helpers?|common|shared)/", p):
        return "module", "util"
    if name.lower() in {"main", "index", "app", "_app", "server", "root"}:
        return ("component" if "component" in kinds else "module"), "entry"
    if "component" in kinds or main_kind == "component":
        return "component", "component"
    if re.search(r"(config|constants?|env|settings)\.[jt]sx?$", p):
        return "module", "config"
    if main_kind == "class":
        return "class", "service" if name.lower().endswith("service") else "model"
    if kinds <= {"type", "enum"} and kinds:
        return "module", "types"
    return "module", "module"


def _load_tsconfig_paths(root: Path, app_dir: str) -> list[tuple[str, str]]:
    import json
    out = []
    for nm in ("tsconfig.json", "jsconfig.json", "tsconfig.app.json"):
        p = root / app_dir / nm if app_dir else root / nm
        if not p.exists():
            continue
        try:
            txt = re.sub(r"//.*?$|/\*.*?\*/", "", p.read_text(encoding="utf-8", errors="replace"), flags=re.M | re.S)
            txt = re.sub(r",\s*([}\]])", r"\1", txt)
            cfg = json.loads(txt)
        except Exception:
            continue
        co = cfg.get("compilerOptions", {}) or {}
        base = co.get("baseUrl", ".")
        for alias, targets in (co.get("paths") or {}).items():
            if targets:
                out.append((alias.rstrip("*"), posixpath.normpath(posixpath.join(app_dir or ".", base, targets[0].rstrip("*"))) + "/"))
    if not out:  # conventional "@/..." -> src/
        out.append(("@/", posixpath.join(app_dir, "src/") if app_dir else "src/"))
        out.append(("~/", posixpath.join(app_dir, "src/") if app_dir else "src/"))
    return out


def build_js(parsed: list[dict], files_by_abs: dict, apps: list[dict], root: Path, units: dict, edges: EdgeSet,
             endpoints: dict, tables: dict, libraries: dict):
    by_rel: dict[str, dict] = {}
    files_by_rel = {x["path"]: x for x in files_by_abs.values()}
    rel_set = set()
    for rec in parsed:
        f = files_by_abs.get(rec["path"])
        if f and "error" not in rec:
            by_rel[f["path"]] = rec
            rel_set.add(f["path"])
    alias_cache: dict[str, list] = {}

    def resolve_import(src: str, from_rel: str, app_dir: str) -> str | None:
        cands = []
        if src.startswith("."):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(from_rel), src))
            cands.append(base)
        else:
            if app_dir not in alias_cache:
                alias_cache[app_dir] = _load_tsconfig_paths(root, app_dir)
            for alias, target in alias_cache[app_dir]:
                if src.startswith(alias):
                    cands.append(posixpath.normpath(target + src[len(alias):]).lstrip("./"))
        for b in cands:
            if b in rel_set:
                return b
            for ext in JS_EXTS:
                if b + ext in rel_set:
                    return b + ext
            for ext in JS_EXTS:
                if f"{b}/index{ext}" in rel_set:
                    return f"{b}/index{ext}"
        return None

    for rel, rec in by_rel.items():
        f = files_by_rel[rel]
        a = app_for(rel, apps)
        app_dir = a["dir"] if a else ""
        inner = rel[len(app_dir) + 1:] if app_dir else rel
        segs = inner.split("/")
        if segs[0] in ("src", "app", "lib") and len(segs) > 2:
            mod = segs[1]
        elif segs[0] in ("src",) and len(segs) <= 2:
            mod = "root"
        elif len(segs) > 1:
            mod = segs[0]
        else:
            mod = "root"
        app_name = a["name"] if a else root.name
        module_id = f"{app_dir or '.'}::{mod if mod != 'root' else app_name}"
        kind, layer = classify_js(f, rec)
        main = next((m for m in rec["members"] if m["name"] == rec.get("defaultExport")), None)
        name = Path(rel).stem
        if name.lower() == "index" and len(segs) > 1:
            name = segs[-2]
        if main and main["name"] not in ("default",) and main["name"][:1].isupper():
            name = main["name"]
        methods = []
        for m in rec["members"]:
            if m["kind"] in ("type", "enum"):
                continue
            methods.append({"name": m["name"], "kind": m["kind"], "line": m["line"], "endLine": m["endLine"],
                            "loc": max(1, m["endLine"] - m["line"] + 1), "complexity": m.get("complexity", 1),
                            "maxNesting": m.get("maxNesting", 0), "statements": m.get("statements", 0), "doc": m.get("doc", False),
                            "public": m.get("exported", False), "params": [], "calls": m.get("calls", []), "constructor": False,
                            "abstract": False, "annotations": [d["name"] for d in m.get("decorators", [])], "_idents": m.get("idents", []),
                            "_jsx": m.get("jsx", [])})
            for mm in m.get("methods", []):
                methods.append({"name": f"{m['name']}.{mm['name']}", "kind": "method", "line": mm["line"], "endLine": mm["endLine"],
                                "loc": max(1, mm["endLine"] - mm["line"] + 1), "complexity": mm.get("complexity", 1),
                                "maxNesting": mm.get("maxNesting", 0), "statements": mm.get("statements", 0), "doc": mm.get("doc", False),
                                "public": True, "params": [], "calls": mm.get("calls", []), "constructor": mm["name"] == "constructor",
                                "abstract": False, "annotations": [d["name"] for d in mm.get("decorators", [])], "_idents": [], "_jsx": []})
        uid = "js:" + rel
        units[uid] = {
            "id": uid, "name": name, "fqn": rel, "kind": kind, "layer": layer, "language": f["language"], "file": rel,
            "line": 1, "endLine": f["loc"], "loc": f["loc"], "module": module_id, "app": app_dir, "package": posixpath.dirname(rel),
            "annotations": [], "annotationArgs": {}, "doc": any(m.get("doc") for m in rec["members"] if m.get("exported")),
            "extends": [], "implements": [], "fields": [], "methods": methods, "is_test": f["is_test"],
            "abstract": False, "public": True, "exports": rec.get("exports", []),
            "members": [{"name": m["name"], "kind": m["kind"], "line": m["line"], "exported": m.get("exported", False)} for m in rec["members"]],
        }

    # import edges + library usage
    client_base: dict[str, dict[str, str]] = {}  # rel -> {localName: baseURL}
    for rel, rec in by_rel.items():
        for c in rec.get("httpClients", []):
            client_base.setdefault(rel, {})[c["name"]] = c.get("baseURL") or ""
    for rel, rec in by_rel.items():
        uid = "js:" + rel
        u = units[uid]
        local_from: dict[str, str] = {}
        used_idents = set()
        jsx_used = set()
        for m in u["methods"]:
            used_idents.update(m.get("_idents", []))
            jsx_used.update(m.get("_jsx", []))
        for imp in rec.get("imports", []):
            tgt_rel = resolve_import(imp["source"], rel, u["app"])
            if tgt_rel:
                tgt = "js:" + tgt_rel
                names = [n["local"] for n in imp.get("names", [])]
                for n in imp.get("names", []):
                    local_from[n["local"]] = tgt_rel
                rendered = [n for n in names if n in jsx_used]
                if rendered:
                    edges.add(uid, tgt, "renders", f"<{rendered[0]} />")
                etype = "uses" if imp.get("typeOnly") else "imports"
                edges.add(uid, tgt, etype, ", ".join(names[:6]) if names else imp["source"], 0.5 if imp.get("typeOnly") else 1.0)
            elif not imp["source"].startswith("."):
                pkg = imp["source"].split("/")[0] if not imp["source"].startswith("@") else "/".join(imp["source"].split("/")[:2])
                if pkg.startswith(("@/", "~/")):
                    continue
                libraries.setdefault(pkg, set()).add(uid)
        u["_local_from"] = local_from
        # resolved call targets for impact at method level
        for m in u["methods"]:
            rc = []
            for c in m["calls"]:
                r = c.get("root")
                recv = c.get("receiver")
                # `imported().catch()` / `svc.get().then()` call a method on a return value, not on the import.
                if recv and not re.fullmatch(re.escape(r or "") + r"(\.\w+)*", recv):
                    continue
                if r and r in local_from:
                    rc.append({"target": "js:" + local_from[r], "method": c["name"] if c.get("receiver") else r, "line": c["line"],
                               "inLoop": c.get("inLoop", False)})
            m["resolvedCalls"] = rc

        # HTTP calls -> base url from imported axios instance
        for call in rec.get("apiCalls", []):
            base = ""
            cl = call.get("client")
            if cl:
                if cl in client_base.get(rel, {}):
                    base = client_base[rel][cl]
                elif cl in local_from and local_from[cl] in client_base:
                    cb = client_base[local_from[cl]]
                    base = next(iter(cb.values()), "")
            url = call["url"]
            if url.startswith("http"):
                url = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
                base = ""
            full = join_url(base, url) if base and not url.startswith(base) else url
            call["full"] = full
            call["norm"] = norm_path(full)
        u["apiCalls"] = rec.get("apiCalls", [])

        # Express / Nest routes
        for r in rec.get("routes", []):
            eid = f"ep:{r['method']} {norm_path(r['path'])}"
            endpoints[eid] = {"id": eid, "method": r["method"], "path": r["path"], "norm": norm_path(r["path"]), "unit": uid,
                              "handler": r.get("handler") or "", "file": rel, "line": r["line"], "framework": r.get("framework", "express"),
                              "params": [], "returns": None, "consumers": [], "tests": []}
            edges.add(eid, uid, "handles", r.get("handler") or rel)
        for dm in rec.get("dbModels", []):
            tid = "db:" + dm["name"].lower()
            tables.setdefault(tid, {"id": tid, "name": dm["name"], "entity": uid, "columns": [], "relations": [], "source": dm["kind"]})
            edges.add(uid, tid, "maps", f"{dm['kind']} model {dm['name']}")


def parse_prisma(root: Path, configs: list[str], tables: dict):
    """Prisma schema models become tables (with columns and relations)."""
    for c in configs:
        if not c.endswith(".prisma"):
            continue
        try:
            text = (root / c).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        models = re.findall(r"model\s+(\w+)\s*\{(.*?)\n\}", text, re.S)
        names = {m[0] for m in models}
        for name, body in models:
            mp = re.search(r'@@map\("([^"]+)"\)', body)
            tid = "db:" + name.lower()
            cols, rels = [], []
            for line in body.splitlines():
                parts = line.strip().split()
                if len(parts) < 2 or parts[0].startswith(("@@", "//")):
                    continue
                ftype = parts[1].rstrip("?[]")
                if ftype in names:
                    rels.append({"field": parts[0], "kind": "OneToMany" if parts[1].endswith("[]") else "ManyToOne", "target": "db:" + ftype.lower()})
                else:
                    cols.append({"name": parts[0], "type": parts[1], "id": "@id" in line, "relation": None})
            tables[tid] = {"id": tid, "name": mp.group(1) if mp else name, "entity": tid, "columns": cols, "relations": rels,
                           "source": "Prisma", "file": c}


def link_orm_calls(units: dict, tables: dict, edges: EdgeSet):
    """`prisma.article.findMany()` / `db.user.create()` style calls -> persists edge to the table."""
    by_lower = {t["name"].lower(): tid for tid, t in tables.items()}
    by_lower.update({tid[3:]: tid for tid in tables})
    for uid, u in units.items():
        if u["language"] == "Java":
            continue
        for m in u["methods"]:
            for c in m.get("calls", []):
                r = (c.get("receiver") or "").replace("this.", "")
                mm = re.match(r"^(?:prisma|db|client|orm|tx)\.(\w+)$", r)
                if mm and mm.group(1).lower() in by_lower:
                    edges.add(uid, by_lower[mm.group(1).lower()], "persists", f"{c['name']}() on {mm.group(1)}")


def match_endpoints(units: dict, endpoints: dict, edges: EdgeSet):
    """Link frontend HTTP calls to backend endpoints (cross-language edges)."""
    eps = list(endpoints.values())
    unmatched = []
    for uid, u in units.items():
        for call in u.get("apiCalls", []) or []:
            best, best_score = None, -1
            csegs = call["norm"].strip("/").split("/")
            for ep in eps:
                if ep["method"] not in (call["method"], "ANY"):
                    continue
                esegs = ep["norm"].strip("/").split("/")
                score = _match_segments(csegs, esegs)
                if score < 0 and esegs and esegs[0] == "api" and csegs[:1] != ["api"]:
                    score = _match_segments(csegs, esegs[1:])  # proxy that strips /api
                if score > best_score:
                    best, best_score = ep, score
            if best is not None and best_score >= 0:
                call["endpoint"] = best["id"]
                if uid not in best["consumers"]:
                    best["consumers"].append(uid)
                edges.add(uid, best["id"], "http", f"{call['method']} {call['full']}")
            else:
                unmatched.append({"unit": uid, **{k: call[k] for k in ("method", "full", "line")}})
    return unmatched


def _match_segments(c: list[str], e: list[str]) -> int:
    if len(c) != len(e):
        return -1
    score = 0
    for a, b in zip(c, e):
        if a == b:
            score += 2
        elif a == "{param}" or b == "{param}":
            score += 0
        else:
            return -1
    return score
