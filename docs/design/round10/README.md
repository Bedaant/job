# Round 10: four new landing-page directions in Figma

Figma file: https://www.figma.com/design/iR4Dl0jjxJrdh4SRGHrlgb

All four are editable Figma layers (text, auto-layout, local components), not screenshots. The PNGs here are previews exported from Figma.

## The four directions

| | Direction | Idea | Type | Colour |
|---|---|---|---|---|
| A | **Redline** (Swiss editorial) | A resume marked up like an editor's proof: red footnotes (F2, F4) back each line, and "No source, removed" strikes the bad one. Very large type and a strict grid. | Inter | Black and white plus signal red `#FF3B00` |
| B | **Command** (keyboard-first, dark) | A Raycast/Linear-style command bar: you type a request, and matches and actions appear with keyboard shortcuts. | Geist + Geist Mono | Near-black plus electric lime `#D7FF3A` |
| C | **Warm** (phone-first, mass market) | A big rounded forest-green hero with two phone screens ("3 jobs ready", "Check before sending"), trust chips, cards for each career stage, and ₹ pricing. | Bricolage Grotesque + Plus Jakarta Sans | Forest `#0E3B2C`, lime `#C8F169`, cream and peach |
| D | **Global** (multi-market) | A language switcher (EN / हिं / ع), "Every line true." shown in English, Hindi and Arabic, and market cards for India, UAE and Singapore with local currency. | Noto Sans + Noto Sans Devanagari + Noto Sans Arabic | White and ink plus saffron `#FF7A1A` |

## Components (above each pair of pages)
- `A/Button`, `A/Button secondary`
- `B/Button primary`, `B/Button ghost`, `B/Result row`
- `C/Button lime`, `C/Trust chip`
- `D/Button`, `D/Market card`

## Known issues
- In C, the phone screens are cut off on the right inside the hero panel, and the job titles in the first phone are truncated.
- All prices are example values. Gulf and Singapore prices are placeholders.
- Claims such as "Nothing is sent without you" still depend on the `can_send()` safety gate being built.
