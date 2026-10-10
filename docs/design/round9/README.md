# Round 9: tech direction, animated hero, fact-link signature (light and dark)

Pictures and prototypes only. Production styling is unchanged.

## What's new compared with round 8
1. **An animated hero** (`hero-demo-dark.mp4`, `hero-demo-light.mp4`; the HTML pages loop it live). The loop runs about 13 seconds:
   - a job is matched (fit 92);
   - tailored lines appear one by one;
   - each line draws a green link to the fact that backs it;
   - "Led a team of 6 analysts" searches every fact with dashed red lines, finds nothing, and is struck out and removed;
   - Approve is pressed and a "Sent from your Gmail" receipt appears.
   
   With `prefers-reduced-motion` the end state is shown without animation. Add `?step=0–11` to a page's URL to freeze one frame.
2. **A signature visual: the fact link.** Thin green lines from a fact to the resume line it backs. It runs through the hero and the Truth check cell, and can carry into ads, social posts and the app itself.
3. **A polish pass:**
   - tighter type sizes and section spacing;
   - copy rewritten;
   - 2x hero screenshots;
   - the phone layout stacks the facts above the resume and hides the link lines, so they never cross the text.

## Files
| File | What it shows |
|---|---|
| `landing-dark.html`, `landing-light.html` | Open in a browser to see the animation |
| `hero-demo-*.mp4` | Recorded hero animation |
| `shots/*-hero.png` | Hero at 2x |
| `shots/*-full.png` | Full page |
| `shots/*-mobile-strip.png` | Phone layout |

## Before launch
- "100% of lines linked to a fact" and "0 sent without your approval" only become true once the `can_send()` gate is enforced on every send path (council finding P0).
- Prices are placeholders.
- linear.app, vercel.com and uidiscovery.com were blocked by the network policy, so nothing was compared against the live sites.
