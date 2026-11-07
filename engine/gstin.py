import re
CH = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
def checksum(g14):
    tot = 0
    for i, c in enumerate(g14):
        v = CH.index(c) * (1 if i % 2 == 0 else 2)
        tot += v // 36 + v % 36
    return CH[(36 - tot % 36) % 36]
def valid(g):
    return bool(re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g or "")) and checksum(g[:14]) == g[14]
# characters Tesseract confuses; used to repair a GSTIN whose checksum fails
CONF = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z", "G": "6", "6": "G"}
def repair(g):
    """Try single-character confusions until the checksum passes. Returns (gstin, repaired?)"""
    if valid(g): return g, False
    if not g or len(g) != 15: return g, False
    for i, c in enumerate(g):
        if c in CONF:
            cand = g[:i] + CONF[c] + g[i+1:]
            if valid(cand): return cand, True
    return g, False

PAIRS = {frozenset(x) for x in ["O0", "I1", "IT", "IJ", "S5", "B8", "Z2", "G6", "58", "UV", "DO", "QO", "Q0"]}
def repair_with_registry(g, registry, max_diff=3):
    """OCR often swaps look-alike characters. Accept a registry GSTIN only if (a) every differing
    character is a known look-alike pair, (b) it passes the checksum, (c) it is the unique such match."""
    if not g or len(g) != 15: return g, False
    hits = []
    for cand in registry:
        diffs = [(a, b) for a, b in zip(g, cand) if a != b]
        if 0 < len(diffs) <= max_diff and all(frozenset(d) in PAIRS for d in diffs) and valid(cand):
            hits.append(cand)
    return (hits[0], True) if len(hits) == 1 else (g, False)
