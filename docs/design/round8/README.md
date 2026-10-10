# Round 8: tech direction (Vercel / Linear style)

Pictures only. Production styling is unchanged.

**Why round 7 still looked like WordPress:** the structure was a stack of centred sections (label, headline, paragraph, three rounded cards with shadows) on cream paper, with large flat yellow panels. That reads as a blog or a retail site, whatever the colour.

## What makes this one read as a tech company
- **A 1px grid frame** with "+" marks where lines cross. Content sits in bordered cells, not floating cards.
- **A black-and-white base.** Colour appears only with a meaning:
  - green = backed by a fact
  - amber = needs you
  - red = removed or blocked
  - blue = link
  - marigold only in the logo dot
- **Geist and Geist Mono** (Vercel's open-source typefaces): Geist for headings and text, Geist Mono for data, times, IDs and labels.
- **Product properties instead of slogans:** 6 sources, 100% of lines linked to a fact, 0 sent without approval, ₹0 to start.
- **A visible pipeline** (Find → Match → Tailor + verify → Approve → Send) with an example activity log.
- **A feature grid built from real interface pieces:** the truth check, approving on a phone, the fit explanation, a receipt, the scam guard.
- **A comparison with typical AI auto-apply tools.**
- **The phone version shows the phone app**, not a shrunken desktop screenshot.

## Files
| File | What it is |
|---|---|
| `landing-dark.html` | Linear-style dark version |
| `landing-light.html` | Vercel-style light version |
| `shots/*-hero.png` | Hero section of each version |
| `shots/*-full.png` | Full page of each version |
| `shots/*-mobile-strip.png` | Phone version of each, split into a strip |

## Before this can go live
- The claims "100% of lines linked to a fact" and "0 sent without your approval" are **not true in the code yet**. The council audit found that the truth-check gate is not enforced on the send paths. These lines can only be published after the `can_send()` gate ships.
- Prices are placeholders.
- "Hourly" and "6 sources" must match production configuration.
