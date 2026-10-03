"""Code-aware retrieval for RAG and semantic search.

Chunking follows the AST (one chunk per class header, per method/function, per endpoint and per doc
section) rather than fixed windows. Ranking is BM25 over identifier-aware tokens with a code-concept
synonym expansion, optionally fused (Reciprocal Rank Fusion) with dense embeddings when an
embedding-capable provider (OpenAI / Ollama) is configured.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

STOP = set("""a an the of to in on for and or is are be by with as at from this that it its into how what where which who why does do
when will would can could should i we you my our your me show tell find get all any about there their they them using use used
explain list give implemented implement work works working happen happens project code file files""".split())

SYNONYMS = {
    "auth": ["authentication", "login", "jwt", "token", "security", "password", "credential", "authorize", "session", "filter"],
    "authentication": ["auth", "login", "jwt", "token", "security", "password"],
    "login": ["auth", "signin", "authenticate", "credential", "password", "token"],
    "payment": ["pay", "charge", "refund", "stripe", "gateway", "checkout", "transaction"],
    "pay": ["payment", "charge", "checkout"],
    "checkout": ["order", "payment", "cart", "place"],
    "order": ["checkout", "purchase", "cart"],
    "db": ["database", "repository", "entity", "table", "jpa", "sql", "query"],
    "database": ["repository", "entity", "table", "jpa", "sql", "query", "persist"],
    "email": ["mail", "notification", "send", "smtp"],
    "notification": ["email", "mail", "notify", "alert"],
    "user": ["customer", "account", "profile", "member"],
    "customer": ["user", "account"],
    "stock": ["inventory", "quantity", "warehouse"],
    "inventory": ["stock", "quantity", "restock"],
    "api": ["endpoint", "controller", "route", "rest", "http"],
    "endpoint": ["api", "controller", "route", "mapping"],
    "test": ["tests", "spec", "junit", "mock"],
    "config": ["configuration", "properties", "settings", "env"],
    "security": ["auth", "csrf", "cors", "jwt", "secret", "password"],
    "error": ["exception", "throw", "catch", "fail"],
    "product": ["catalogue", "catalog", "item", "sku"],
    "cart": ["basket", "checkout", "item"],
    "price": ["pricing", "discount", "total", "coupon", "tax"],
    "discount": ["coupon", "price"],
}


def split_ident(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return [t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if t]


def stem(t: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ers", "ies", "es", "ed", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in split_ident(text) if t not in STOP and len(t) > 1]


def expand_query(q: str) -> list[str]:
    toks = [t for t in split_ident(q) if t not in STOP and len(t) > 1]
    out = list(toks)
    for t in toks:
        out += SYNONYMS.get(t, [])
    return [stem(t) for t in out]


class Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.docs = [Counter(tokenize(c["search_text"])) for c in chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 1
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.vectors = None

    def bm25(self, q_tokens: list[str], k1=1.4, b=0.75) -> list[tuple[int, float]]:
        weights = Counter(q_tokens)
        scores = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t, w in weights.items():
                tf = d.get(t)
                if not tf:
                    continue
                s += w * self.idf.get(t, 0) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lens[i] / self.avg))
            if s > 0:
                scores.append((i, s))
        scores.sort(key=lambda x: -x[1])
        return scores

    def search(self, query: str, k: int = 10, kinds: set[str] | None = None, boost_units: set[str] | None = None,
               query_vec: list[float] | None = None) -> list[dict]:
        q_tokens = expand_query(query)
        # exact identifiers in the query get extra weight
        for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query):
            if any(ch.isupper() for ch in w[1:]):
                q_tokens += [stem(t) for t in split_ident(w)] * 2
        lex = self.bm25(q_tokens)
        ranked: dict[int, float] = defaultdict(float)
        for r, (i, s) in enumerate(lex[:200]):
            ranked[i] += 1 / (60 + r)
        if query_vec is not None and self.vectors is not None:
            import numpy as np
            v = np.asarray(query_vec, dtype="float32")
            v /= (np.linalg.norm(v) or 1)
            sims = self.vectors @ v
            for r, i in enumerate(np.argsort(-sims)[:200]):
                ranked[int(i)] += 1 / (60 + r)
        lex_score = dict(lex)
        out = []
        for i, s in sorted(ranked.items(), key=lambda kv: -kv[1]):
            c = self.chunks[i]
            if kinds and c["kind"] not in kinds:
                continue
            bonus = 1.25 if boost_units and c.get("unit") in boost_units else 1.0
            out.append({**{k_: v for k_, v in c.items() if k_ != "search_text"}, "score": round(s * bonus * 1000, 3),
                        "bm25": round(lex_score.get(i, 0), 3)})
        out.sort(key=lambda x: -x["score"])
        return out[:k]


def build_chunks(root: Path, twin: dict) -> list[dict]:
    chunks: list[dict] = []
    cache: dict[str, list[str]] = {}

    def src(file: str) -> list[str]:
        if file not in cache:
            try:
                cache[file] = (root / file).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                cache[file] = []
        return cache[file]

    units = twin["units"]
    deps = defaultdict(list)
    rdeps = defaultdict(list)
    for e in twin["edges"]:
        if e["source"] in units and e["target"] in units:
            deps[e["source"]].append(units[e["target"]]["name"])
            rdeps[e["target"]].append(units[e["source"]]["name"])
    for uid, u in units.items():
        lines = src(u["file"])
        header_end = min(len(lines), u["line"] + 25)
        first_method = min([m["line"] for m in u["methods"]] or [header_end])
        header = "\n".join(lines[max(0, u["line"] - 4): min(header_end, first_method - 1 if first_method > u["line"] else header_end)])
        meta = (f"{u['name']} is a {u['layer']} ({u['kind']}, {u['language']}) in module {u['module'].split('::')[-1]}. "
                f"Depends on: {', '.join(sorted(set(deps[uid]))[:15]) or 'nothing'}. Used by: {', '.join(sorted(set(rdeps[uid]))[:15]) or 'nothing'}. "
                f"Methods: {', '.join(m['name'] for m in u['methods'][:30])}.")
        chunks.append({"id": f"{uid}#header", "kind": "unit", "unit": uid, "name": u["name"], "file": u["file"], "start": u["line"],
                       "end": max(u["line"], first_method - 1), "layer": u["layer"], "text": header[:2500], "meta": meta,
                       "search_text": f"{u['name']} {u['name']} {u['layer']} {u['file']} {meta} {header}"})
        for m in u["methods"]:
            if m.get("constructor") and m.get("loc", 0) < 12:
                continue
            body = "\n".join(lines[m["line"] - 1: min(m["endLine"], m["line"] + 80)])
            if not body.strip():
                continue
            chunks.append({"id": f"{uid}#{m['name']}#{m['line']}", "kind": "function", "unit": uid, "name": f"{u['name']}.{m['name']}",
                           "file": u["file"], "start": m["line"], "end": m["endLine"], "layer": u["layer"], "text": body[:3500],
                           "meta": f"{m['name']}() in {u['name']} (complexity {m['complexity']})",
                           "search_text": f"{u['name']} {m['name']} {m['name']} {u['layer']} {body}"})
    for eid, ep in twin["endpoints"].items():
        h = units.get(ep["unit"], {})
        consumers = [units[c]["name"] for c in ep.get("consumers", []) if c in units]
        txt = (f"{ep['method']} {ep['path']} handled by {h.get('name', '?')}.{ep['handler']}()"
               f"{'; called from ' + ', '.join(consumers) if consumers else '; no frontend consumer found'}")
        chunks.append({"id": eid, "kind": "api", "unit": ep["unit"], "name": f"{ep['method']} {ep['path']}", "file": ep["file"],
                       "start": ep["line"], "end": ep["line"], "layer": "endpoint", "text": txt, "meta": txt,
                       "search_text": f"{txt} api endpoint {ep['path'].replace('/', ' ')}"})
    for d in twin.get("docs", [])[:30]:
        lines = src(d)
        sect, start, buf = "Overview", 1, []
        for i, l in enumerate(lines + ["# END"], start=1):
            if l.startswith("#") and buf:
                text = "\n".join(buf).strip()
                if text:
                    chunks.append({"id": f"doc:{d}:{start}", "kind": "doc", "unit": None, "name": f"{Path(d).name} › {sect}", "file": d,
                                   "start": start, "end": i - 1, "layer": "doc", "text": text[:3000], "meta": sect,
                                   "search_text": f"{sect} {text}"})
                buf, start = [], i
                sect = l.lstrip("# ").strip()
            elif l.startswith("#"):
                sect, start = l.lstrip("# ").strip(), i
            else:
                buf.append(l)
    for c in twin.get("configs", [])[:20]:
        lines = src(c)
        if lines and len(lines) < 400:
            text = "\n".join(lines)[:3000]
            chunks.append({"id": f"cfg:{c}", "kind": "config", "unit": None, "name": c, "file": c, "start": 1, "end": len(lines),
                           "layer": "config", "text": text, "meta": f"configuration file {c}", "search_text": f"{c} configuration {text}"})
    return chunks


def save_index(path: Path, chunks: list[dict], vectors=None):
    path.write_text(json.dumps(chunks))
    if vectors is not None:
        import numpy as np
        np.save(path.with_suffix(".npy"), np.asarray(vectors, dtype="float32"))


def load_index(path: Path) -> Index | None:
    if not path.exists():
        return None
    idx = Index(json.loads(path.read_text()))
    vp = path.with_suffix(".npy")
    if vp.exists():
        try:
            import numpy as np
            v = np.load(vp)
            norms = np.linalg.norm(v, axis=1, keepdims=True)
            norms[norms == 0] = 1
            idx.vectors = v / norms
        except Exception:
            idx.vectors = None
    return idx


def maybe_embed(chunks: list[dict], settings: dict):
    """Compute dense vectors if an embedding-capable provider is configured; otherwise None."""
    mode = settings.get("embeddings", "auto")
    if mode == "none":
        return None
    from .llm import OpenAI, Ollama
    prov = None
    if mode in ("auto", "openai") and settings.get("openai_api_key"):
        prov = OpenAI(settings["openai_api_key"], "", settings.get("openai_base_url") or "https://api.openai.com/v1")
    elif mode == "ollama" or (mode == "auto" and settings.get("provider") == "ollama"):
        o = Ollama(settings.get("ollama_url") or "http://localhost:11434", "", settings.get("ollama_embed_model") or "nomic-embed-text")
        prov = o if o.available() else None
    if not prov:
        return None
    texts = [(c["meta"] + "\n" + c["text"])[:2000] for c in chunks]
    vecs = []
    try:
        for i in range(0, len(texts), 64):
            vecs += prov.embed(texts[i:i + 64])
        return vecs
    except Exception:
        return None


def embed_query(q: str, settings: dict):
    vecs = maybe_embed([{"meta": "", "text": q}], settings)
    return vecs[0] if vecs else None
