# M29 Proposal Studio · Pitch Deck Interno

> Presentación interna para los Sales Directors de Capybaras Agency.
> Borrador — Mayo 2026.

---

## Qué es

Un pitch deck en HTML dinámico que presenta la propuesta de **M29 Proposal Studio** (módulo nuevo del Agency OS para automatizar las propuestas comerciales que hoy se arman manualmente en PowerPoint).

La presentación misma usa el formato que el módulo va a generar — o sea, los Sales Directors ven en vivo el output al mismo tiempo que escuchan la idea.

## Cómo abrirlo

1. Doble click sobre `index.html` → abre en el browser por defecto
2. **Scroll vertical** para navegar entre slides (scroll-snap entre secciones)
3. **Flechas ↑/↓ o PageUp/PageDown** para navegación con teclado
4. Funciona offline (todo embebido excepto Chart.js + Google Fonts vía CDN)

## Cómo presentarlo

**Modo call**: compartir pantalla, presentar a fullscreen (F11), scrollear con flechas mientras hablás.

**Modo asíncrono**: mandar el archivo .html por mail/Slack — el receptor lo abre y navega solo.

## Estructura — 9 slides

1. **Cover** — M29 Proposal Studio + meta
2. **El Problema** — proceso actual, 4h por propuesta, 0 reuso
3. **La Solución** — 4 pillars del workflow (Selección / Inputs / Render / Export)
4. **Catálogo** — 27 módulos (7 FIXED + 20 VARIABLE) agrupados por categoría con tags por Tool Used
5. **Demo en vivo** — caso real Dermaglós Main Image con KPIs animados + Chart.js
6. **Workflow** — los 4 pasos del sales director (~20 min total)
7. **Stack técnico** — código snippet + features clave del módulo
8. **Roadmap** — 4 fases (MVP → Audits → Market → Auto-poblado)
9. **Closing** — CTA: priorizar 1 VARIABLE para el MVP

## Decisiones de diseño

- **Paleta**: dark (#0a0a0a) + naranja Capybaras (#FF6B35) + topográfico SVG. Coherente con el PDF Sunny Zebra.
- **Tipografía**: Bricolage Grotesque (display) + Geist (body) + JetBrains Mono (data). NO usé Inter ni Space Grotesk.
- **Motion**: scroll-snap mandatory + IntersectionObserver para fade-in escalonado + counters animados al entrar viewport + Chart.js con animation enabled.
- **Diferenciador (slide 4)**: catálogo presentado como grilla por categorías con tags color-coded por herramienta (Manual / Atom11 / Data Dive / H10 / Combo). Es el slide que se acuerda.

## Datos reales usados

- **Slide 5 (Demo Dermaglós)**: data del slide 21 del PDF Sunny Zebra. CTR 0.48% → 0.76% (+58.87%). CVR change +92.85%. ROAS 0.41 → 1.38. Total Sales $79.92 → $224.53.
- **Slide 4 (Catálogo)**: los 27 módulos exactos del Excel `Capybaras_Proposal_Module_Template.xlsx` hoja "Proposal Modules", con sus Tool Used originales.

## Próximos pasos después de presentar

1. Recoger feedback de los Sales Directors sobre **qué VARIABLE arrancamos como piloto** del MVP
2. Confirmar la **lista de 3 propuestas próximas** con las que se va a validar M29
3. Una vez confirmado, este HTML se mueve a `.claude/porting-sources/m29-pitch.html` y el `html-to-streamlit-porter` lo usa como input para portar a `modules/pages/proposal_studio.py`

## Tareas pendientes para la versión final

- [ ] Reemplazar logo Capybaras placeholder por SVG oficial cuando esté disponible
- [ ] Agregar mockup real del UI Streamlit en slide 6 (workflow) — hoy son cards conceptuales
- [ ] Generar versión PDF con Playwright (instalación pendiente)
- [ ] Validar render en Safari + Edge (probado solo en Chrome)

---

**Owner**: Lenin Acosta
**Repo destino**: `Leninead/ppc-manager` → `presentations/m29-proposal-studio-pitch/`
**Stack**: HTML + Chart.js 4.4.1 + Google Fonts (Bricolage Grotesque, Geist, JetBrains Mono)
