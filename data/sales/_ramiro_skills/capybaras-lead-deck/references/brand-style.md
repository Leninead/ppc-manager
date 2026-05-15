# Capybaras Brand Style — Deck Spec

Visual system for the lead deck. Follow exactly. Inconsistencies between slides are the #1 thing that makes a deck look amateur.

---

## Colors

| Token | Hex | Use |
|-------|-----|-----|
| `BLACK` | `#0E0E0E` | Dark slide backgrounds, dark text on light |
| `PURE_BLACK` | `#000000` | Rare — avoid unless asked |
| `ORANGE` | `#FF3300` | Primary accent: divider lines, headers, stat numbers, CTAs |
| `ORANGE_DARK` | `#E85B03` | Secondary accent, hover states, gradients |
| `WHITE` | `#FFFFFF` | Text on dark, content slide backgrounds |
| `GRAY_LIGHT` | `#A0A0A0` | Muted body text on dark backgrounds |
| `GRAY_MID` | `#666666` | Muted body text on light backgrounds |
| `GRAY_BG` | `#F5F5F5` | Subtle card backgrounds on white slides |
| `GREEN` | `#22C55E` | "What's working" callouts |
| `RED` | `#EF4444` | "Missing" / "Critical" tags |

**Contrast rule:** Never put gray text on cream/beige. Never put light orange (`#E85B03`) on white — it fails contrast.

---

## Typography

**Primary font:** `Blauer Nue` — Capybaras brand font. Set via `fontFace: 'Blauer Nue'` in every pptxgenjs `addText` call. **Ramiro must have this font installed locally** for the deck to render correctly when opened in PowerPoint/Keynote. When sending to a client, always export to PDF first (File → Export → PDF) so the font is locked into the document; do not send the raw .pptx unless the recipient is known to have Blauer Nue.

**Fallback if Blauer Nue is not available on the machine running the build:** `Arial` (PowerPoint will substitute automatically when the named font isn't found, but the design tokens below are calibrated for Blauer Nue's metrics).

| Element | Size | Weight | Color (on dark / on light) |
|---------|------|--------|----------------------------|
| Cover title | 54pt | Bold | White |
| Cover subtitle (brand name) | 44pt | Regular | White |
| Section divider title | 80pt | Bold | White |
| Slide title | 36pt | Bold | Orange (brand keyword) + Black (rest) |
| Subtitle / section header | 22pt | Bold | White / Black |
| Body text | 14–16pt | Regular | White / Black |
| Body emphasis | 14–16pt | Bold | White / Black |
| Stat number | 56–72pt | Bold | Orange |
| Stat caption | 12–14pt | Regular | Gray Mid |
| Caption / footer | 10–11pt | Regular | Gray Light / Gray Mid |

**Slide titles** follow the pattern: `<orange keyword> - <black descriptor>` (e.g. "Nandog - Overview"). The orange word is the brand/category, the black word is the slide type.

---

## Layout

- **Format:** `LAYOUT_WIDE` — 13.3" × 7.5"
- **Margins:** 0.5" minimum on every side
- **Content area:** Roughly 12.3" × 6.5"
- **Gap between content blocks:** 0.3" or 0.5" — pick one and use consistently across the deck
- **Card padding:** 0.3" internal padding minimum

---

## The Capybaras Motif — Orange Divider Line

This is the most recognizable Capybaras visual element. Place it under every content slide title.

**Specification:**
- Horizontal orange line, ~1.5" wide, 0.04" tall, color `#FF3300`, rounded ends (`rectRadius: 0.02`)
- Two small filled orange circles, radius ~0.05", placed at each end of the line
- Position: centered under the slide title, ~0.15" of vertical gap between title and line
- Alignment: align the line's left edge with the leftmost letter of the title (do not center it)

**pptxgenjs example:**
```javascript
// Under a title positioned at x=0.5, y=0.5
slide.addShape('roundRect', {
  x: 0.5, y: 1.1, w: 1.5, h: 0.04,
  fill: { color: 'FF3300' },
  line: { color: 'FF3300' },
  rectRadius: 0.02
});
slide.addShape('ellipse', {
  x: 0.46, y: 1.08, w: 0.08, h: 0.08,
  fill: { color: 'FF3300' }, line: { color: 'FF3300' }
});
slide.addShape('ellipse', {
  x: 1.96, y: 1.08, w: 0.08, h: 0.08,
  fill: { color: 'FF3300' }, line: { color: 'FF3300' }
});
```

**Do not** use this motif on section divider slides (those are just the big white title centered on black) or on the cover.

---

## Section Divider Slides

