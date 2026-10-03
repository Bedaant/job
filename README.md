# Apply Scout

**Upload your resume once. The app finds matching jobs, tailors your resume to each job's ATS, applies from your own browser, then emails people inside the company to ask for a referral. The goal is to get you interviews, not just applications.**

Apply Scout (the browser extension is called **ApplyScout**) is a personal project, built to run for the owner and about 5–7 friends. It is not a commercial product yet. This README is the blueprint: what the system does end to end, how the parts fit together, which repos and tools are used where and why, and what is built versus still to build.

> **Status in one line:** everything from resume upload through auto-apply is built and tested. The last step (referral outreach by email) is designed but **not built**. We make no promise of an interview. We aim to raise the chance of a reply, and we measure it.

---

## 1. The whole loop

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │ 1 Resume │──▶│ 2 Facts  │──▶│3 Campaign│──▶│ 4 Find   │──▶│ 5 Match  │
 │  upload  │   │ review   │   │ (roles,  │   │  jobs    │   │ & explain│
 └──────────┘   └──────────┘   │ places)  │   └──────────┘   └────┬─────┘
                               └──────────┘                       │
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
 │ 9 Learn  │◀──│ 8 Refer- │◀──│ 7 Apply  │◀──│ 6 Tailor │◀───────┘
 │ & track  │   │ ral email│   │ in your  │   │ to the   │
 │          │   │ (PLANNED)│   │ browser  │   │ job's ATS│
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

| # | Stage | What happens | Built? |
|---|---|---|---|
| 1 | **Resume upload** | You upload a PDF or DOCX. It is parsed. | ✅ |
| 2 | **Facts review** | The resume becomes 25–40 small, checkable claims (the **Facts KB**), such as *"Cut checkout API p99 latency from 1.4s to 180ms, Payments team, Q2 2025"*. You edit them. Everything written later can only use facts you confirmed. | ✅ |
| 3 | **Campaign** | You say what you want: job titles, locations, sources, caps, and whether each application waits for your review (assisted) or goes out on its own. | ✅ |
| 4 | **Find jobs** | Scheduled workers pull jobs from many public sources into one deduplicated table. | ✅ |
| 5 | **Match** | Every job is scored against your whole profile, not only the title. Each match says why: "7 of 9 required skills matched, missing Kubernetes". | ✅ |
| 6 | **Tailor to the ATS** | For each job the app rewrites your resume to the job's own wording, then truth-checks it. | ✅ built, quality not yet measured |
| 7 | **Apply** | The extension fills and submits the employer's form inside your own browser. | ✅ built, first real submission still to do |
| 8 | **Referral email** | After you apply, the app finds a suitable person at the company, verifies an email, writes a short note and sends it from your Gmail. | ❌ planned |
| 9 | **Track and learn** | A Kanban tracker, a daily digest, and reply and interview rates. | ✅ tracker and digest, 🟡 analytics |

### Stage 5 in more detail: how matching works
- **Semantic match:** your facts are compared to the job description with embeddings.
- **Skill coverage:** which required skills you have and which you lack (the keyword gap).
- **Hard filters:** location and remote policy, seniority, visa or work-authorisation text, and remote jobs that are limited to another country.
- **Near-duplicate removal:** the same role listed on three boards appears once.

### Stage 6 in more detail: tailoring to the ATS
Before each application the app reads the job description and rewrites your resume to match what that employer's ATS and recruiter look for:
- **Title alignment:** if you are a *Product Manager* and the job says *Technical Product Manager*, the app uses the job's wording where your real experience supports it.
- **Skill alignment:** it pulls the skills the job asks for and puts the ones you actually have into your skills section and bullets, in the job's wording.
- **ATS-safe layout:** single column, standard section names, no tables or text boxes.

Three steps do the work:
1. **Tailor:** reorder and reword your real facts for this job.
2. **Truth-check:** a second, independent model call checks the draft against your Facts KB. A claim your facts don't support blocks the application. So "Technical Product Manager" appears only when your facts back it up, and a skill you lack is flagged as a gap and never added.
3. **Voice:** strips the usual AI filler so the text sounds like you.

The result is an ATS-safe DOCX. The app re-parses its own output to confirm the content survives a parser.

### Stage 7 in more detail: auto-apply
- A server-side **planner** (Stagehand) studies each job's form once, read-only, and saves a fill plan. A network guard blocks every non-GET request, and the plan holds no personal data.
- The **ApplyScout extension** runs the plan in your browser, with your IP and your logins, using your real data. It checks each field after writing it. The server never submits an application.
- **Assisted mode:** the extension fills, you press Send. **Automatic mode:** it sends within your daily cap.
- It follows multi-page forms (Workday-style "Next" flows). At a sign-in wall it stops and tells you, and it never types a password.
- It never answers EEO or demographic questions. It never guesses essay questions or "How did you hear about us?". Those come from your saved answers, or it asks you.
- An application counts as *submitted* only when the employer's confirmation page says so.

### Stage 8 in more detail: referral email (planned)
Once an application is submitted:

1. **Pick who to contact.** At the same company, find 1–3 people who can help. If you applied as a Developer I, that means a Developer II or III, an Engineering Manager, or the hiring manager.
2. **Get an email.** Take a candidate address from a public source, a pattern guess (`first.last@company.com`), or a finder service.
3. **Verify it** (MX and SMTP checks) and send only when the result is safe.
4. **Write it.** At most 120 words: *"I applied for this role and I'm very interested. Here is my profile."* Every claim comes from your Facts KB.
5. **Send from your own Gmail** through OAuth, paced and capped.
6. **Watch.** A bounce, a reply or an opt-out stops all further mail to that person. A reply notifies you.

---

## 2. System architecture

```
                  ┌───────────────────────────────┐
  You ──────────▶ │ Web app (Next.js)             │   onboarding, facts, campaign,
                  │ dashboard                     │   matches, review, tracker
                  └──────────────┬────────────────┘
                                 │ REST + live events (SSE)
 ┌──────────────┐   ┌────────────▼────────────────┐        ┌─────────────────────────┐
 │ ApplyScout   │◀─▶│ API (FastAPI)               │◀──────▶│ PostgreSQL + pgvector   │
 │ Chrome ext.  │   │ auth, tenancy, campaigns,   │        │ (Neon). Row-level       │
 │ fills forms  │   │ matching, tailoring, plans  │        │ security per user       │
 └──────┬───────┘   └────────────┬────────────────┘        └─────────────────────────┘
        │                        │ jobs
        │              ┌─────────▼────────────┐   ┌──────────────────────────────────┐
        │              │ Redis + RQ workers   │──▶│ Job sources: Greenhouse, Lever,  │
        │              │ + scheduler          │   │ Ashby, Remotive, Reed, 6 feeds   │
        │              │ discover · embed ·   │   └──────────────────────────────────┘
        │              │ prepare · plan forms │   ┌──────────────────────────────────┐
        │              │ · (outreach, later)  │──▶│ AI: Claude (tailor + truth-check)│
        │              └─────────┬────────────┘   │ Voyage (embeddings)              │
        │                        │                │ Stagehand planner (form reading) │
        │              ┌─────────▼────────────┐   └──────────────────────────────────┘
        │              │ Planned: outreach    │   ┌──────────────────────────────────┐
