# ApplyScout: Logo Guidelines (compact)

## 1. The logo
- **Idea:** an A drawn as an upward chevron with a dot in its counter, like a scout's trail marker pointing forward.
- **Versions:** horizontal (primary), stacked, symbol-only, wordmark-only. Each has a full-colour and a reversed file.
- **Files:** `kit/*.svg` are masters. `kit/variants/` has black, white and brand-mono SVGs plus PNGs, favicon.ico, apple-touch-icon, icon-192/512, maskable-512 and `site.webmanifest`. `kit/presentation.html` shows everything in use.
- **Wordmark:** Inter SemiBold, converted to outlines, so no font is needed to display it. Never retype the name in place of the file.

## 2. Clear space
Keep a clear zone of **1 x** around the logo on all sides, where x = the stroke width of the A (about one fifth of the symbol's height). The zone scales with the logo; never use a fixed distance.

## 3. Minimum size
| Version | Screen | Print |
|---|---|---|
| Horizontal | 96 px wide | 25 mm wide |
| Stacked | 64 px wide | 18 mm wide |
| Symbol | 24 px (full) | 8 mm |
| Symbol, small-size cut (`applyscout-symbol-small.svg`) | 16 px (favicon, tabs) | n/a |

Below 24 px, always use the small-size cut: it is thicker and has no dot, because the dot disappears at that size.

## 4. Colour
| Name | HEX | RGB | CMYK (approx.) | Pantone |
|---|---|---|---|---|
| Indigo (primary) | #4F46E5 | 79, 70, 229 | 66, 69, 0, 10 | match at printer |
| Amber (accent, the dot) | #F59E0B | 245, 158, 11 | 0, 36, 96, 4 | match at printer |
| Ink | #111827 | 17, 24, 39 | 56, 38, 0, 85 | match at printer |
| Light indigo (on dark) | #A5B4FC | 165, 180, 252 | 35, 29, 0, 1 | match at printer |

CMYK values are mathematical conversions. Proof them on the actual paper and process before a large print run.

**Contrast:** indigo on white 6.3:1 and ink on white 17.7:1 (both pass WCAG AA for text). White on indigo 6.3:1. Light indigo on ink 8.9:1. Amber is a graphic accent only (2.2:1 on white); never use it for text.

**Approved pairs:** full colour on white or off-white, reversed on indigo or ink, black on white, white on any dark photo area. Single-colour versions are in `kit/variants/`.

## 5. Typography
- Headlines and the wordmark: Inter SemiBold. Body: Inter Regular and Medium. Web fallback: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Licence: Inter is open source under the SIL Open Font License, which allows use in logos and products.

## 6. Don'ts
Don't stretch or squash. Don't recolour outside the palette. Don't rotate. Don't add shadows, outlines, gradients or effects. Don't rearrange or resize the parts of a lockup. Don't place on busy backgrounds without a container. Don't recreate the wordmark by typing it. Don't use the amber dot as text colour.

## 7. Open items
- **Trademark:** nobody has searched "ApplyScout" or the symbol in any trademark database. Do this before investing in the brand (India, UAE, Singapore, plus any market you sell in).
- **Print files:** this kit is SVG and PNG. PDF/EPS masters need Inkscape or Illustrator.
- **Master construction:** the symbol is built from two round-capped strokes at exactly 60 degrees (stroke 36 on a 256 grid, dot radius 17). The reversed version is drawn about 6% thinner so it does not look heavier on dark backgrounds.
