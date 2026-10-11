# Engineering principles

Written 2026-10-11. These are rules of thumb used as a checklist, not features to build. Each is tied to something already in this repo. **Nothing here has been implemented**; the metrics at the end are a proposal.

## The checklist

| Law | What it means here | Do this |
|---|---|---|
| **Gall's Law**: a complex system that works evolved from a simple one that worked | The core loop (find → tailor → truth-check → approve → send) has run for one user. Do not add agents, cloud browsers, new markets or imports until it works for ~20 non-owner users. | Gate new scope on the loop being proven (see `docs/council/2026-10-10-council-report.md`, report D). |
| **Little's Law**: items in system = arrival rate × time each takes | `HANDOFF-100-USERS.md`: 1,000 tailorings/day at ~60 s is ~0.7 busy workers on average; if most arrive in a few hours, plan for several at peak (illustrative arithmetic, not measured). | Size workers from measured arrival rate and job time, not guesses. |
| **Amdahl's Law**: the serial part caps the speedup | If the LLM rate limit is the serial part, more workers do nothing. `sweep_campaigns_task` (`workers/jobs.py:832`) is also one serial job. | Find the real bottleneck before adding replicas. |
| **Universal Scalability Law**: contention makes extra parallelism slower | Redis Cloud free tier caps at 30 clients (`GAPS.md` 5.3); Neon limits connections. | Use pooled connections; load-test before adding workers. |
| **Murphy's Law** | A row stuck in `submitting` is never recovered by anything (`main.py`, claim/close-submission). | Add a sweeper for stale `submitting` rows and a kill switch. |
| **Fallacies of distributed computing**: the network is reliable, latency is zero | Tailoring calls use `retries=0` (`tailoring/engine.py:181`); Neon latency is high from a laptop. | Explicit timeouts; retry only safe calls; keep every effect idempotent. |
| **CAP Theorem** | Sending is irreversible, so correctness beats availability. | Keep the at-most-once claim in `claim_submission` (`main.py:333`). |
| **Hyrum's Law**: anything observable gets depended on | The extension ↔ API contract and employers' form layouts will be relied on in unplanned ways. | Version the extension–API contract. |
| **Zipf's / Pareto's laws** | A few application systems and a few question wordings cover most applications. | Cache field→answer mappings; build adapters for the top systems first. |
| **Wirth's Law**: software slows faster than hardware speeds up | Users are on budget Android phones. | Set page-weight and JavaScript budgets. |
| **Parkinson's / Brooks's laws** | Work fills the time given; adding people to a late project delays it. | Timebox design rounds; keep scope small. |
| **Conway's Law** | One founder → one well-organised monolith. | Do not split into microservices. |

## Not applicable yet
- **Metcalfe's / Reed's laws**: no network effects yet. The closest is a shared library of application-form layouts that improves as more users apply.
- **Gustafson's / Zawinski's laws**: not needed at this scale.
- **Postel's law**: be liberal when parsing résumés, strict when validating requests or sending.
- **Leaky abstractions**: remember it when choosing any agent or browser framework.

## Proposed metrics (not implemented)
`/health` already reports queue depth and failed counts per queue (`observability.py`). It does not report:
1. **Age of the oldest queued job**, per queue. This is the first signal of a Little's Law problem.
2. **Count of `submitting` rows older than N minutes.**
3. **LLM calls per minute vs the provider limit**, and 429 count.
4. **p50/p95 tailoring time** and cost per tailoring (cost is currently a guess in `engine.py`).
5. **Redis client count** against the 30 cap.

Approve these separately before any code is written.
