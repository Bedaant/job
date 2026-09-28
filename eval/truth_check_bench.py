"""Truth-check (pass 2) precision/recall on eval/truth_check_cases.json, live.

Runs ONLY pass 2 against whatever LLM_PROVIDER apps/api/.env names, on drafts
with known unsupported additions and known-clean drafts. A flag is a true
positive when it names one of the case's `unsupported` phrases.

    cd apps/api && .venv/Scripts/python ../../eval/truth_check_bench.py [variant ...] [--repeat N]

Variants: base, base_think, strict, strict_think, det, base+det, strict+det,
strict_think+det (a "+det" variant reuses the LLM run and adds the
deterministic post-check; it costs nothing extra).
"""
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "api")
sys.path.insert(0, API_DIR)
os.chdir(API_DIR)  # Settings reads .env relative to CWD

from rapidfuzz import fuzz  # noqa: E402

from tailoring import engine  # noqa: E402

CASES = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "truth_check_cases.json")))
THINK = {"chat_template_kwargs": {"enable_thinking": True}}


def _user(case):
    return f"CANDIDATE FACTS KB:\n{json.dumps(case['facts'], indent=2)}\n\nDRAFT:\n{json.dumps(case['draft'], indent=2)}"


def _llm(case, strict, think):
    kw = {"extra_body": THINK, "max_tokens": 16384} if think else {}
    t = time.perf_counter()
    if strict:
        audit = engine._call_claude_structured(engine.STRICT_CHECK_SYSTEM, _user(case), engine.ClaimAudit, **kw)
        flags = audit.unsupported({f["id"] for f in case["facts"]})
    else:
        flags = engine._call_claude_structured(engine.CHECK_SYSTEM, _user(case), engine.TruthCheckResult, **kw).unsupported_claims
    return flags, time.perf_counter() - t


def _det(case):
    d = case["draft"]
    sentences = engine.split_sentences(d["summary"]) + d["bullets"] + engine.split_sentences(d["cover_letter"])
    return engine.deterministic_unsupported(case["facts"], sentences)


def _hit(needle, flag):
    n, f = needle.lower(), flag.lower()
    return n in f or fuzz.partial_ratio(n, f) >= 85


def score(runs):
    """runs: list of (case, flags). Returns precision, recall, clean-case false alarms."""
    flags_total = flags_ok = needles_total = needles_hit = clean_alarms = 0
    for case, flags in runs:
        needles = case["unsupported"]
        flags_total += len(flags)
        flags_ok += sum(any(_hit(n, f) for n in needles) for f in flags)
        needles_total += len(needles)
        needles_hit += sum(any(_hit(n, f) for f in flags) for n in needles)
        clean_alarms += (not needles) and bool(flags)
    precision = flags_ok / flags_total if flags_total else 1.0
    return precision, needles_hit / needles_total if needles_total else 0.0, clean_alarms


def main(variants, repeat):
    llm_needed = {v.split("+")[0] for v in variants if v != "det"}
    results = {}  # llm variant -> list of (case, flags, seconds, error)

    def job(args):
        v, case = args
        err = None
        for attempt in range(6):  # the free NIM tier 429s under load; back off, don't score it
            try:
                flags, secs = _llm(case, strict=v.startswith("strict"), think=v.endswith("think"))
                return v, case, flags, secs, None
            except Exception as exc:
                err = f"{type(exc).__name__}: {str(exc)[:120]}"
                if "429" not in err:
                    break
                time.sleep(15 * (attempt + 1))
        return v, case, None, None, err

    work = [(v, c) for v in llm_needed for _ in range(repeat) for c in CASES]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for v, case, flags, secs, err in pool.map(job, work):
            results.setdefault(v, []).append((case, flags, secs, err))

    print(f"{'variant':<20}{'precision':>10}{'recall':>8}{'clean FA':>10}{'p50 s':>8}{'max s':>8}{'errors':>8}")
    for v in variants:
        if v == "det":
            runs, secs, errs = [(c, _det(c)) for c in CASES], [0.0], 0
        else:
            base = results[v.split("+")[0]]
            # Errored calls are reported, not scored (production raises on them).
            runs = [(c, f + (_det(c) if v.endswith("+det") else [])) for c, f, _, e in base if e is None]
            secs = [s for _, _, s, _ in base if s is not None] or [0.0]
            errs = sum(e is not None for *_, e in base)
        # "full" = résumé-sized drafts (6 bullets + cover letter), where padding hides.
        for label, subset in ((v, runs), ("  full-size only", [r for r in runs if r[0]["name"].startswith("full")])):
            p, r, fa = score(subset)
            clean_n = sum(not c["unsupported"] for c, _ in subset)
            print(f"{label:<20}{p:>10.2f}{r:>8.2f}{f'{fa}/{clean_n}':>10}{statistics.median(secs):>8.1f}{max(secs):>8.1f}{errs:>8}")
    if "--verbose" in sys.argv:
        for v, rows in results.items():
            for c, f, s, e in rows:
                print(f"[{v}] {c['name']}: {e or f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    repeat = int(args[args.index("--repeat") + 1]) if "--repeat" in args else 1
    names = [a for a in args if not a.startswith("--") and not a.isdigit()] or ["base"]
    main(names, repeat)
