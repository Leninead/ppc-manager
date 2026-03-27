---
name: Hardcoded Client Data Issues
description: Critical violations of client data isolation in atom11_rules_builder.py and campaign_builder.py
type: feedback
---

## Issues Found

**Why:** Hardcoded client names and ASINs break multi-client support. Code must accept all client data from user input, not defaults.

**How to apply:** Remove all value= parameters with client-specific data. Use only placeholder= for examples. Only defaults allowed: empty strings, generic numbers (1.0, 10.0, etc.), or technology-agnostic defaults like "Título de página".

## Files with violations

### atom11_rules_builder.py:10-20
_DEFAULT_ASINS contains 9 hardcoded Dermaglos ASINs:
- B0CYLMJJJC (Moisturizing Cream, $9.99)
- B0CYK4G2Y8 (Facial Cleanser, $9.89)
- B0CYLM4L23 (Body Lotion, $18.89)
- B0CYLDSQ5L (Body Cream, $13.49)
- B0F4KXZVNM (2-Pack Cream, $16.99)
- B0CYKDSDJX (Hyaluronic Serum, $18.89)
- B0CYL1RLNQ (Night Cream, $19.79)
- B0F548KTXD (2-Pack Lotion, $32.11)
- B0F6VZMF2V (Skincare Set, $32.90)

Used as default table data — should be empty until user uploads Campaign CSV.

### campaign_builder.py:97-104
Hardcoded defaults in sidebar inputs:
- Line 97: `value="Dermaglos"` in marca input
- Line 98: `value="B0CYLMJJJC"` in asin input
- Line 102: `value=9.99` in precio input (Dermaglos-specific price)

These should all be empty strings or None.

## Exception
Placeholders and examples in help text / st.text_input(placeholder="...") are OK — those are just UI hints.
