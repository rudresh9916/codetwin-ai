"""Repository scanner: discovers files, languages, line counts, frameworks, databases and build roots."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from ..config import IGNORED_DIRS, MAX_FILE_BYTES

LANG_BY_EXT = {
    ".java": "Java", ".kt": "Kotlin", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".py": "Python", ".go": "Go", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".h": "C", ".rs": "Rust", ".swift": "Swift", ".scala": "Scala", ".vue": "Vue",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sql": "SQL", ".xml": "XML", ".yml": "YAML", ".yaml": "YAML",
    ".json": "JSON", ".md": "Markdown", ".properties": "Properties", ".gradle": "Gradle", ".sh": "Shell",
}
ANALYZED = {".java", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
CONFIG_NAMES = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json", "docker-compose.yml", "docker-compose.yaml",
                "Dockerfile", "application.properties", "application.yml", "application.yaml", ".env", ".env.example",
                "tsconfig.json", "jsconfig.json", "settings.gradle", "vite.config.ts", "vite.config.js", "next.config.js",
                "next.config.mjs", "angular.json", "nest-cli.json", "prisma/schema.prisma", "schema.prisma"}
TEST_PAT = re.compile(r"(^|/)(src/test/|__tests__/|tests?/)|(\.|_)(test|spec)\.[jt]sx?$|Test\.java$|Tests\.java$|IT\.java$")
GENERATED_PAT = re.compile(r"\.min\.js$|\.bundle\.js$|-lock\.json$|\.d\.ts$|\.map$")

FRAMEWORK_RULES = [
    # (regex over build file text, framework label, category)
    (r"spring-boot", "Spring Boot", "backend"), (r"spring-boot-starter-web\b|spring-webmvc", "Spring MVC", "backend"),
    (r"spring-boot-starter-webflux", "Spring WebFlux", "backend"), (r"spring-boot-starter-data-jpa|hibernate", "JPA / Hibernate", "orm"),
    (r"spring-boot-starter-security|spring-security", "Spring Security", "security"), (r"jjwt|java-jwt|jsonwebtoken", "JWT", "security"),
    (r"spring-kafka|kafka-clients|\"kafkajs\"", "Kafka", "messaging"), (r"spring-boot-starter-amqp|\"amqplib\"", "RabbitMQ", "messaging"),
    (r"lombok", "Lombok", "tooling"), (r"junit", "JUnit", "testing"), (r"mockito", "Mockito", "testing"),
    (r"stripe", "Stripe", "payments"), (r"spring-boot-starter-mail|nodemailer", "Email (SMTP)", "integration"),
    (r"\"react\"\s*:", "React", "frontend"), (r"\"next\"\s*:", "Next.js", "frontend"), (r"\"vue\"\s*:", "Vue", "frontend"),
    (r"\"@angular/core\"", "Angular", "frontend"), (r"\"svelte\"\s*:", "Svelte", "frontend"),
    (r"\"express\"\s*:", "Express", "backend"), (r"\"@nestjs/core\"", "NestJS", "backend"), (r"\"fastify\"\s*:", "Fastify", "backend"),
    (r"\"koa\"\s*:", "Koa", "backend"), (r"\"axios\"\s*:", "Axios", "http"), (r"\"react-router(-dom)?\"", "React Router", "frontend"),
    (r"\"redux\"|\"@reduxjs/toolkit\"", "Redux", "state"), (r"\"zustand\"", "Zustand", "state"), (r"\"vite\"\s*:", "Vite", "tooling"),
    (r"\"tailwindcss\"", "Tailwind CSS", "frontend"), (r"\"mongoose\"", "Mongoose", "orm"), (r"\"prisma\"|\"@prisma/client\"", "Prisma", "orm"),
    (r"\"sequelize\"", "Sequelize", "orm"), (r"\"typeorm\"", "TypeORM", "orm"), (r"\"jest\"\s*:", "Jest", "testing"),
    (r"\"vitest\"", "Vitest", "testing"), (r"\"graphql\"", "GraphQL", "api"), (r"\"socket\.io\"", "Socket.IO", "realtime"),
]
DB_RULES = [
    (r"postgres", "PostgreSQL"), (r"mysql|mariadb", "MySQL"), (r"mongo", "MongoDB"), (r"\bh2\b|com\.h2database", "H2"),
    (r"redis", "Redis"), (r"sqlite", "SQLite"), (r"oracle", "Oracle"), (r"sqlserver|mssql", "SQL Server"), (r"cassandra", "Cassandra"),
    (r"elasticsearch", "Elasticsearch"), (r"dynamodb", "DynamoDB"),
]

_COMMENT_RE = {
    "c": (re.compile(r"^\s*//"), re.compile(r"/\*"), re.compile(r"\*/")),
}


def is_test_path(rel: str) -> bool:
    return bool(TEST_PAT.search(rel))


def count_lines(text: str, ext: str) -> dict:
    """Physical / source / comment / blank line counts for C-family languages."""
    total = blank = comment = 0
    in_block = False
    c_like = ext in ANALYZED or ext in {".kt", ".cs", ".go", ".scala", ".swift", ".c", ".cpp", ".h", ".rs", ".php"}
    for raw in text.splitlines():
        total += 1
        line = raw.strip()
        if not line:
            blank += 1
            continue
        if not c_like:
            continue
        if in_block:
            comment += 1
            if "*/" in line:
                in_block = False
            continue
        if line.startswith("//"):
            comment += 1
        elif line.startswith("/*"):
            comment += 1
            if "*/" not in line[2:]:
                in_block = True
        elif line.startswith("*"):
            comment += 1
    return {"loc": total, "sloc": max(0, total - blank - comment), "comments": comment, "blank": blank}


# --- Halstead ---------------------------------------------------------------------------------
_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|'
                       r'>>>=|>>=|<<=|===|!==|\?\?=|\.\.\.|->|=>|==|!=|<=|>=|&&|\|\||\?\?|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|'
                       r'[{}()\[\];,.<>+\-*/%&|^!~?:=@]')
_KEYWORDS = set("""abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally
float for goto if implements import instanceof int interface long native new package private protected public return short static
strictfp super switch synchronized this throw throws transient try void volatile while var let function async await yield typeof
delete in of export from as type readonly declare namespace module get set constructor null true false undefined record""".split())


def halstead(text: str) -> dict:
    ops, opnds = Counter(), Counter()
    for m in _TOKEN_RE.finditer(_strip_comments(text)):
        tok = m.group(0)
        if tok[0].isalpha() or tok[0] in "_$":
            (ops if tok in _KEYWORDS else opnds)[tok] += 1
        elif tok[0].isdigit() or tok[0] in "\"'`":
            opnds[tok] += 1
        else:
            ops[tok] += 1
    n1, n2 = len(ops), len(opnds)
    N1, N2 = sum(ops.values()), sum(opnds.values())
    n, N = n1 + n2, N1 + N2
    volume = N * math.log2(n) if n > 1 else 0.0
    difficulty = (n1 / 2) * (N2 / n2) if n2 else 0.0
    return {"n1": n1, "n2": n2, "N1": N1, "N2": N2, "volume": round(volume, 1), "difficulty": round(difficulty, 1),
            "effort": round(volume * difficulty, 1)}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)//.*$", " ", text)


def maintainability_index(volume: float, complexity: int, sloc: int) -> float:
    """Microsoft-normalised Maintainability Index (0..100)."""
    if sloc <= 0:
        return 100.0
    v = max(volume, 1.0)
    mi = 171 - 5.2 * math.log(v) - 0.23 * complexity - 16.2 * math.log(sloc)
    return round(max(0.0, min(100.0, mi * 100 / 171)), 1)


# --- Scan -------------------------------------------------------------------------------------
def scan(root: Path) -> dict:
    root = Path(root).resolve()
    files: list[dict] = []
    configs: list[str] = []
    lang_files, lang_loc = Counter(), Counter()
    docs: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".") and
                       f"{rel_dir}/{d}".lstrip("./") not in IGNORED_DIRS]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = full.relative_to(root).as_posix()
            ext = full.suffix.lower()
            if fn in CONFIG_NAMES or rel in CONFIG_NAMES or fn.startswith("application-") or fn.endswith(".prisma") or \
                    (fn.startswith("docker-compose") and ext in {".yml", ".yaml"}):
                configs.append(rel)
            if ext == ".md":
                docs.append(rel)
            lang = LANG_BY_EXT.get(ext)
            if not lang or GENERATED_PAT.search(fn):
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            if ext in ANALYZED or ext in {".sql"}:
                try:
                    text = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lc = count_lines(text, ext)
                rec = {"path": rel, "abs": str(full), "ext": ext, "language": lang, "size": size, **lc,
                       "is_test": is_test_path(rel), "analyzed": ext in ANALYZED}
                if ext in ANALYZED:
                    rec["halstead"] = halstead(text)
                files.append(rec)
                lang_files[lang] += 1
                lang_loc[lang] += lc["sloc"]
            elif lang not in {"JSON", "Markdown", "XML", "YAML", "Properties"}:
                lang_files[lang] += 1
    frameworks, databases = detect_stack(root, configs, files)
    return {"files": files, "configs": sorted(configs), "docs": sorted(docs), "languages": dict(lang_files),
            "language_loc": dict(lang_loc), "frameworks": frameworks, "databases": databases, "apps": detect_apps(root, configs)}


def detect_stack(root: Path, configs: list[str], files: list[dict]) -> tuple[list[dict], list[str]]:
    blob = []
    for c in configs:
        try:
            blob.append((root / c).read_text(encoding="utf-8", errors="replace")[:200_000])
        except OSError:
            pass
    text = "\n".join(blob)
    seen, frameworks = set(), []
    for pat, label, cat in FRAMEWORK_RULES:
        if label not in seen and re.search(pat, text, re.I):
            seen.add(label)
            frameworks.append({"name": label, "category": cat})
    if any(f["ext"] in {".ts", ".tsx"} for f in files) and "TypeScript" not in seen:
        frameworks.append({"name": "TypeScript", "category": "language"})
    dbs = []
    db_text = text + "\n" + "\n".join(f["path"] for f in files if f["ext"] == ".sql")
    for pat, label in DB_RULES:
        if re.search(pat, db_text, re.I) and label not in dbs:
            dbs.append(label)
    return frameworks, dbs


def detect_apps(root: Path, configs: list[str]) -> list[dict]:
    """Deployable sub-projects: directories that own a build manifest."""
    apps = []
    for c in configs:
        name = Path(c).name
        if name in {"pom.xml", "build.gradle", "build.gradle.kts", "package.json"}:
            d = Path(c).parent.as_posix()
            d = "" if d == "." else d
            if any(a["dir"] == d for a in apps):
                continue
            kind = "java" if name != "package.json" else "node"
            label = d.split("/")[-1] if d else root.name
            meta = {}
            if name == "package.json":
                try:
                    pj = json.loads((root / c).read_text(encoding="utf-8", errors="replace"))
                    meta = {"package": pj.get("name"), "scripts": list((pj.get("scripts") or {}).keys())}
                    deps = {**(pj.get("dependencies") or {}), **(pj.get("devDependencies") or {})}
                    if any(k in deps for k in ("react", "vue", "@angular/core", "svelte", "next")):
                        kind = "frontend"
                    elif any(k in deps for k in ("express", "@nestjs/core", "fastify", "koa")):
                        kind = "node-backend"
                except Exception:
                    pass
            apps.append({"dir": d, "name": label, "kind": kind, "manifest": c, **meta})
    # nested manifests (e.g. root package.json for workspaces) keep the deepest owner per file
    apps.sort(key=lambda a: -len(a["dir"]))
    return apps


def app_for(path: str, apps: list[dict]) -> dict | None:
    for a in apps:  # sorted deepest first
        if not a["dir"] or path == a["dir"] or path.startswith(a["dir"] + "/"):
            return a
    return None
