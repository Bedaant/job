# ApplyScout design directions (round 1: pictures only, nothing built)

Boards: `directions/direction-a.png`, `direction-b.png`, `direction-c.png` (sources are the `.html` files beside them).
All three show your real Today screen layout with **sample data**. No product features were invented: the nav, the Maggie status card, the four tiles and the activity rows come from `apps/web/app/today/page.tsx`.

## What I inspected first
- **Product:** a job-application autopilot. Upload a resume, set a campaign, Maggie finds matches, tailors the resume (truth-checked), and the extension fills the form. The user approves each application in assisted mode or lets it send within a daily cap.
- **Existing UI:** shadcn-style components on Tailwind 3, one blue accent (`#1F55C9`), system font stack, Lucide icons, light/dark by OS setting, radius 0.875rem. Colours are already tokens in `apps/web/styles/globals.css`, so a re-skin is a token change, not a rewrite.
- **Audience:** job seekers in India first, then the Gulf and Southeast Asia, many on mid-range Android phones, at an anxious moment. Trust and clarity matter more than flair.

## Findings in the current UI (prioritised)
1. **No brand typeface:** system fonts only, so the product has no recognisable voice. (High, cheap to fix.)
2. **One blue accent, no logo link:** the in-app logo (a bird glyph) doesn't match the new A logo. (High, cheap.)
3. **"SaaS card kit":** nearly everything is a rounded-2xl bordered card with the same soft shadow, so nothing stands out. Hierarchy comes from size alone. (Medium.)
4. **Category-cliché icons:** a rocket for Campaign. A target or route icon is more honest. (Low.)
5. **Strengths to keep:** plain-language labels, an explicit "needs you" state, text and icon (not colour alone) for status, `aria-live` on the Maggie status, `sr-only` text for external links.

## The three directions
| | A · Indigo Ink | B · Calm Teal | C · Material Tonal |
|---|---|---|---|
| Primary | `#4338CA` | `#0F766E` | `#4A44C6` |
| Attention (needs you) | amber | amber | amber container |
| Typeface | Plus Jakarta Sans | Figtree | Roboto |
| Shape | 12/10 px, hairline borders, no shadow | 18/14 px, soft shadow | 20 px cards, pill buttons, tonal surfaces |
| Feel | precise, confident | gentle, reassuring | friendly, thumb-first |

**Automated contrast, measured from the swatches** (all text pairs on each board pass WCAG AA 4.5:1; lowest is 5.1:1 for B's primary text on its background). This is a calculation, not a usability test.

### Scoring (my judgement, 1 to 5, not user-tested)
| Criterion | A | B | C |
|---|---|---|---|
| Looks trustworthy | 5 | 5 | 4 |
| Distinct from competitors | 3 | 5 | 2 |
| Matches the new logo | 5 | 3 (logo would be recoloured teal) | 4 |
| Mobile and touch friendliness | 4 | 4 | 5 |
| Cost to adopt in `apps/web` | 5 (closest to current) | 4 | 3 (new component shapes) |
| Risk | Indigo is common in SaaS | Success green vs teal brand need text/icon, never colour alone | Looks like a Google app |

## Recommendation
**A · Indigo Ink, borrowing C's 48 px touch targets on mobile.**
- It matches the logo you just approved, so the brand is one thing, not two.
- The flat, bordered style is the most trust-signalling and the cheapest to adopt (change tokens, font and a few component sizes).
- Keep amber for exactly one meaning, "needs you", so the user's eye goes to the action that blocks Maggie.
- B is the best pick if differentiation matters more than logo consistency (teal is rare in this category). Choose it only if you're happy to recolour the logo.

## Trust and behaviour rules applied in every board (to carry into the build)
- One obvious primary action per screen; secondary actions are outlined or tonal.
- The status card states what Maggie will and won't do: "You approve each application before it is sent · Daily limit 10 · Pause any time". Nothing here is a fake-urgency or hidden-consent pattern.
- Destructive actions are outlined in danger colour and need a confirmation that names what is removed. Status always has an icon and text, never colour alone.
- Loading, empty, error and disabled states are required for every component (the existing Today page already has loading and error states).

## What is not done, and what isn't validated
- Nothing is built in `apps/web`. These are pictures.
- Contrast ratios are computed; **keyboard, focus and screen-reader behaviour of the new styles haven't been tested**, because nothing has been implemented.
- Nothing here has been tested with real users. Pick a direction, then I'd run a short test with 5 job seekers.
- Hindi, Arabic (right-to-left) and other scripts aren't shown. If the Gulf matters early, Arabic needs a font and layout review (Plus Jakarta Sans and Figtree don't cover Arabic).

## Skills used
- `anthropics/skills` frontend-design: the brief-first process and its list of "AI default" tells to avoid (cream plus terracotta, identical rounded cards, eyebrow labels). I tried not to repeat them.
- `nicohodt/claude-code-ui-ux-skill`: its design database for palette and type ideas. Its auto-generated recommendation was a dark terminal style, which I rejected as wrong for anxious job seekers.
- `Leonxlnx/taste-skill` and `h3nryprod01/design-taste`: the "read the brief first" and "never ship the first version" rules, and the contrast and states checklist.
These were read and used as guidance, not installed into the repo.
