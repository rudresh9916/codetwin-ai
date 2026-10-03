"""Rebuild the ShopVerse sample repository with a realistic multi-month git history.

Usage:  python build_sample_history.py [path-to-shopverse]

The final source tree is kept; the script re-creates .git so CodeTwin's
evolution/hotspot features have real commit history to analyse.
"""
import os, shutil, subprocess, sys, tempfile, random
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "shopverse").resolve()
J = "backend/src/main/java/com/shopverse/"
F = "frontend/src/"

PHASES = [
    ("2026-01-12", "Aarav Mehta", "Initial commit: Spring Boot API with users and catalogue", [
        "README.md", "backend/pom.xml", "backend/src/main/resources/application.properties", J + "ShopverseApplication.java",
        J + "user/", J + "product/Product.java", J + "product/ProductRepository.java", J + "product/ProductController.java",
        "database/schema.sql"]),
    ("2026-01-20", "Priya Sharma", "Add React storefront with product listing", [
        "frontend/package.json", "frontend/tsconfig.json", F + "main.tsx", F + "App.tsx", F + "api/client.ts", F + "api/productApi.ts",
        F + "pages/ProductsPage.tsx", F + "pages/ProductDetailPage.tsx", F + "components/ProductCard.tsx", F + "components/Navbar.tsx", F + "utils/format.ts"]),
    ("2026-02-03", "Aarav Mehta", "Add JWT authentication and security config", [
        J + "auth/", J + "config/", F + "api/authApi.ts", F + "context/", F + "hooks/useAuth.ts", F + "pages/LoginPage.tsx",
        F + "components/ProtectedRoute.tsx", F + "api/userApi.ts", F + "pages/ProfilePage.tsx"]),
    ("2026-02-17", "Dev Patel", "Inventory tracking and shopping cart", [
        J + "inventory/", J + "product/ProductService.java", J + "cart/", F + "api/cartApi.ts", F + "hooks/useCart.ts",
        F + "pages/CartPage.tsx", F + "components/CartItem.tsx"]),
    ("2026-03-05", "Aarav Mehta", "Checkout: orders, Stripe payments and email notifications", [
        J + "order/", J + "payment/", J + "notification/", F + "api/orderApi.ts", F + "pages/CheckoutPage.tsx", F + "pages/OrdersPage.tsx"]),
    ("2026-04-02", "Priya Sharma", "Product reviews and ratings", [J + "review/"]),
    ("2026-04-28", "Dev Patel", "Admin dashboard and sales reports", [J + "admin/", J + "common/", F + "pages/AdminDashboard.tsx"]),
    ("2026-05-15", "Priya Sharma", "Add unit tests for services", ["backend/src/test/"]),
    ("2026-06-01", "Aarav Mehta", "Docker compose setup", ["docker-compose.yml"]),
]

