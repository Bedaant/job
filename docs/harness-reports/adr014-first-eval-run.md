# ADR-014 eval: the first completed run, and what it measured

**Date:** 2026-10-04 · 30 golden rows, NIM (`nemotron-3-super-120b-a12b`), `-j 1 --no-cache`,
8m48s · raw output `eval/results-run.json` (NOT committed — `eval/results.json` was already gitignored, so eval output follows that convention; regenerate with §5)

**This is the first time ADR-014's harness has completed a run since it was built.** Three
separate things had to be fixed to get here, and the headline number promptfoo prints is
misleading — read §3, not §1.

---

## 1. The headline number is not a quality result

```
Results: 0 passed, ✗ 30 failed, 0 errors (0%)
```

**Ignore it.** promptfoo fails a row if *any* assertion fails, and each row carries two:

| Gate | Outcome | Usable? |
|---|---|---|
| `truth_check.py` (python, hard gate, ADR-006) | **1 pass / 29 fail** | **yes — this is the measurement** |
| `llm-rubric` (soft gate, per-row `__expected`) | 30 fail: 16 "No output", 4 "Could not extract JSON from llm-rubric response", rest substantive | **no — the grader is broken, see §4** |

Because the rubric fails on every row for grader reasons, the overall pass rate is 0% no matter
how good the tailoring is. **The per-assertion numbers are the only honest read**, and they have
to be pulled out of `results-run.json`; the CLI summary cannot express this.

## 2. Three blockers had to be cleared before any of this ran

1. **The golden facts had no `id`.** `engine.py`'s path check is
   `llm_provider == "nvidia_smoke" or not known_fact_ids`, and `known_fact_ids` comes from the
   facts' ids — so all 30 rows silently ran the *unvalidated smoke path*, which has no
   `TailoredDraft` validation and no `source_fact_ids`. Fixed by adding ids (158 across 30 rows).
2. **promptfoo spawned the provider with the system Python.** `import instructor` inside
   `tailoring/engine.py` failed, the worker crash-looped 3× and the run stalled with no useful
   error — a 20-minute "hang" that looked like slow LLM calls. Fixed with
   `config.pythonExecutable` in `promptfooconfig.yaml`.
3. **The rubric had no grading model.** promptfoo defaults to OpenAI and this project has no
   OpenAI key. Pointing it at NIM did not work either (§4).

## 3. What the run actually measured

### Pass 1 (drafting) is cleanly grounded

**107 bullets across 30 rows, every one citing a real fact id. Zero ungrounded bullets.** The
`TailoredDraft` validation (`source_fact_ids` `min_length=1`, each id checked against the KB for
that call) is doing exactly its job, and the citation markers that leaked into bullet text on the
smoke path are gone.

> ## ⚠ CORRECTION (2026-10-04, same day) — this section named the wrong cause
>
> The text below says every failure comes from `deterministic_unsupported`, "pass 2's model-free
> half". **That is wrong.** I inferred it from the `[not in facts: …]` suffix, not realising that
> **both halves of pass 2 format their flags identically** (`engine.py` — `audit.unsupported`
> and `deterministic_unsupported` build the same string).
>
> Measured properly by calling the two halves separately on 5 rows:
>
> | half | flags |
> |---|---|
> | `deterministic_unsupported` (model-free) | **0** |
> | model checker (`STRICT_CHECK_SYSTEM`) | **31** |
>
> **The deterministic half is clean. The model checker produces 100% of the flags.**
>
> And it is not misbehaving — `STRICT_CHECK_SYSTEM` *explicitly* tells it to flag "added outcomes
> or purposes", "scope or scale", "domains, tools, numbers, **titles**, durations and **praise
> adjectives**". So it is working exactly as specified when it flags
> `"Senior Backend Engineer with expertise in Python, FastAPI…"` or `"Proven ability to design
> high-performance backend systems"`.
>
> **The real finding is a specification conflict between the two passes.** Pass 1 is asked for
> "a 2-sentence professional summary" and a cover letter — prose that inherently carries titles,
> scope and evaluative framing — while pass 2 is instructed to flag precisely those. The gate is
> not too strict by accident; the two prompts disagree about what a résumé sentence may contain.
>
> **Option (a) from §3 has since been measured and eliminated.** Adding an explicit facts-only
> instruction for the summary and cover letter changed nothing: **10/10 rows flagged before, 10/10
> after** (~5.5 flags/row both arms), with mean summary length 200 → 206 chars. A one-line prompt
> constraint does not move it.
>
> Revised options, with the diagnosis corrected:
> 1. **Narrow `STRICT_CHECK_SYSTEM`** so titles/praise/scope framing are not claims — but those
>    are real fabrication vectors ("Senior" when untrue, "enterprise" scale).
> 2. **Make the model half advisory and the deterministic half the hard gate** — the deterministic
>    half had zero false positives here and is precise about the fabrication that matters (unlisted
>    tools and numbers). Cost: it cannot see invented outcomes in plain words, which its own
>    docstring says it leaves to the model checker.
> 3. **Rewrite pass 1's summary/cover-letter spec** to a form that survives pass 2 — stronger than
>    the one-line attempt above.
> 4. **Keep as-is** and accept that almost nothing sends.
>
> Everything below is left as originally written, with the cause corrected here rather than
> silently edited, because the merged version was already presented and acted on.