- Background: `assets/brand/topographic_bg_dark.png` covering the full slide (13.3" × 7.5"), or solid `#0E0E0E` if the texture would clash with foreground content
- Title: white, ~80pt bold, centered both axes
- Capybaras icon (just the orange rounded square with capybara silhouette) at bottom-left: `assets/logos/capybaras_logo_icon.png`, ~0.9" × 0.85", positioned at x=0.5, y=6.2 (well clear of the centered title)
- Orange brick decoration top-right: `assets/brand/orange_bricks.png`, ~1.6" × 1.35" (preserves the 1.19:1 source ratio), positioned at x=11.4, y=0.4

---

## Cover Slide

- Background: `assets/brand/topographic_bg_dark.png` covering the full slide, or solid `#0E0E0E`
- Top center: Capybaras combined logo `assets/logos/capybaras_logo_combined.png` (the pill with capybara icon + "Capybaras" wordmark on dark). Place at ~3.5" wide × ~1.07" tall (preserves the 3.27:1 aspect ratio of the source file), centered horizontally, ~1.5" from the top
- Title "Commercial Proposal" — white, 54pt bold, centered horizontally
- Subtitle (brand name) — white, 44pt regular, centered, with an orange divider line + end dots below
- Date pill: rounded orange shape (`pillBoth` or `roundRect` with high radius), centered, ~1.8" wide × 0.5" tall, white bold text 14pt inside
- Bottom-left accent (optional but matches reference decks): `assets/brand/orange_arrow.png`, ~0.7" × 0.7", at x=0.5, y=6.3

---

## Stat Cards (Content Slides)

**Big stat block** (used on Agency Stats slide and audit market overview):
- Number: orange, 56–72pt bold, no margin
- Caption: gray mid, 12–14pt regular, centered under the number

**Compact stat card** (used in 2×3 or 3×2 grids):
- Card background: white with subtle border (1pt, color `#E5E5E5`), or `#F5F5F5` fill no border
- Card padding: 0.3" all sides
- Heading: black, 14pt bold
- Body: gray mid, 11–13pt regular
- Optional small orange icon in a 0.4" × 0.4" circle to the left of the heading

---

## Service / Feature Grid Cards (Plan slides)

Used on Amazon Implementation Plan and Meta Ads Engine slides.

- Card: rounded rectangle, fill `#F5F5F5` or `#1A1A1A` (depending on slide background), padding 0.3"
- Left edge: 0.05" wide solid orange bar from top to bottom of the card
- Small orange filled icon area (~0.5" × 0.5") top-left inside the card
- Title: 16pt bold, white or black depending on bg
- Description: 12pt regular, gray
- Spacing between cards in a grid: 0.3"

---

## Case Study Slide Layout

- Split: left 40% / right 60%
- Left panel: white background, brand wordmark set as text (large bold, color appropriate to the brand — black for Tattoo Care and Shapermint, light blue `#A8D8E8` for Wamery), centered both axes. Optional one-line gray subtitle below the wordmark describing the brand category.
- Right panel: dark `#0E0E0E` background
- Right panel content stack:
  - "CHALLENGE" heading — orange 16pt bold
  - Challenge text — white 12pt regular, ~3 lines
  - "SOLUTIONS & SERVICES" heading — orange 16pt bold
  - Solution text — white 12pt regular, ~6 lines
  - "RESULTS" heading — orange 16pt bold
  - Three result cards in a row at the bottom, each: big orange number top, small white caption below

---

## Why Capybaras Slide

- White background
- Title at top with orange divider line motif
- Four content blocks stacked vertically with 0.25" gap between
- Each block:
  - Background: white with a 1pt border `#E5E5E5`, or `#F8F8F8` fill no border
  - Left edge: 0.08" wide solid orange bar from top to bottom of the block
  - Padding: 0.4" left, 0.3" other sides
  - Heading: black 16pt bold
  - Body: black 12pt regular, 2 sentences

---

## Team Slide

- Top ~60%: white background
- Bottom ~40%: `assets/brand/topographic_bg_dark.png` cropped to fit the dark band (or solid `#0E0E0E` if cropping is fiddly)
- Title at top white area: "Success Team for {{BRAND}}" with orange motif under
- Main team row (4 or 6 members, centered horizontally):
  - Photo: load from `assets/team_photos/<firstname>.png` — already comes with the orange/dark gradient background and circular crop baked into the source image. Place as a square image, 1.5" × 1.5", at the desired position. No additional masking needed.
  - Name below photo: orange 18pt bold
  - Role below name: gray mid 12pt regular
- Cross-Support row on dark band: 3 members, same pattern but smaller photos (1.1" × 1.1"), white text on dark
- Left side of dark band: orange chevron/flag shape — pptxgenjs `chevron` or `right` arrow shape — with "CROSS-SUPPORT TEAM" in white 14pt bold

