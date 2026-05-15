# Deck Structure Blueprint

Every slide in the Capybaras lead deck, in order, with layout and required elements. All dimensions assume `LAYOUT_WIDE` (13.3" × 7.5").

Symbols used below:
- `[STATIC]` — copy comes from `static-content-{lang}.md`, do not rewrite
- `[DYNAMIC]` — copy is generated from audit data
- `[CONDITIONAL]` — only render under specific conditions

---

## Section 1 — Capybaras Intro

### Slide 1 — Cover `[STATIC + DYNAMIC]`
- Background: `assets/brand/topographic_bg_dark.png` (covers full slide) or solid `#0E0E0E`
- Top center: Capybaras combined logo `assets/logos/capybaras_logo_combined.png`, ~3.5" × 1.07", positioned ~1.5" from the top
- Title: "Commercial Proposal" — white, ~54pt bold, centered
- Subtitle: `{{BRAND_NAME}}` — white, ~44pt, with a short orange divider line and end dots below it
- Date pill: rounded orange pill bottom-center with date inside, white text, ~16pt
- Bottom-left accent (optional): `assets/brand/orange_arrow.png`, ~0.7" × 0.7", at x=0.5, y=6.3

### Slide 2 — "About Us" Section Divider `[STATIC]`
- Background: `assets/brand/topographic_bg_dark.png` or solid `#0E0E0E`
- Centered title: "About Us", white, ~80pt
- Capybaras logo icon (`assets/logos/capybaras_logo_icon.png`) bottom-left, ~0.9" × 0.85", at x=0.5, y=6.2
- Orange bricks decoration (`assets/brand/orange_bricks.png`) top-right, ~1.6" × 1.35", at x=11.4, y=0.4

### Slide 3 — Agency Stats `[STATIC]`
- White background
- Dark header band top with title: "We are the #1 Amazon Growth agency in The Americas"
- Subtitle line under the title, with short orange line between two dots
- Tagline below: "We boost your e-commerce sales so your brand reaches its full potential"
- Five large stat callouts in a row, each big orange number on top, short caption below — see static-content for exact values
- Bottom strip: 4 partner/certification cards (Certifications, Mentorships, Collaborators, Strategic Partners) — orange labels with logo placeholders. If no logo assets, use plain text names.
- Optional accent: `assets/brand/americas_map_orange.png` placed bottom-right at ~1.5" × 1.75" as a subtle reinforcement of the "Americas" positioning, low opacity / faded if it competes with the stats numerically. Skip if it adds visual noise.

### Slide 4 — Create / Launch / Scale `[STATIC]`
- White background
- Dark header band with title: "We help our clients create, launch, and scale their businesses."
- Subtitle stating the agency generates $9M+/month across 20+ categories
- Three rounded cards in a row, each labeled CREATE / LAUNCH / SCALE, each containing 3 brand names per stage — see static-content
- Bottom tagline: "We support DTC brands at any stage"

### Slide 5 — Services Overview `[STATIC]`
- Dark background
- Left column: large title "We cover the store's operation completely."
- Right column: four service blocks around a central "Strategic Management" highlighted card
  - Strategic Management — center, white card with dark text
  - Advertising (top-left or left) — orange title, white description
  - Creative (bottom-center) — orange title, white description
  - Supply (right) — orange title, white description
- See static-content for descriptions

### Slide 6 — "Case Studies" Section Divider `[STATIC]`
- Background: `assets/brand/topographic_bg_dark.png` or solid `#0E0E0E`. Centered "Case Studies" title. Capybaras icon `assets/logos/capybaras_logo_icon.png` bottom-left, orange bricks `assets/brand/orange_bricks.png` top-right.

### Slide 7 — Tattoo Care Case Study `[STATIC]`
- Split layout: left ~40% white panel, right ~60% dark panel `#0E0E0E`
- Left panel: brand name "TATTOO CARE" in large bold black text (~48pt, centered), no phone mockup. Optional: a small caption underneath like "Skin care for tattoos" in gray
- Right panel content:
  - CHALLENGE heading (orange)
  - 2–3 sentence challenge description
  - SOLUTIONS & SERVICES heading (orange)
  - 4–5 sentence solution narrative
  - RESULTS heading (orange)
  - Three results stat cards: "5° Top ranking", "Amazon Choice", "6 Figure Sales"

