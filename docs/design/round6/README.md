# Round 6: three design-system prototypes, compared fairly

Production styling is unchanged. These are standalone prototypes.

- `prototype.html?t=a`, `?t=b` and `?t=c` are one page with **identical markup and content**. Only the tokens differ.
- `compare-landing.png`, `compare-app.png`, `compare-forms-states-tokens.png` and `compare-mobile.png` show the three side by side.
- `shots/` holds every section per theme, desktop and phone, plus a focus-ring capture.
- `tokens.json` has the full token sets, `contrast.md` the measured contrast and `checks.json` the raw results of the automated checks.

## 1. Audit of the current app (baseline)

| Area | Finding | Evidence |
|---|---|---|
| Stack | Next.js 15, Tailwind 3, shadcn/ui on Radix, Lucide icons, Geist font | `apps/web/package.json`, `app/layout.tsx:7` |
| Colour | One blue accent (`--primary: 31 85 201`), calm neutrals, light and dark tokens, raw `emerald/amber/red/blue-500` classes in `ApplicationCard.tsx` and the Kibo status component | `styles/globals.css`, grep |
| Focus | Two focus treatments stack: a global `:focus-visible` 3px outline **and** each component's `ring-[3px] ring-ring/50` | `globals.css`, `components/ui/button.tsx:8`, `input.tsx:11` |
| Disabled | `disabled:opacity-50`, which usually drops text below 4.5:1 | `button.tsx`, `input.tsx` |
| Shape | Base radius 0.875rem plus `rounded-2xl` on most cards (53 uses); six radius values in use | grep |
| Type | 15px body, 12 text sizes including one-off pixel values | grep |
| Motion | A global `prefers-reduced-motion` rule exists (good) | `globals.css` |
| **Measured accessibility** | **0 axe violations** (WCAG 2 A/AA, 2.1 AA, best practice) on /today, /review, /applications, /campaign, /onboarding and /login, run against a mock API | `checks.json` → baseline |
| **Phone layout** | **No horizontal overflow at 390px on /today.** The overflow reported in round 3's audit came from my screenshot method, not the app | `checks.json` → `today_mobile_overflow` |

The current app is accessible and orderly. Its problem is that it **has no brand**: a generic blue, rounded cards everywhere, and no visual idea that says "truthful resumes".

## 2. What all three prototypes share

- **Same content and functionality:** landing page, Today dashboard, job card with match reasons, resume truth check, campaign form with validation, and loading, empty, error and undo states.
- **Lucide only:** one rendered stroke of 1.5px at every size (16, 18, 20, 24, 28), and always next to a word. The two icon-only controls (account menu, remove chip) carry an `aria-label`.
- **Native, accessible controls:**
  - real `<button>`, `<input>`, `<fieldset>`/`<legend>` and radio inputs
  - the error is linked with `aria-describedby` and marked `aria-invalid`
  - loading uses `aria-busy`; errors use `role="alert"`; the toast uses `role="status"`
  - there is a skip link
- **Removed generic effects:** no glows, decorative grids, gradients, grain or floating cards. Cards are used only for real objects (a job, a resume, a form). Lists are separated by rules, not boxes.
- **Truth-check indicators, one meaning each, never colour alone:**
  - *Backed*: check icon plus "Backed by your facts" plus fact chips F1, F2.
  - *Not added*: minus icon plus a warning tint: "Listed by the job, missing from your facts".
  - *Blocks sending*: x icon plus error text, with Remove line and Add as a fact actions, and a "Can't send yet" alert.
- **Interaction states:** hover, active, focus-visible (2px ring, 2px offset, token `--focus`), disabled (its own tokens rather than opacity), and invalid.
- **Reduced motion** removes all transitions. Only colour changes on hover, at 120ms.

## 3. The three systems

