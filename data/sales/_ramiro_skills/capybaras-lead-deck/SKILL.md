---
name: capybaras-lead-deck
description: Generate a polished PPTX commercial proposal deck for a Capybaras Agency lead, combining a Capybaras intro, audit findings (Amazon, and optionally DTC), an implementation plan, and team slides. Use this skill whenever Ramiro asks to build a "commercial proposal", "propuesta comercial", "lead deck", "pitch deck", "proposal pptx", or any sales presentation for a prospective client. Also trigger when the request mentions converting an audit into a pitch, packaging audit findings into slides, or preparing a deck after running the amazon-brand-audit or digital-presence-audit skills. Outputs a .pptx in Capybaras Agency brand style (black + orange) ready to send to the prospect.
---

# Capybaras Lead Deck Skill

Builds a multi-slide PPTX commercial proposal for a prospective client. The deck is the deliverable that follows after `amazon-brand-audit` and (optionally) `digital-presence-audit` have run — it packages those findings into a sales asset.

Structure:
1. Capybaras Agency intro (who we are, case studies, services)
2. Amazon audit summary + implementation plan
3. (Conditional) DTC audit summary + implementation plan
4. Conclusions (Why Capybaras + Success Team for [Brand])

## When to include the DTC section

Capybaras' core DTC services are **Shopify store building** and **Meta Ads**. Only include the DTC section if there is a meaningful opportunity in one of those.

Include DTC if any of the following are true:
- Meta Ads grade is D or F AND at least one competitor is running active Meta ads
- Website Quality grade is D or F (signals Shopify rebuild opportunity)
- The brand has no Shopify/DTC store at all but the category has clear DTC demand
- Ramiro explicitly asks for DTC to be included

Exclude DTC if:
- The lead is purely an Amazon manufacturer or 1P→3P transition with no DTC plans
- Meta Ads grade is C or better AND Website grade is C or better
- Ramiro explicitly asks for Amazon-only

When the signal is unclear, ask Ramiro briefly before building: "Include the DTC section? Their Meta Ads is grade [X] and Website is grade [Y]."

## Inputs

**Required:**
- Brand name
- Amazon audit findings — either the HTML output file from `amazon-brand-audit` or a written summary

**Optional:**
- DTC audit findings (HTML from `digital-presence-audit`)
- Date (defaults to current month + year, e.g. "May 2026")
- Custom team roster (defaults to the standard one in `references/static-content-en.md`)

The deck is always built in English. This matches the language used by the upstream audit skills (`amazon-brand-audit` and `digital-presence-audit`) and is the language of the target leads (US-based brands).

## Workflow

### Step 1 — Read references first

Before writing any build script, read these in order:

1. `references/deck-structure.md` — slide-by-slide blueprint with layout specs
2. `references/static-content-en.md` — exact copy for the boilerplate slides
3. `references/brand-style.md` — colors, fonts, spacing, motifs

Then read the public pptx skill at `/mnt/skills/public/pptx/SKILL.md` and `/mnt/skills/public/pptx/pptxgenjs.md` for the technical build pattern. **Do not skip these** — they contain non-obvious constraints about text overflow, alignment, and rendering.

### Step 2 — Extract audit findings

**From the Amazon audit**, extract:
- 4–6 high-impact opportunities, specific and ASIN-level when possible (e.g. "Title is missing 3 of the top 10 search-volume keywords for the category")
- 3 implementation milestones spanning the next 30–90 days
- Category snapshot stats (total revenue, median price, median reviews, competitor count) for the Market Analysis slide
- The lead's current grade per lane (Listing / Visual / Social Proof / Competitive / Advertising)

**From the DTC audit** (if included), extract:
- 3–5 high-impact opportunities focused on Meta Ads and Shopify/website
- 3 DTC implementation milestones
- Competitive context (which competitors are running Meta, who has a stronger DTC site)

Always quote real numbers from the audit. Never invent stats — if a number is missing, omit the line rather than guess.

### Step 3 — Decide DTC inclusion and team composition

Apply the DTC rule above. If DTC is in scope:
- Add the DTC section between Amazon implementation plan and "Why Capybaras"
- Add **Angeles (Shopify Expert)** and **Magali (Meta Ads Expert)** to the Success Team slide — 6 members in the main row total

Standard team always shown (main row, 4 members):
- Agustin Favano — Account Manager
- Lenin Acosta — PPC Expert
- Marcos Callorda — Catalog Specialist
- Jeremias Orcajo — Graphic Designer