### Slide 8 — Wamery Case Study `[STATIC]`
- Same split layout. Left panel: "WAMERY" in large bold (use a light blue tone `#A8D8E8` to match the reference brand mark color, optional caption "Water filters & kitchen items")
- Three results: "20% Increase in CTR", "50% Increased CR", "-10% TACOS Reduction"

### Slide 9 — Shapermint Case Study `[STATIC]`
- Same split layout. Left panel: "shapermint" in large bold black (lowercase, matching the brand wordmark style), optional caption "Women's apparel"
- Three results: "#1° Top Ranking", "61% Sales Increase", "-19% TACoS Reduction"

---

## Section 2 — The Project / Audit

### Slide 10 — "The Project" Section Divider `[STATIC]`
- Background: `assets/brand/topographic_bg_dark.png` or solid `#0E0E0E`. Centered title: "The Project".
- Capybaras icon `assets/logos/capybaras_logo_icon.png` bottom-left, orange bricks `assets/brand/orange_bricks.png` top-right

### Slide 11 — Brand Overview `[DYNAMIC]`
- White background
- Title: `{{BRAND_NAME}}` in orange + " - Overview" in black, with short orange divider line under it
- 2–3 paragraph brand summary based on what the audit found out about the brand
- A "Value Proposition" block with 3 bullet points (use bold for the lead-in phrase, regular for the explanation)
- Optional: small Capybaras logo top-right

### Slide 12 — Category / Market Overview `[DYNAMIC]`
- White background
- Title: `{{CATEGORY_NAME}} - Category Overview`
- Two horizontal panels stacked:
  - Top "Market Summary" panel: 4 stat cards (Total Revenue, Total Sales, Median Price, Median Reviews) with values from audit
  - Bottom "Competitors Analysis" panel: 2 charts side-by-side — opportunity evaluation (KW count) and competitors search volume strength
- Below the panels: 2–3 bullet takeaways about the category

### Slide 13 — SEO / Keyword Opportunity `[DYNAMIC]`
- White background
- Title: `{{CATEGORY}} - SEO Opportunity`
- Body: a takeaway line at top: "Most keywords aren't being targeted by main players" or similar
- Below: a comparison table of top 10–15 keywords, the niche median, the lead's column, and 3–5 competitors' columns — showing which ranks where
- If a full table is too heavy to render cleanly, show top 5 keyword gaps as cards instead

### Slide 14 — Listing Improvements / Current State `[DYNAMIC]`
- White background
- Title: `{{CATEGORY}} - Listing Improvements`
- Left side: thumbnail/description of the lead's current listing main image — if no screenshot available, list its visible attributes (gallery count, badges present)
- Right side: 6 rows, each row = one improvement area with "✕ MISSING" or "✓ PRESENT" label
  - Main Image
  - Infographics
  - Bullet Points
  - A+ Content
  - Brand Storefront
  - Product Video
- Each row: small orange icon + label + short description of what's missing

### Slide 15 — Implementation Plan (Amazon) `[DYNAMIC]`
- White background, or split layout (dark left / white right)
- Title: "Amazon Launch & Growth"
- Subtitle: "Our conversion channel — capturing high-intent buyers from day one." or similar
- 6 cards in a 2×3 or 3×2 grid:
  - Catalog Creation / Setup
  - SEO & Keyword Research
  - Listing Optimization
  - Brand Storefront
  - PPC Campaign Management
  - Promos & Ranking Strategy
- Each card: small orange icon + bold title + 1-line description
- Bottom footer line: "Goal: maximize visibility, conversion rate, and profitability from day one." in italic orange

---

## Section 3 — DTC `[CONDITIONAL — only if DTC in scope]`

### Slide 16 — DTC Opportunity Summary `[DYNAMIC]`
- White background
- Title: "Where Your DTC is Bleeding"
- Three columns or three stacked rows, each one a finding from the digital-presence-audit:
  - Meta Ads grade + 1-sentence finding
  - Website / Shopify grade + 1-sentence finding
  - SEO / Social grade + 1-sentence finding (only if relevant)
- Below: 1-paragraph takeaway about why a DTC channel matters even when Amazon is winning

