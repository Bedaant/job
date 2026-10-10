# Round 7: product-grade direction, one palette chosen

Pictures only. Production styling is unchanged.

**Limitation:** linear.app and uidiscovery.com are blocked by this environment's network policy, so neither site was opened. The direction comes from the research report (`reports/Linear and SaaS design lessons.md`) and from known patterns at Linear, Vercel, Stripe, Notion and Mercury.

## What changed from round 6, and why
- **The serif is gone.** Round 6's editorial serif read as "blog". Top product companies use one strong grotesk set tight at large sizes.
- **The product is the hero.** A real, dense app screen sits on a solid brand-colour panel, the way Linear, Vercel and Mercury lead with the product rather than illustrations.
- **Neutral by default, colour only where it means something:**
  - the brand panel
  - the selected row
  - "Needs you"
  - fact chips
  - the logo dot
- **No effects:**
  - no gradients, glows or grain
  - hairline borders and one shadow
  - keyboard hints (`/`, `⏎`) on desktop
  - thumb-first bottom tabs and a sticky Approve bar on phones

## Typography: Inter (Display optical size for headlines, Text for UI)
`type-candidates.png` compares 12 faces on the same hero and job card: Inter, Inter Tight, Geist, Onest, Instrument Sans, Manrope, Schibsted, Mona Sans, Hanken, Host Grotesk, Funnel Display and Plus Jakarta.

Inter wins for four reasons:
- It is the sharpest at both 76px and 13px.
- It is the font Linear and Figma use.
- It is already the logo's wordmark font.
- It has tabular numbers.

Supporting faces: Geist Mono for IDs and fact tags, and Noto Sans Devanagari for Hindi later.

**Scale:**

| Use | Size | Weight | Letter-spacing |
|---|---|---|---|
| Display | 76 (desktop) / 44 (phone) | 620 | −4.5% |
| Section heading | 46 | — | −3.5% |
| Body | 15–19 | — | — |
| UI | 13.5 | — | — |

## Colour: six explored, one chosen
`palettes.png` shows the same layout in six palettes: Cobalt, Forest, Vermilion, Ink + marigold, Wine and Midnight.

**Chosen: Ink + marigold.**

| Token | Hex |
|---|---|
| Ink | `#16130E` |
| Paper | `#FBF9F4` |
| Marigold | `#F2A51A` |
| Marigold tint | `#FDF1D6` |
| Text on tint | `#7A4B00` |
| Success | `#157A46` |
| Error | `#B42318` |

Why this one:
- **It stands out in its category.** LinkedIn, Naukri and Indeed are all blue, and ink + marigold is unlike any of them.
- **It means something in India.** Marigold stands for celebration and new beginnings, and it already appears as the dot in the logo.
- **It looks premium.** Ink buttons are what Linear, Vercel and Notion use.
- **Marigold has one job: "your move".** It marks things that need you, and it is never used for text or for errors.

Runner-up: Forest + lime, which is calm and money-like. Its weakness is that the green primary sits close to the green "Ready" status.

**Contrast:**
- All text pairs pass WCAG AA: ink on paper 17.6, muted text 5.6, text on tint 6.6, success 4.75, error 5.75, ink on marigold 9.0.
- Borders are decorative only (1.5:1).

**Logo:** in this direction the symbol is ink and the dot is marigold. The logo guidelines still say indigo, so changing it needs your approval.

## Files
| File | What it shows |
|---|---|
| `shots/final-landing.png` | Full landing page in the chosen palette |
| `shots/final-app.png` | Desktop app (Today) |
| `shots/final-phones.png` | Phone landing, Today and Review |
| `palettes.png` | All six palettes compared |
| `shots/hero-*.png`, `shots/band-*.png` | Each palette's hero and trust section |
| `type-candidates.png` | The 12 typefaces compared |
| `p-*.html` | Source pages; open in a browser |

Prices on the landing page (₹0 / ₹299 / ₹799) are placeholders, not a pricing decision. Nothing here has been tested with users or on a budget Android phone.

## Landing v2 (after reviewing the three reference mock-ups)
`landing-v2.html` and `shots/v2-*.png`. It keeps what worked in the references:
- a left-aligned headline with the product on the right
- an "Upload your resume" button instead of a generic "Start free"
- a before/after resume
- cards for each career stage
- a closing call-to-action band

It removes what would hurt:
- logo walls of employers (Google, Microsoft, Amazon) that imply endorsement
- made-up stats and testimonials
- rainbow gradients and 3D icons
- decorative photos that are heavy on budget phones

The before/after section now also shows *proof*: fact tags on each line, and one line removed because it isn't backed by the user's facts.