### Pass 2 (truth-check) flags 29 of 30 — on the summary and cover letter, not the bullets

Every failure comes from `deterministic_unsupported`, pass 2's model-free half, which flags any
**technology name or number** in the draft that no fact contains. Representative flags:

```
'Staff Engineer with expertise in building and scaling real-time event pipelines using Kafka and Py…'
'Backend engineer with deep experience in PostgreSQL performance tuning and query optimization. [not in facts: …]'
'I am eager to bring this technical foundation to Nimbus Cloud to support your core Python/FastAPI …'
```

The bullets cite facts properly; the **summary and cover-letter prose generalise past the facts**,
naming tools and numbers the KB does not contain. That is exactly the fabrication class ADR-006
exists to catch, so the gate is arguably working — but it fires on nearly every row.

### Why that matters more than it looks

`main.py:161` filters the ready/work queue to applications with **no**
`flagged_unsupported_claims`. Flagged means **not sent**.

> **So on this golden set, ~97% of applications would never be sent — while every bullet is
> correctly grounded.**

This is the single most useful thing the harness has produced, and it was invisible before today.

**It is a decision, not a bug to patch quietly.** The options are genuinely different products:

| Option | Effect | Risk |
|---|---|---|
| Constrain the summary/cover letter to facts-only language | Keeps the strict gate; prose gets drier | May read as stilted |
| Scope the hard gate to bullets; treat summary flags as warnings | Applications flow | Weakens ADR-006 where prose is least verifiable |
| Keep as-is | Maximum safety | The product sends almost nothing |

Left to the owner. ADR-006/009 are deliberately strict rails and this is exactly their trade-off
surfacing with a number on it for the first time.

## 4. The rubric grader: NIM is not a drop-in

Configuring `defaultTest.options.provider` to NIM's OpenAI-compatible endpoint (`apiBaseUrl` +
`apiKeyEnvar`, both confirmed by reading promptfoo 0.120.19's own bundle) **did not work**:

- 16 rows: `No output`
- 4 rows: `Could not extract JSON from llm-rubric response`
- a few returned substantive judgements, so it is not a pure auth/plumbing failure

`nemotron-3-super` does not reliably return the JSON shape `llm-rubric` parses. **The grader
config is therefore removed rather than left in place**: a configured-but-broken grader fails
every row for the wrong reason and masks the gate that works — the same "red by artifact" problem
as a green-by-workaround pipeline.

There was also a second-order problem with it even when it answered: **the grader and the graded
model were the same model**, and a model is a lenient judge of its own output. A real soft gate
needs an independent, stronger grader — which needs a key this project does not have.

## 5. How to re-run

```
cd eval
export NVIDIA_API_KEY=...            # from apps/api/.env
export PROMPTFOO_DISABLE_TELEMETRY=1 CI=true
npx promptfoo eval -j 1 --no-cache --no-progress-bar -o results-run.json
```

- `-j 1` deliberately: NIM's free tier, and the run is ~9 minutes serialized.
- `CI=true` matters — without it promptfoo can sit on an interactive prompt with no stdin.
- **Read the per-assertion results out of the JSON**, not the CLI pass rate (§1).
- `config.pythonExecutable` is pinned in `promptfooconfig.yaml`; without it the provider cannot
  import and the run stalls.