### Slide 17 — Shopify DTC Strategy `[STATIC + DYNAMIC]`
- White background
- Title: "Shopify: Direct-to-Consumer Channel"
- Subtitle/intro: 1-paragraph framing (static)
- Left side: 4 icon rows
  - Own Customer Data
  - Better Margins
  - Richer Brand Storytelling
  - Flexible Promotions
- Right side: customer journey flow (Ad Creative → Landing Page → Purchase → Email Follow-up) — orange "Purchase" highlighted

### Slide 18 — Meta Ads Growth Engine `[STATIC]`
- White background
- Title: "Meta Ads: Growth Engine"
- Subtitle: "Generate demand beyond marketplace search — turn paid media into a growth engine."
- 2×3 grid of feature cards:
  - Demographic Targeting
  - Interest-Based Targeting
  - Retargeting Visitors
  - Cart Abandonment Recovery
  - Pixel Data Optimization
  - Creative Testing at Scale
- Bottom italic line: "Funnel: Awareness → Interest → Retargeting → Purchase → Retention"

### Slide 19 — DTC Implementation Plan `[DYNAMIC]`
- White background
- Title: "DTC Implementation Plan"
- 3 milestone cards horizontally:
  - 30 days: foundation (pixel install, Meta setup, Shopify audit)
  - 60 days: campaigns launched, A/B tests running
  - 90 days: scale, optimize, retargeting layered
- Each card: bold heading + 2–3 short bullet items

---

## Section 4 — Conclusions

### Slide 20 — "Why Capybaras?" Section Divider `[STATIC]`
- Background: `assets/brand/topographic_bg_dark.png` or solid `#0E0E0E`. Centered title "Why Capybaras?". Capybaras icon bottom-left, orange bricks top-right.

### Slide 21 — Why to Join Capybaras `[STATIC]`
- White or light background
- Title: "Why to join Capybaras"
- Short orange divider line under title
- Four content blocks stacked vertically, each with an orange left border:
  - The End of Amateur Hour
  - Information Asymmetry
  - The Intellectual Capital
  - CEO Bandwidth Recovery
- Each block: bold heading + 2-sentence paragraph
- See static-content for exact copy — **do not paraphrase**

### Slide 22 — Success Team for [Brand] `[DYNAMIC + STATIC]`
- White background top section (~60%), dark bottom section (~40%)
- Title (white area): "Success Team for {{BRAND_NAME}}" with orange motif under
- Short orange divider line under title
- Top row (white area) — main team, 4 or 6 members depending on DTC scope:
  - Standard 4: Agustin Favano (Account Manager), Lenin Acosta (PPC Expert), Marcos Callorda (Catalog Specialist), Jeremias Orcajo (Graphic Designer)
  - With DTC: add Angeles (Shopify Expert) and Magali (Meta Ads Expert) — 6 members total
- Each member: photo from `assets/team_photos/<firstname>.png` (pre-cropped circular with brand-colored background — place as a square image), name in orange bold below, role in gray below
- Bottom row (dark area, use `assets/brand/topographic_bg_dark.png` cropped to band height or solid `#0E0E0E`) — cross-support, 3 members always: Freddy Neuman (Founder & CEO), Guille Neuman (Advertising Manager), Ramiro Folgueras (Director & Strategy Manager)
- Left edge of dark band: orange chevron/flag shape with "CROSS-SUPPORT TEAM" label in white bold

### Slide 23 — Closing "Let's scale!" `[STATIC]`
- Background: `assets/brand/topographic_bg_dark.png` covering the full slide, or solid `#0E0E0E`
- Left ~45%: capybara character illustration `assets/brand/capybara_character.png`, sized ~5" × 4.7", at x=0.5, y=1.3
- Right ~55%: Capybaras wordmark (orange "Capybaras" text, large) + main headline
  - Headline: "Let's scale!" (default) or "Let's scale on Amazon!" (Amazon-only deck)
- Headline ~80pt white bold

---

## Slide Count Summary

| Configuration | Slides |
|---------------|--------|
| Amazon only | 19 slides (1–15, 20–23) |
| Amazon + DTC | 23 slides (full 1–23, with 16–19 included) |

Always finish on the "Let's scale!" closing slide.
