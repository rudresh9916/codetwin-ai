"""Clone detection via rolling hashes over normalised source lines (Type-1/Type-2-ish clones)."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path

WINDOW = 6
_SKIP = re.compile(r"^(import |package |@|\}|\{|\)|\]|//|/\*|\*|export \{|\};?$|\);?$)")


def _normalise(line: str) -> str:
    s = line.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def detect(files: list[dict], min_lines: int = WINDOW) -> list[dict]:
    """Return clone pairs: [{a:{file,start,end}, b:{...}, lines, snippet}]."""
    windows: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    meaningful_cache: dict[str, list[tuple[int, str]]] = {}
    for f in files:
        if not f.get("analyzed") or f.get("is_test"):
            continue
        try:
            text = Path(f["abs"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = []
        for i, raw in enumerate(text.splitlines(), start=1):
            s = _normalise(raw)
            if len(s) < 4 or _SKIP.match(s):
                continue
            lines.append((i, s))
        meaningful_cache[f["path"]] = lines
        for k in range(0, max(0, len(lines) - min_lines + 1)):
            chunk = lines[k:k + min_lines]
            h = hashlib.md5("\n".join(s for _, s in chunk).encode()).hexdigest()
            windows[h].append((f["path"], k, chunk[0][0]))

    # Pair up windows, then merge consecutive window matches into blocks
    pair_hits: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for occ in windows.values():
        if len(occ) < 2 or len(occ) > 12:
            continue
        for i in range(len(occ)):
            for j in range(i + 1, len(occ)):
                (fa, ka, _), (fb, kb, _) = occ[i], occ[j]
                if fa == fb and abs(ka - kb) < min_lines:
                    continue
                if (fa, ka) > (fb, kb):
                    (fa, ka), (fb, kb) = (fb, kb), (fa, ka)
                pair_hits[(fa, fb)].append((ka, kb))
    clones = []
    for (fa, fb), hits in pair_hits.items():
        # Consecutive windows of one clone share an offset (kb - ka); merge along each offset so a copied block
        # is reported once instead of once per overlapping window.
        hits = sorted(set(hits), key=lambda h: (h[1] - h[0], h[0]))
        block = None
        blocks = []
        for ka, kb in hits:
            if block and kb - ka == block[2] - block[0] and ka <= block[1] + 1:
                block[1], block[3] = ka, kb
            else:
                if block:
                    blocks.append(block)
                block = [ka, ka, kb, kb]
        if block:
            blocks.append(block)
        la, lb = meaningful_cache[fa], meaningful_cache[fb]
        for a0, a1, b0, b1 in blocks:
            sa, ea = la[a0][0], la[a1 + min_lines - 1][0]
            sb, eb = lb[b0][0], lb[b1 + min_lines - 1][0]
            n = a1 - a0 + min_lines
            snippet = "\n".join(s for _, s in la[a0:a0 + min(n, 8)])
            clones.append({"a": {"file": fa, "start": sa, "end": ea}, "b": {"file": fb, "start": sb, "end": eb},
                           "lines": n, "snippet": snippet})
    clones.sort(key=lambda c: -c["lines"])
    return clones[:200]
