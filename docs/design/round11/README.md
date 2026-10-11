# Round 11: job-portal landing page, studied from the Dribbble references

Pictures and prototype only. Production styling is unchanged. Open `landing.html` in a browser; add `?t=sunrise` for the warm colourway (default `?t=sky`).

## What I studied (seven Dribbble shots) and what I did with each

| Reference | What works | What to avoid | Used here as |
|---|---|---|---|
| **TalentConnect** (lavender hero) | Centred headline with one accent word, big search box, category icons, floating pill nav with Login/Signup | Stock-icon carousel, fake brand logos | Floating pill nav; accent word in a serif italic; a prompt-style box with one clear action |
| **Hirablee** (sky, fanned colour cards) | Fanned pastel job cards with salary, behind the main product card | Emoji inside the headline, floating social icons that imply partnerships | Fanned example job cards (₹ LPA, tags, "Review application") behind the central resume card |
| **Lowker** (AI agent) | Chat preview with suggested prompts around it; serif headline | Tiny text, vague claims | "Ask Maggie" section with real prompts and honest answers |
| **Collective OS** | Floating callouts on a product screenshot | Blurred, hard-to-read dashboard | Four floating callouts: 14 of 14 lines backed, nothing sent until you approve, receipt |
| **Popular searches** | Pill chips, one selected | Lorem ipsum | Role chips under the prompt box |
| **Featured job circulars** | Job rows with logo, tags, pay | Dense small text | "Jobs that actually fit you" cards with skills match |
| **Budiarti R.** (benefits vs drawbacks) | Two-column comparison | Flat clip-art illustrations | "Typical auto-apply" vs "ApplyScout" |

## What I kept from our own work
- The fact-link idea: every resume line shows the fact that backs it, and an unbacked line is struck out and removed.
- No invented logos, stats or testimonials. The only company names are labelled "Example data".
- Prices are placeholders.

## Choices
- Type: Plus Jakarta Sans (friendly, readable on small screens) with Source Serif 4 italic only for accent words; Noto Sans Devanagari for the Hindi switcher.
- Colourways: **Sky** (cobalt on pale blue/lavender) and **Sunrise** (orange on cream and blush). Both use a near-black primary button.
- Phone: nav collapses to the logo and one button; the prompt box stacks; chips scroll sideways; the fanned cards are hidden.

## Files
`landing.html`, `r11.py` (generator), `fonts/`, `shots/` (sky/sunrise hero at 2x, full desktop, phone strip).

## Known gaps
- The fanned cards are hidden on phones, so the phone hero is simpler.
- Nothing is animated yet (only a blinking caret).
- Not tested on a real Android phone or with users.
- "Every line true" and "nothing sent without you" still depend on the send-safety gate being built.