| Token family | A. Premium and trustworthy | B. Editorial and distinctive | C. Refined dark |
|---|---|---|---|
| Background, surface | Warm ivory `#FAF7F0`, white | Off-white `#F6F5F1`, white | Layered charcoal `#121211`, `#1A1A18`, `#222220` |
| Text, muted | Deep navy `#14213D`, `#46506A` | Near-black `#111111`, `#4F4D47` | Warm white `#F2EEE6`, `#B8B2A7` |
| Primary action | Navy `#14213D` | Cobalt `#1D4ED8` | Muted amber `#D9A84E` (dark label) |
| Accent and links | Restrained blue `#2C5AA8` | Cobalt; gold `#B8892D` for the brand dot and fact chips only | Amber `#F0CD8A` |
| Success, warning, error | Accessible green `#1D7447`; amber; red, each with tint and text tokens | Same roles, tuned | Light tints on dark |
| Display / body type | IBM Plex Sans 600 / IBM Plex Sans | **Source Serif 4** 600 / Geist | Geist / Geist |
| Radius (sm, md, lg) | 6, 8, 12 | 2, 4, 4 (sharp) | 6, 8, 10 |
| Elevation | One soft navy shadow | None: hairline rules and borders | Lighter surfaces plus a 1px top highlight |

Spacing is shared: a 4px base (4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56), 44px minimum targets, 52px large buttons.
The type scale is shared: display clamp 36–58, heading 26–34, title 20, body 16/1.55, small 14, extra small 13. Body lines are kept under about 65 characters.

## 4. Checks run (automated, headless Chromium via puppeteer)

| Check | A | B | C |
|---|---|---|---|
| axe, desktop 1440px (WCAG 2 A/AA, 2.1 AA, best practice) | 0 violations | 0 | 0 |
| axe, phone 390px | 0 | 0 | 0 |
| Keyboard: 14 Tab presses, every focused element shows a visible outline | yes | yes | yes |
| Horizontal overflow at 390px | none | none | none |
| `prefers-reduced-motion: reduce` turns transitions off | 0s | 0s | 0s |
| Contrast (15 pairs, `contrast.md`) | all pass | all pass | all pass |

**Fixed during the checks:**
- Theme A's subtle text was 4.48:1, just under 4.5, and was darkened.
- The summary panel was a nested `<aside>` landmark (an axe best-practice failure) and became a labelled region.

**Not done:**
- Testing with a screen reader by hand.
- Testing on a real budget Android phone in daylight.
- Any user testing.

Automated checks catch roughly a third to a half of accessibility issues. They don't prove usability.

## 5. Trade-offs

**A. Premium and trustworthy.**
- *Strengths:* the calmest and most legible. Status colours are clearly separated from the navy primary. It reads like a bank or a serious career service, which suits people anxious about their careers.
- *Risks:* it is the least distinctive. Navy and blue sit inside the category's blue (LinkedIn, Naukri, Indeed). Without a strong idea elsewhere, it may look generic.

**B. Editorial and distinctive.**
- *Strengths:* the brand comes from **type and geometry, not effects.* A serif display face and sharp, rule-based layout read as a well-made document, which matches the product's core story (an honest, edited resume). Gold is reserved for one meaning, evidence: fact chips and the brand dot. No shadows, so it stays crisp on cheap screens.
- *Risks:*
  - Cobalt is still a blue, so distinctiveness depends on the typography being executed well.
  - Source Serif 4 and Geist have no Devanagari. Hindi later needs Noto Serif and Noto Sans Devanagari as companion faces.
  - Too much serif turns "magazine"; keep it to headlines only.

**C. Refined dark.**
- *Strengths:* premium and modern, and comfortable for long evening sessions.
- *Risks:*
  - Amber is both the primary action and the warning colour, so "Answer" and the warning callouts compete. This was visible in `compare-app.png`.
  - Dark pages read worse in bright daylight on budget phones.
  - For a brand default, dark signals "developer tool" more than "career service".
  - It is better as the app's optional dark theme than as the brand.

## 6. Recommendation

**B. Editorial and distinctive**, with two adjustments:
1. Use the serif only for display and headings. Everything people operate (buttons, forms, lists) stays in Geist, which the app already uses.
2. Derive the app's dark mode from C's layering, but give dark mode its own primary (a light cobalt) so amber is never both action and warning.

Why B over A: it gets a recognisable identity from typography and structure, not colour or effects. That is the only route that is both distinctive and as readable as A, and it expresses "every line true" visually, because the product looks like a carefully edited document.

If you want the most conservative choice instead, A is safe and clearly better than today's app, but it won't be memorable.

**Before deciding,** look at `prototype.html?t=b` on your own phone and laptop, and show `compare-landing.png` and `compare-app.png` to five people from your target group. Nothing in production changes until you approve a direction.