CHURN = {  # file -> list of (date, author, message)
    J + "payment/PaymentService.java": [
        ("2026-03-09", "Aarav Mehta", "Fix double charge on retry"), ("2026-03-14", "Dev Patel", "Handle card_declined separately"),
        ("2026-03-21", "Aarav Mehta", "Partial refunds"), ("2026-04-06", "Aarav Mehta", "Refund window policy"),
        ("2026-04-19", "Priya Sharma", "Hotfix: refund NPE when payment missing"), ("2026-05-02", "Aarav Mehta", "Retry reminders for failed payments"),
        ("2026-05-24", "Dev Patel", "INR formatting in payment emails"), ("2026-06-10", "Aarav Mehta", "Mark order paid after successful charge"),
        ("2026-06-14", "Aarav Mehta", "Cancel order with refund + restock"),
        ("2026-07-03", "Aarav Mehta", "Hotfix: payment status after gateway timeout"), ("2026-07-29", "Dev Patel", "Tune retry count"),
        ("2026-08-18", "Aarav Mehta", "Fix rounding in refund calculation")],
    J + "order/OrderService.java": [("2026-06-10", "Aarav Mehta", "Mark order paid after successful charge"),
        ("2026-03-11", "Aarav Mehta", "Coupon codes"), ("2026-03-28", "Dev Patel", "Shipping charges by city"),
        ("2026-04-12", "Aarav Mehta", "GST calculation"), ("2026-05-09", "Priya Sharma", "Low-stock alerts on order"),
        ("2026-06-14", "Aarav Mehta", "Cancel order with refund + restock"), ("2026-07-21", "Dev Patel", "Ship order endpoint"),
        ("2026-08-25", "Aarav Mehta", "Hotfix: inventory decremented twice")],
    # changes that touched several files at once (gives CodeTwin change-coupling data)
    J + "order/OrderController.java": [("2026-06-14", "Aarav Mehta", "Cancel order with refund + restock"),
                                       ("2026-07-21", "Dev Patel", "Ship order endpoint")],
    J + "notification/EmailService.java": [("2026-05-02", "Aarav Mehta", "Retry reminders for failed payments"),
                                           ("2026-06-14", "Aarav Mehta", "Cancel order with refund + restock"),
                                           ("2026-07-21", "Dev Patel", "Ship order endpoint")],
    J + "auth/AuthService.java": [("2026-02-10", "Aarav Mehta", "Block disabled accounts"), ("2026-05-30", "Priya Sharma", "Password reset flow")],
    F + "pages/CheckoutPage.tsx": [("2026-03-18", "Priya Sharma", "Coupon field at checkout"), ("2026-06-20", "Priya Sharma", "Show payment failure message"),
                                   ("2026-08-02", "Dev Patel", "Refresh cart after order")],
    J + "product/ProductService.java": [("2026-04-09", "Dev Patel", "Bulk pricing discounts"), ("2026-06-26", "Dev Patel", "In-stock listing")],
    J + "user/UserService.java": [("2026-02-24", "Aarav Mehta", "Record last login")],
    F + "hooks/useCart.ts": [("2026-03-02", "Priya Sharma", "Cart total from API")],
}
EMAILS = {"Aarav Mehta": "aarav@shopverse.dev", "Priya Sharma": "priya@shopverse.dev", "Dev Patel": "dev@shopverse.dev"}


def git(cwd, *args, date=None, author=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T11:00:00+05:30"
    if author:
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = author
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = EMAILS[author]
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def main():
    random.seed(7)
    final = Path(tempfile.mkdtemp()) / "final"
    shutil.copytree(ROOT, final, ignore=shutil.ignore_patterns(".git"))
    shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    git(ROOT, "init", "-q", "-b", "main")
    events = [(d, a, m, ("phase", paths)) for d, a, m, paths in PHASES]
    grouped = {}
    for f, items in CHURN.items():
        items = sorted(items)
        for i, (d, a, m) in enumerate(items):
            grouped.setdefault((d, a, m), []).append((f, i == len(items) - 1))
    for (d, a, m), fl in grouped.items():
        events.append((d, a, m, ("churn", fl)))
    events.sort(key=lambda e: e[0])
    for date, author, msg, ev in events:
        if ev[0] == "phase":
            for p in ev[1]:
                src, dst = final / p, ROOT / p
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        else:
            for f, last in ev[1]:
                target = ROOT / f
                if not target.exists():
                    continue
                lines = (final / f).read_text().splitlines()
                if not last:  # intermediate revision: a slightly different version of the file
                    idx = random.randint(len(lines) // 3, max(len(lines) // 3 + 1, len(lines) - 3))
                    cmt = "//" if f.endswith((".java", ".ts", ".tsx")) else "#"
                    lines.insert(idx, f"    {cmt} {msg.lower()} (wip)")
                target.write_text("\n".join(lines) + "\n")
        git(ROOT, "add", "-A")
        git(ROOT, "commit", "-q", "--allow-empty", "-m", msg, date=date, author=author)
    # final sync to make sure the tree equals the final sources
    shutil.copytree(final, ROOT, dirs_exist_ok=True)
    git(ROOT, "add", "-A")
    git(ROOT, "commit", "-q", "--allow-empty", "-m", "Release v1.4.0", date="2026-09-01", author="Aarav Mehta")
    print("History rebuilt at", ROOT)


if __name__ == "__main__":
    main()