**Available photo files in `assets/team_photos/`:**
- `agustin.png`, `lenin.png`, `marcos.png`, `jeremias.png` — main team (always shown, 4 members)
- `angeles.png`, `magali.png` — main team (additional, only shown when DTC is in scope, bringing total to 6)
- `freddy.png`, `guille.png`, `ramiro.png` — cross-support (always shown, 3 members)

**Fallback if a photo is missing:** generate a filled `ellipse` shape (fill `#444444`, white 2pt border) with the member's initials in white bold 24pt centered. This should never be needed for the standard roster — all photos are provided.

---

## Closing Slide

- Background: `assets/brand/topographic_bg_dark.png` covering the full slide, or solid `#0E0E0E`
- Left ~45%: capybara character illustration `assets/brand/capybara_character.png` (911×857, near-square), sized ~5" × 4.7", positioned roughly at x=0.5, y=1.3
- Right ~55% content:
  - Capybaras orange wordmark "Capybaras" at ~64pt bold (or use the combined logo asset if cleaner)
  - Headline below: "Let's scale!" (default) or "Let's scale on Amazon!" (when the deck is Amazon-only)
  - Headline ~80pt white bold

---

## Things to Avoid

- ❌ Full-width orange or dark bars across the top/bottom of content slides — reads as AI slop
- ❌ Centered body paragraphs — left-align all paragraphs
- ❌ Accent lines under every single title — only use the orange motif on content slides, never on section dividers or cover
- ❌ Stat cards with equal visual weight — the big orange number should dominate, caption should recede
- ❌ Using cream/beige backgrounds — Capybaras is black + orange + white only
- ❌ Mixing fonts within the deck — Blauer Nue everywhere
- ❌ Decorative gradients — Capybaras style is flat
- ❌ Drop shadows on shapes — flat only

---

## Quick Color Recap for `pptxgenjs`

All hex strings in pptxgenjs are **6 characters without `#`**:
- `'0E0E0E'` (black background)
- `'FF3300'` (orange accent)
- `'E85B03'` (dark orange)
- `'FFFFFF'` (white)
- `'A0A0A0'` (light gray)
- `'666666'` (mid gray)
- `'F5F5F5'` (subtle bg)

---

## Assets Inventory

All assets live under `assets/` inside the skill folder. The build script should reference them via relative paths from wherever the script runs — typically you'll copy the skill's `assets/` folder into the working directory before running `node build_deck.js`.

### `assets/logos/`

| File | Dimensions | Use |
|------|-----------|-----|
| `capybaras_logo_combined.png` | 2107×644 (3.27:1) | Cover slide top center |
| `capybaras_logo_icon.png` | 227×209 (~1:1) | Section dividers bottom-left |

### `assets/brand/`

| File | Dimensions | Use |
|------|-----------|-----|
| `topographic_bg_dark.png` | 1920×1080 (16:9) | Full-slide background on cover, section dividers, team slide dark band, closing slide |
| `orange_bricks.png` | 665×560 (~1.19:1) | Top-right corner decoration on section divider slides |
| `orange_arrow.png` | 470×470 (1:1) | Optional bottom-left accent on cover slide |
| `capybara_character.png` | 911×857 (~1:1) | Closing slide left panel |
| `americas_map_orange.png` | 657×768 (~0.86:1, portrait) | Optional accent on the Agency Stats slide (slide 3) to reinforce "Americas" positioning, or on a market analysis slide if the lead targets multi-country US+LATAM. Use sparingly. |

### `assets/team_photos/`

All photos are square (1200×1200 or 2400×2400), pre-cropped to a circle with orange/dark gradient backgrounds baked in. Place them as square images — the visual content already reads as circular.

| File | Person | Role | Standard / DTC / Cross |
|------|--------|------|------------------------|
| `agustin.png` | Agustin Favano | Account Manager | Standard |
| `lenin.png` | Lenin Acosta | PPC Expert | Standard |
| `marcos.png` | Marcos Callorda | Catalog Specialist | Standard |
| `jeremias.png` | Jeremias Orcajo | Graphic Designer | Standard |
| `angeles.png` | Angeles | Shopify Expert | DTC scope only |
| `magali.png` | Magali | Meta Ads Expert | DTC scope only |
| `freddy.png` | Freddy Neuman | Founder & CEO | Cross-support |
| `guille.png` | Guille Neuman | Advertising Manager | Cross-support |
| `ramiro.png` | Ramiro Folgueras | Director & Strategy Manager | Cross-support |

### Pending assets

The skill is now fully equipped for the standard deck. Case-study slide phone mockups (Tattoo Care, Wamery, Shapermint) are intentionally not asset-backed — Ramiro confirmed those are not a priority. The case-study slides should be built with text-only layouts on the dark right panel, using the brand wordmark of each case study brand as the left-panel anchor (set in text, not image).
