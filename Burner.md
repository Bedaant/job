# Apply Scout — cash burn

Checked 18 October 2026. Companion to `Arch.md`, which covers the repository, the product workflow, and what still has to be built. No product code was changed to produce this.

Rupee figures use the FBIL rate published on the RBI site for 16 October 2026: **₹95.0194 per USD** ([RBI](https://www.rbi.org.in/)). GST, TDS, and card foreign-exchange fees are not in these totals.

The monthly operating bill, at 8 jobs per active user, is about **$99, $330, $2,843, and $13,207** for the four scenarios. Roughly 85% of that is Apify contact search. Resume generation is about **$0.0013** each.

The model endpoint the code calls is a free NVIDIA prototype that **stops being supported on 19 October 2026**. The figures below replace it with the same model on DeepInfra.

## Provider prices

**LLM.** DeepInfra, Nemotron 3 Super, standard tier: **$0.085 / 1M input and $0.40 / 1M output** ([DeepInfra](https://deepinfra.com/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B)). Flex is 0.8× and fits background tailoring. The free NVIDIA endpoint is https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b. A third-party listing of $0.10 / $0.50 was not used.

**Embeddings.** `voyage-3-lite` is **$0.02 / 1M tokens, no free tokens** ([Voyage pricing](https://docs.voyageai.com/docs/pricing)). Newer `voyage-4-lite` is the same price with 200 million free tokens, but it is a different dimension than the 512-d column already migrated. For pasted jobs, skip embeddings. They are not in the totals below.

**Contacts.** The wired actor charges **$0.10 per search page plus $0.01 per profile in Full + email mode**, and email is not guaranteed ([Apify actor](https://apify.com/harvestapi/linkedin-profile-search)). Free Apify allows 10 runs and $5 of usage. Paid plans are Starter $19, Scale $199, Business $999, each including that much prepaid usage, with caps of $100, $1,000, and $5,000 ([Apify pricing](https://apify.com/pricing)). GitHub stays free and is the right first source for engineers. Hunter finds an email from a name and domain. It does not answer “who at this company hires for this role.” Hunter Data Platform is about **$50 / 1,000 searches and $11 / 1,000 verifications**, annual, minimum 1,000 ([Hunter data plans](https://help.hunter.io/en/articles/9920427-data-platform-plans-for-api-users)).

**Verification.** ZeroBounce pay-as-you-go is **$39 / 2,000 ($0.0195), $69 / 5,000 ($0.0138), $129 / 10,000 ($0.0129), $649 / 100,000 ($0.00649), $1,299 / 250,000 ($0.005196)**. Unknown results are not charged. A free account includes 100 credits a month ([ZeroBounce](https://www.zerobounce.net/docs/frequently-asked-questions/billing-and-payments/how-is-pricing-determined-for-email-verification)). This is a deliverability opinion, not proof of ownership.

**Documents.** python-docx is already in the repo. A paid PDF API is unnecessary.

**Hosting.** Neon Launch is **$0.106 per CU-hour** and **$0.35 per GB-month**, no monthly minimum. Free is 100 CU-hours and 1 GB per project ([Neon](https://neon.com/pricing)). Redis Cloud free is **30 MB and 30 connections**. Paid Essentials starts at **$0.007/hour, about $5/month for 250 MB** ([Redis](https://redis.io/pricing/)). The app process is one small VM. This model uses **$8 / $24 / $48** across the three larger bands. Those VM figures are estimates. No SKU was selected.

**Sending.** Personal Gmail is about **500 messages/day**. Workspace is about **2,000/day**, with a **25 MB** send attachment limit ([Gmail consumer](https://support.google.com/mail/answer/22839), [Workspace](https://support.google.com/a/answer/166852)). The product cap of 10 outreach emails a day is far under that. Marginal cost of a send from the user’s own account is **$0**.

**Payments.** Nothing is integrated. Stripe India list price is **2% for domestic Mastercard and Visa**, and the global UPI page lists **2%** ([Stripe India](https://stripe.com/in/pricing), [UPI](https://stripe.com/pricing/local-payment-methods)). UPI AutoPay recurring is capped at ₹15,000.

## Assumptions

**Baseline activity per monthly active user, assumed, not measured:** 8 job descriptions, 1.2 resume generations, 2 people looked up, 1 address actually returned and verified, 2 emails drafted with a truth-check each, 1 email sent. Low is 4 jobs. High is 20. Retries are mostly absorbed by the existing cache and the three-attempt prep cap, so they are not given a separate multiplier.

**Token assumption per job:** tailor 4,500 in / 1,200 out, truth-check 3,000 / 400, times 1.2 generations; two drafts at 2,500 / 400 and two draft checks at 2,000 / 300; 30% of jobs need a 2,000 / 600 extraction. That is **18,600 input and 3,500 output tokens**.

```text
LLM   = 18600 × 0.085/1e6 + 3500 × 0.40/1e6 = $0.002981
Apify = 0.10 + 0.01 × 2 = $0.12
Verify cash = smallest ZeroBounce pack that covers (jobs × 1 check)
```

**Fixed** is modelled, not metered:

| Band | Fixed / month | What is inside |
|---|---:|---|
| Early | $35 | Neon ~$20, Redis $5, VM $8, domain ~$1.50 |
| Small launch | $45 | Same shape, slightly more database |
| Growing | $125 | Larger Neon, Redis, and VM ($24) |
| Larger | $260 | Larger Neon, Redis, and VM ($48) |

## Monthly totals

| Scenario | Registered / active | Jobs, low / base / high | Low | Baseline | High | Baseline INR |
|---|---:|---|---:|---:|---:|---:|
| Early MVP | 100 / 25 | 100 / 200 / 500 | $86 | $99 | $135 | ₹9,400 |
| Small launch | 1,000 / 250 | 1,000 / 2,000 / 5,000 | $207 | $330 | $729 | ₹31,400 |
| Growing | 10,000 / 2,500 | 10,000 / 20,000 / 50,000 | $1,484 | $2,843 | $6,919 | ₹2,70,000 |
| Larger | 50,000 / 12,500 | 50,000 / 100,000 / 250,000 | $7,054 | $13,207 | $32,304 | ₹12,55,000 |

Baseline composition:

| Scenario | Apify | ZeroBounce pack | LLM | Fixed | Total |
|---|---:|---:|---:|---:|---:|
| Early MVP | $24 | $39 | $1 | $35 | $99 |
| Small launch | $240 | $39 | $6 | $45 | $330 |
| Growing | $2,400 | $258 | $60 | $125 | $2,843 |
| Larger | $12,000 | $649 | $298 | $260 | $13,207 |

Free tiers die immediately in production. Neon’s 100 CU-hours is about two weeks of a 0.25 CU database that does not sleep. Apify free is 10 runs. ZeroBounce free is 100 checks, then the $39 minimum. Voyage has no free tokens on the model already in the schema. NVIDIA’s free endpoint ends 19 October 2026.

At $0.12 per job, Apify’s published caps cover about **830 jobs** (Starter), **8,300** (Scale), and **41,700** (Business). The growing high band and every larger-product band are past $5,000. Those rows use the public per-event price. The contract price above the cap is unknown.

**Development cost, separate from the burn above.** The core product is built. The remaining product work is intake, PDF, per-user mail credentials, a verifier, deploy, and billing. That is on the order of four to eight weeks for someone who already knows this repo. Founder time is not in the monthly totals. A contracted build at a chosen rate is `weeks × rate`, not an operating cost.

The shared job crawler is an optional extra. Embedding 10,000 new descriptions a month at about 1,500 tokens is about **$0.30** on Voyage. Crawler traffic and a larger database dwarf that. Do not start it for the pasted-description product.

If contact lookup is off, monthly burn at these scales falls to roughly the fixed **$35–$260** plus a few dollars of LLM.

## Unit economics

At the 2,000-pack verification rate:

| Unit | Cost | Formula |
|---|---:|---|
| Processed job | $0.143 | $0.0030 LLM + $0.12 Apify + $0.0195 verify |
| Tailored resume | $0.0013 | (7,500 × $0.085 + 1,600 × $0.40) / 1e6 |
| Discovered contact | $0.060 | $0.12 / 2 profiles |
| Verified address | $0.0195, falling to $0.0032 at 1M | one ZeroBounce credit |
| Drafted email | $0.0008 | draft plus truth-check |
| Sent email | $0 | user’s Gmail or SMTP |
| Active user / month | $1.14 variable | 8 × $0.143, before fixed cost |

Fixed cost per active user falls from about $1.40 at 25 users to about $0.02 at 12,500, as long as Apify remains available at the list rate.

## Monetization options

There is no billing code and no price in the current product. These are illustrations.

A resume-only plan is cheap to support. Eight jobs and one regeneration is about **$0.03** of model cost per active user. A **₹499/month** plan (~$5.25) has a gross margin near 99% on model cost, before the fixed ~$35 and Stripe’s 2%.

A plan that includes two contact lookups per job cannot be unlimited. Eight jobs at $0.12 is **$0.96** of Apify, so a **₹999/month** plan (~$10.51) still has roughly **80% gross margin** on variable cost at the baseline (`(10.51 − 1.14) / 10.51`), and about **78% after a 2% Stripe fee**. At the high band, 20 jobs cost about **$2.85** variable, and margin is still above 70%. A user who processes 100 jobs with lookups costs about **$14**, which is more than ₹999. Cap lookups, or sell them as credits at about **₹15–20 per lookup** against a $0.06 cost.

Do not sell unlimited contact search. The abuse case is the whole margin.

Gross margin is not profit. At 25 paying users on ₹999, revenue is about $263 and baseline cost is $99, before tax, refunds, and time. At 25 free users doing lookups, the operator pays the $99.

## Assumptions that move the bill

- 8 jobs per active user, two profiles per job, half of those profiles returning an address.
- DeepInfra standard pricing, ZeroBounce as the verifier.
- A single small VM whose exact price is estimated.
- Contact lookup on by default. Turning it off collapses the bill to hosting plus LLM.

## Sources checked 18 October 2026

- NVIDIA NIM model page: https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b
- DeepInfra Nemotron 3 Super: https://deepinfra.com/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B
- Voyage pricing: https://docs.voyageai.com/docs/pricing
- Apify actor: https://apify.com/harvestapi/linkedin-profile-search
- Apify plans: https://apify.com/pricing
- Hunter data plans: https://help.hunter.io/en/articles/9920427-data-platform-plans-for-api-users
- ZeroBounce credit pricing: https://www.zerobounce.net/docs/frequently-asked-questions/billing-and-payments/how-is-pricing-determined-for-email-verification
- Neon: https://neon.com/pricing
- Redis: https://redis.io/pricing/
- Gmail consumer limits: https://support.google.com/mail/answer/22839
- Workspace sending limits: https://support.google.com/a/answer/166852
- Stripe India: https://stripe.com/in/pricing
- Stripe UPI: https://stripe.com/pricing/local-payment-methods
- FBIL rate via RBI, 16 October 2026: https://www.rbi.org.in/