Cross-Support row (always shown):
- Freddy Neuman — Founder & CEO
- Guille Neuman — Advertising Manager
- Ramiro Folgueras — Director & Strategy Manager

All photos live at `assets/team_photos/<firstname-lowercase>.png`.

### Step 4 — Build the deck with pptxgenjs

Write a single Node.js build script at `/home/claude/build_deck.js`. Follow the slide order in `references/deck-structure.md` and pull the static copy from `references/static-content-en.md`.

**Before running the script, copy the skill's `assets/` folder next to the script** so image paths resolve. Example: if the skill is installed at `/mnt/skills/user/capybaras-lead-deck/`, copy `assets/` to `/home/claude/assets/` first. The script should reference images via `assets/logos/...` and `assets/team_photos/...`.

Key build rules:
- Use `LAYOUT_WIDE` (13.3" × 7.5") to match the reference decks
- Set every text block's `fontFace` to `'Blauer Nue'` (Capybaras brand font). Document for Ramiro that the font must be installed on his machine for the deck to render correctly; PowerPoint substitutes if missing
- Set `margin: 0` on every text box that has to align with shapes or accent lines
- The orange divider line under section titles is a short rounded rectangle (~1.5" wide, 0.04" tall, color FF3300) with two small circles at each end (radius 0.05", same color) — this is the Capybaras motif, repeat it consistently on content slides
- Section divider slides are fully dark (`#0E0E0E` background) with the big white title centered, plus the small Capybaras icon bottom-left and orange brick decoration top-right
- Content slides use white or near-white background by default; dark background only for cover, section dividers and the closing slide
- Never use text-only slides — every content slide needs an icon, shape grid, or visual element
- Avoid full-width colored bars or accent lines under titles on content slides — they read as AI slop

### Step 5 — Render and verify

After running `node /home/claude/build_deck.js`:

1. Run `extract-text` to confirm all key content is present and no placeholder strings (`{{BRAND}}`, lorem, TODO) leaked through:
   ```bash
   extract-text /home/claude/output.pptx | grep -iE "\bx{3,}\b|lorem|ipsum|\bTODO|\{\{"
   ```
2. Convert to images and visually inspect a few representative slides (cover, one case study, the audit summary, the team slide, the closing). Look for: text overflow, overlap with shapes, low-contrast text, off-screen elements.
3. Fix any user-visible defects. Don't chase pixel-perfect — one fix-and-verify cycle is enough.

### Step 6 — Output

Save the final file to:
```
/mnt/user-data/outputs/Capybaras_Proposal_{BrandName}_{YYYY-MM}.pptx
```

Use `present_files` to share it. Keep the post-message short — no long postamble after linking.

**Recommendation for Ramiro:** Before sending the deck to a lead, open it in PowerPoint (with Blauer Nue installed locally) and either (a) export to PDF to lock the font, or (b) embed the font via File → Options → Save → "Embed fonts in the file". Sending raw .pptx to clients without Blauer Nue installed will trigger font substitution and break the visual.

## Capybaras Brand Style (quick reference)

| Token | Hex | Use |
|-------|-----|-----|
| Black | `#0E0E0E` | Dark backgrounds (cover, dividers, closing) |
| Pure black | `#000000` | Rarely; mostly use 0E0E0E |
| Orange | `#FF3300` | Primary accent, divider lines, callouts |
| Light orange | `#E85B03` | Secondary accent, gradients |
| White | `#FFFFFF` | Text on dark, content slide backgrounds |
| Light gray | `#A0A0A0` | Muted text on dark backgrounds |
| Mid gray | `#666666` | Muted text on light backgrounds |

Fonts: `Blauer Nue` (Capybaras brand font, Bold for headers / Regular for body). Sizes: titles 36–44pt, section headers 20–24pt, body 14–16pt, captions 10–12pt.

Full spec in `references/brand-style.md`.

## Important reminders

- The "Why to join Capybaras" copy is fixed wording — do not paraphrase or rewrite without explicit instruction from Ramiro
- The three case studies (Tattoo Care, Wamery, Shapermint) are fixed — do not swap them out unless asked
- All audit numbers must come from the actual audit output. If a number is missing, leave the slide line out rather than fabricate
- When Ramiro provides only a brand name and audit files, do not ask follow-ups about static content — just build with defaults
