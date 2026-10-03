"""End-to-end tests for the analysis engine on the bundled ShopVerse sample.

Run:  cd backend && python -m pytest -q        (or: python tests/test_twin.py)
Requires Java 17+ and Node 18+ with backend/analyzers/js dependencies installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.builder import build_twin  # noqa: E402
from app.analysis.impact import TwinGraph, analyze_impact, whatif  # noqa: E402
from app.ai import retrieval, docs  # noqa: E402
from app.ai.assistant import build_context, offline_answer  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "shopverse"
_twin = None


def twin():
    global _twin
    if _twin is None:
        _twin = build_twin(SAMPLE, "ShopVerse")
    return _twin


def uid(name):
    return next(k for k, u in twin()["units"].items() if u["name"] == name)


def test_parsing_and_model():
    t = twin()
    assert not t["warnings"], t["warnings"]
    c = t["summary"]["counts"]
    assert c["endpoints"] >= 20 and c["tables"] == 7
    assert t["units"][uid("OrderController")]["layer"] == "controller"
    assert t["units"][uid("PaymentRepository")]["layer"] == "repository"
    assert t["units"][uid("CheckoutPage")]["layer"] == "page"
    assert "ep:POST /api/orders" in t["endpoints"]


def test_cross_language_http_links():
    ep = twin()["endpoints"]["ep:POST /api/orders"]
    assert uid("orderApi") in ep["consumers"], "frontend axios call must link to the Spring endpoint"
    assert "ep:GET /api/admin/reports/legacy-export" in twin()["summary"]["unused_endpoints"]


def test_cycle_and_god_class_detected():
    t = twin()
    names = [{t["units"][x]["name"] for x in c} for c in t["cycles"]]
    assert {"OrderService", "PaymentService"} in names
    assert t["units"][uid("OrderService")]["god_class"]


def test_security_rules():
    titles = {i["title"] for i in twin()["issues"]}
    assert "Hard-coded Stripe live secret key" in titles
    assert "SQL built by string concatenation" in titles
    assert "Unsanitised HTML rendering (XSS)" in titles


def test_impact_propagates_to_frontend():
    tg = TwinGraph(twin())
    r = analyze_impact(tg, uid("PaymentService"))
    names = {a["name"] for a in r["affected"]}
    assert {"OrderService", "OrderController", "CheckoutPage"} <= names
    assert any(d["name"] == "payments" for d in r["data"])
    assert r["risk"]["level"] in {"MEDIUM", "HIGH"}


def test_signature_change_only_hits_callers():
    tg = TwinGraph(twin())
    r = analyze_impact(tg, uid("UserService"), "signature", "findByEmail")
    direct = {a["name"] for a in r["affected"] if a["distance"] == 1}
    assert direct == {"AuthService", "JwtAuthFilter"}


def test_whatif_scenarios():
    tg = TwinGraph(twin())
    split = whatif(tg, "split")
    assert len(split["services"]) >= 3
    ext = whatif(tg, "extract", "backend::payment")
    assert ext["boundary"]["distributed_transactions"]
    rep = whatif(tg, "replace", uid("PaymentGateway"))
    assert {r["method"] for r in rep["contract"]} == {"charge", "refund"}


def test_health_and_debt_are_bounded():
    h = twin()["health"]
    assert 0 <= h["overall"] <= 100
    assert all(0 <= d["score"] <= 100 for d in h["dimensions"].values())
    assert twin()["debt"]["minutes"] > 0


def test_refactoring_advice():
    types = {r["type"] for r in twin()["refactorings"]}
    assert {"split-class", "break-cycle", "extract-method"} <= types


def test_rag_retrieval_and_offline_answer():
    t = twin()
    idx = retrieval.Index(retrieval.build_chunks(SAMPLE, t))
    hits = idx.search("where is authentication implemented", k=5)
    assert any("Auth" in h["name"] or "Jwt" in h["name"] or "Security" in h["name"] for h in hits)
    ctx = build_context(t, TwinGraph(t), idx, "What could be affected if I modify UserService?", {"embeddings": "none"})
    assert ctx["facts"] and "UserService" in offline_answer(ctx, "q")


def test_docs_generation():
    d = docs.generate(twin(), {"provider": "none"})
    titles = [s["title"] for s in d["sections"]]
    assert "API Reference" in titles and "Sequence Diagrams" in titles
    assert "```mermaid" in d["markdown"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in tests:
        fn()
        print("✓", fn.__name__)
    print(f"{len(tests)} tests passed")
