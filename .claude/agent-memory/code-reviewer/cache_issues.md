---
name: Missing Cache Decorators
description: Heavy parsing functions lack @st.cache_data for performance
type: feedback
---

**Why:** These functions parse large files (Atom11 CSVs, MerchanSpring PDFs, Business Report files) and should cache results to avoid re-parsing on every interaction.

**How to apply:** Add `@st.cache_data` decorator to each function, or use `@st.cache_data(ttl=3600)` for time-limited cache.

## Functions without cache

| File | Function | Impact |
|------|----------|--------|
| modules/atom11/parser.py | _parse_atom11 | High — Atom11 sheets are large |
| modules/merchanspring/parser.py | _parse_merchanspring | High — XLSX parsing is slow |
| modules/merchanspring/parser.py | _parse_merchanspring_pdf | Very high — PDF parsing is CPU-intensive |
| core/business_report/parser.py | _parse_business_report_map | Medium — scans files at startup |

These should have been cached per CLAUDE.md project spec (line: "Check that file uploaders use caching on heavy parsing functions").
