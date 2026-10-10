# ApplyScout design system proposal (for approval, nothing implemented)

Boards: `option-1.png` (Ink and marigold, recommended), `option-2.png` (Forest and amber), `option-3.png` (Plum and apricot). Each board shows the same screens so the systems can be compared fairly: a landing page, Today (desktop and phone), a job card, the campaign form, loading/empty/error/undo states, and the tokens. Sources are the `.html` files beside them. Screenshots of the app as it is today are in `current/`.

## 1. What exists today (inspected in code and in the running app)
- **Stack:** Next.js 15, Tailwind 3, shadcn/ui on Radix primitives, Lucide icons, Geist font, light/dark by OS setting. Colours are CSS tokens in `apps/web/styles/globals.css`.
- **Structure:** top navigation (Today, Review, Applications, Campaign, Profile) on desktop, a bottom tab bar on phones. There is **no landing page**: `/` redirects to sign in.

## 2. Audit of the current UI
Ranked by how much each hurts the user.
1. **Phone layout overflows on Today** (390 px wide): cards and the Pause button run off the right edge, and the summary text is cut. See `current/today-mobile.png`. This is a real bug, not taste.
2. **The one thing that blocks Maggie isn't emphasised.** "Needs you" is one of four identical tiles, styled the same as "New matches".
3. **Brand mismatch:** the in-app logo is an old bird glyph, the new A logo is not used, and the blue primary (`#1F55C9`) sits next to LinkedIn and Naukri blue.
4. **Inconsistent radii:** six values in use (`rounded-md` 50, `-lg` 26, `-xl` 25, `-2xl` 53, `-full` 19, plus `-sm`, `-xs`, `-4xl`).
5. **Colours that bypass tokens:** raw `emerald-500/700`, `amber-500/800`, `red-500`, `blue-500` in `ApplicationCard.tsx` and the Kibo status component, so dark mode and contrast aren't controlled there.
6. **Icon naming drift (one family, two names):** `AlertTriangleIcon` and `TriangleAlertIcon`, `MailQuestionIcon` and `MailQuestionMarkIcon` are the same icons imported under different names. Icon sizes vary between `size-3`, `3.5`, `4`, `5`, `6`, `7`.
7. **Type drift:** 12 text sizes, including one-off pixel values (`text-[15px]` x10, `[28px]`, `[34px]`, `[17px]`, `[11px]`).
8. **Template tells:** an all-caps "APPLYSCOUT" eyebrow on onboarding, and dot-joined meta strings.
What's already good and must be kept: plain-language copy, status always shown with icon plus words, `aria-live` status, `sr-only` text on external links, real loading and error states, undo after dismiss, 44 px buttons on Review.

## 3. Research behind the choices
- **Competitors are blue, green, teal or purple** (Indeed `#003A9B` and LinkedIn `#0A66C2` confirmed; others from observation). A warm palette is the only clear space.
- **Colour and trust:** the largest cross-cultural study (Jonauskaite et al., 2020, 30 countries) found colour–emotion links are broadly shared, with local variation; purple had the least agreement. Trust comes mainly from clarity, consistency and honest wording, which is why the system spends colour sparingly.
- **Markets:** saffron is politically and religiously loaded in India, so it is avoided. Red reads as danger and is reserved for errors. Green is positive in India and the Gulf but collides with success states. Marigold and gold are warm and positive in India.

## 4. The system (shared by all three options)
**Icons: Lucide only.** It is already installed and covers every symbol needed (checked against the screens above), so Phosphor and Tabler are not needed, and mixing families is not allowed.
- One rendered stroke of **1.5 px at every size** (Lucide `absoluteStrokeWidth`).
- Sizes: **16** in dense rows, **20** in buttons and lists, **24** in the phone tab bar.
- One name per icon; the duplicate aliases are removed.
- An icon always sits beside a word. Icon-only controls (account menu, remove chip) carry an `aria-label`.

**Colour: Radix Colors scales, used by step meaning.**
| Role | Radix step | Rule |
|---|---|---|
| Page, surface, subtle fill | neutral 2, 1, 3 | |
| Borders | neutral 5 | dividers and card edges |
| Input borders | neutral **9** | step 8 measured only 1.9:1; WCAG needs 3:1 for field edges |
| Muted text, text | neutral 11, 12 | |
| Needs you | accent 9 as a fill or dot only | never as text |
| Text on accent tint | accent **12** on accent 3 | Radix step 11 on step 3 measured 3.99 to 4.25:1 for amber, orange and green, which fails AA |
| Success, danger | green, red; text uses step 12 on tints | |
Every pair is listed with its measured ratio on each board; all pass.

**Type:** one family per option, five sizes only. Display 52/56 (landing only), Title 30/36, Heading 17/24, Body 15/24, Small 13/20. Weights 400, 500, 600. Tabular numerals for counts and times. Sentence case, no all-caps labels.

**Spacing:** 4 px base: 4, 8, 12, 16, 24, 32, 48, 64.

**Radius:** two values only, controls and surfaces (6/10, 4/8 or 10/16 depending on option), plus full round for badges.

**Elevation:** surfaces are separated by 1 px borders. One shadow exists, for floating things only (toasts, menus, dialogs).

**Motion:** 150 ms ease-out for state changes a person caused (open, expand, confirm). No entrance animations. `prefers-reduced-motion` respected.

**Behaviour rules:**
- One primary button per screen region.
- Reversible actions use undo instead of a confirmation dialog. Irreversible ones confirm and name exactly what is lost.
- Status is never colour alone.
- Every list has loading, empty and error states.
- The send mode ("I press Send" or "Send automatically") is spelled out with its consequence.
- No urgency, fake counts or hidden opt-outs.

**Layout decisions:**
- Keep the top navigation.
- Today becomes Maggie's short note, then only what is waiting for the person, with the day's numbers and her rules at the side. This replaces the four equal tiles.
- Add a landing page.

## 5. Options and recommendation
**Recommended: Option 1, Ink and marigold, with IBM Plex Sans.**
- It is the furthest from every competitor.
- The logo's amber dot becomes the single "needs you" colour, so the brand mark and the call to action are the same thing.
- IBM Plex has matching Devanagari, Arabic and Thai families for later.
- Its risk is coldness, which the copy and the note must offset.

Option 2 is the strongest alternative. Option 3 is the warmest but has the weakest script coverage and the least predictable colour meaning.

## 6. What was and wasn't verified
- **Done:** contrast for every token pair, computed and shown on each board. Rendered and visually reviewed each board twice. Fixes made from that review:
  - a button-alignment bug
  - two failing contrast pairs (input borders; count text on the orange badge)
  - mislabelled rationale
- **Not done:** keyboard and screen-reader testing of the new styles, since nothing is implemented, and any user testing. Nothing here is "psychologically validated". After approval, implementation should be followed by axe checks, keyboard passes and a short test with about five job seekers.
- **Not used:** `Keenmate/pure-admin-icons` was not reviewed in depth; Lucide covered every symbol, so a second icon set would break the one-family rule.
