---
tipo: meeting
actualizado: 2026-05-22
fecha: 2026-05-22
sesion: setup-notebooklm-capybaras
generado-por: Claude Cowork
---

# Reporte Cowork — Setup NotebookLM Capybaras

**Fecha:** 2026-05-22  
**Sesion:** Setup completo NotebookLM — Lenin Acosta

---

## Resumen de status por fase

| Fase | Descripcion | Status |
|------|-------------|--------|
| FASE 0 | Pre-flight checks | OK |
| FASE 1 | Vault updates (SOP + daily + STATE + Biblioteca + CLAUDE.md + prompts) | OK |
| FASE 2 | Generacion de PDFs desde markdown | OK — 53/53 |
| FASE 3 | Estructura Google Drive | OK |
| FASE 4 | Paquetes de fuentes + manifests | OK con pendientes manuales |
| FASE 5 | Git commit + push | Parcial (*) |
| FASE 6 | Reporte ejecutivo | OK |

---

## Completado automaticamente

### Repo — archivos creados/modificados

**Nuevos:**
- `notes/sops/SOP_NotebookLM_Capybaras_2026.md` (631 lineas, v1.0)
- `notes/prompts/notebooklm/README.md` (placeholder)
- `outputs/pdfs/notebooklm/` (53 PDFs + 4 manifests)

**Modificados:**
- `notes/daily/2026-05-22.md` — seccion NotebookLM agregada al final
- `notes/state/STATE-agencia.md` — bullet adoption NotebookLM en seccion "Conocimiento operativo"
- `notes/Biblioteca.md` — seccion "## SOPs" con entrada NotebookLM
- `notes/CLAUDE.md` — seccion "## SOPs activos" con referencia al SOP

**Commit checkpoint:** `15c5e81` — "checkpoint: antes de setup NotebookLM"  
*Nota: el commit final de los cambios requiere paso manual (ver abajo).*

---

### PDFs generados

**Total: 53 archivos** (engine: xhtml2pdf + markdown, fondo blanco, sin emojis para compatibilidad NotebookLM)

| Carpeta | Archivos |
|---------|----------|
| outputs/pdfs/notebooklm/agencia/ | 11 PDFs (7 SOPs + Biblioteca + STATE + CLAUDE + INTELLIGENCE-INDEX) |
| outputs/pdfs/notebooklm/agencia/knowledge/ | 11 PDFs (todas las notas de knowledge/) |
| outputs/pdfs/notebooklm/agencia/daily/ | 23 PDFs (dailies sustanciales >20 lineas, mas recientes) |
| outputs/pdfs/notebooklm/ltd/ | 1 PDF (brand-LTD.pdf) |
| outputs/pdfs/notebooklm/dermaglos/ | 4 PDFs (brand notes + atom11-rules + skus) |
| outputs/pdfs/notebooklm/setex/ | 3 PDFs (brand-setex + atom11-rules + PENDIENTES_RESTOCK) |

Conversiones fallidas: 0

---

### Google Drive — estructura creada

```
/Capybaras/ (ID: 1VQvIvW6st1IQc90E134mnTXNbp7C0RVY)
└── NotebookLM/ (ID: 1-elAjvtcqe1i8J2ra8rbjgQttvtL32zc)
    ├── 00-SOP-Maestro/
    │   └── SOP_NotebookLM_Capybaras_2026.md  [SUBIDO]
    ├── 01-clientes/
    │   ├── ltd/
    │   │   ├── fuentes/
    │   │   │   ├── _MANIFEST.md  [SUBIDO]
    │   │   │   └── data-bruta/
    │   │   └── outputs-notebook/
    │   ├── dermaglos/
    │   │   ├── fuentes/
    │   │   │   ├── _MANIFEST.md  [SUBIDO]
    │   │   │   └── data-bruta/
    │   │   └── outputs-notebook/
    │   └── setex/
    │       ├── fuentes/
    │       │   ├── _MANIFEST.md  [SUBIDO]
    │       │   └── data-bruta/
    │       └── outputs-notebook/
    ├── 02-sales-prep/
    │   └── _plantilla/
    ├── 03-knowledge-agencia/
    │   ├── fuentes/
    │   │   └── _MANIFEST.md  [SUBIDO]
    │   ├── sops-pdf/
    │   ├── daily-recientes/
    │   └── outputs-notebook/
    └── 04-training-equipo/
        └── _plantilla/
```

**Archivos subidos a Drive:**
- `SOP_NotebookLM_Capybaras_2026.md` → 00-SOP-Maestro/
- `_MANIFEST.md` (x4) → fuentes/ de cada notebook

**PDFs en local** (subir manualmente a Drive o directo a NotebookLM):
- `C:\proyectos\ppc-manager\outputs\pdfs\notebooklm\` — 53 archivos listos

---

## Acciones manuales pendientes para Lenin

### A) Git commit + push (2 min)

El sandbox no puede hacer push porque no tiene credenciales de GitHub.
Abrir PowerShell en `C:\proyectos\ppc-manager` y ejecutar:

```powershell
git add notes/sops/SOP_NotebookLM_Capybaras_2026.md
git add notes/daily/2026-05-22.md
git add notes/state/STATE-agencia.md
git add notes/Biblioteca.md
git add notes/CLAUDE.md
git add notes/prompts/notebooklm/README.md
git add outputs/pdfs/notebooklm/
git commit -m "docs: SOP NotebookLM v1.0 + setup completo Drive + paquetes fuentes"
git push
```

*Nota: si hay un index.lock residual, ejecutar primero:*
```powershell
Remove-Item .git\index.lock -Force
```

---

### B) Permisos en Drive (5 min)

Abrir https://drive.google.com/drive/folders/1SY6fxuRN6qHsUl0tGopN3iPuJYRG__dn (01-clientes) y setear:

- `/01-clientes/ltd/` → Agustin (edit) + Adam (view)
- `/01-clientes/dermaglos/` → Edu (edit)
- `/01-clientes/setex/` → Edu (edit)
- `/03-knowledge-agencia/` → Ramiro (edit) + Freddy (view)
- `/02-sales-prep/` → Freddy (view)

---

### C) Subir PDFs a Drive (10 min)

Abrir el explorador en `C:\proyectos\ppc-manager\outputs\pdfs\notebooklm\` y arrastrar:

- Carpeta `agencia/` → `/Capybaras/NotebookLM/03-knowledge-agencia/fuentes/`
- Carpeta `ltd/` (brand-LTD.pdf) → `/Capybaras/NotebookLM/01-clientes/ltd/fuentes/`
- Carpeta `dermaglos/` (4 PDFs) → `/Capybaras/NotebookLM/01-clientes/dermaglos/fuentes/`
- Carpeta `setex/` (3 PDFs) → `/Capybaras/NotebookLM/01-clientes/setex/fuentes/`

Para Setex: mover tambien `Setex_Atom11_Rules_v2026_3_22May.xlsx` de Drive raiz a `/01-clientes/setex/fuentes/`
(ID Drive: `1w52e6dkANglU1qZ9Dx05KXpw63e9c3UzhUy2ZB2-hYs`)

---

### D) Completar fuentes manuales por cliente (30 min total)

Ver los `_MANIFEST.md` en cada carpeta de fuentes para checklist especifico. Resumen:

**LTD** — descargar de Amazon + Atom 11:
- BR ultimos 3 meses, SQP x4 semanas, STR 90d, Bulk export, Inventory Report
- Atom 11 rules export LTD
- Redactar PDF contrato antes de subir

**Dermaglos** — descargar de Amazon + Atom 11:
- BR ultimos 3 meses, SQP x4 semanas, STR 90d, Bulk export, Inventory Report
- Atom 11 v2026.3 rules export (24 DEC rules nuevas)
- Verificar si Edu ejecuto DG_Atom11_v2026_2_ENTREGABLE.xlsx

**Setex** — descargar de Amazon + esperar Neha:
- BR, SQP, STR, Bulk export (esperar 24hs post-22/05), Inventory
- Atom 11 v2026.3 rules — confirmar con Neha prefix STX + schedule

---

### E) Crear los 4 notebooks en NotebookLM (20 min total)

Ir a `notebooklm.google.com` → "Crear cuaderno":

**1. intel-agencia-q2-2026**
- Boton "Drive" → seleccionar todos los archivos de `/Capybaras/NotebookLM/03-knowledge-agencia/fuentes/`
- Priorizar si >50: SOPs + STATE + knowledge + dailies mayo
- Generar Audio Overview + Mind Map → validar que indexo bien
- NO compartir con el equipo todavia — pilot personal dias 1-7

**2. onboarding-ltd-2026-05**
- Primero completar fuentes manuales del paso D
- Boton "Drive" → seleccionar `/Capybaras/NotebookLM/01-clientes/ltd/fuentes/`
- Compartir con Agustin (editor) + Adam (viewer)
- Generar Audio Overview + Mind Map + Briefing Doc

**3. onboarding-dermaglos-2026-05**
- Fuentes → `/Capybaras/NotebookLM/01-clientes/dermaglos/fuentes/`
- Compartir con Edu (editor)
- Generar Audio Overview + Briefing Doc

**4. onboarding-setex-2026-05**
- Esperar confirmacion Neha (Atom 11 prefix STX)
- Fuentes → `/Capybaras/NotebookLM/01-clientes/setex/fuentes/`
- Compartir con Edu (editor)
- Generar Audio Overview + Briefing Doc

---

### F) Refresh proyecto Claude (3 min)

1. claude.ai → proyecto ppc-manager
2. Panel derecho → "Add content from GitHub"
3. Refrescar:
   - notes/sops/SOP_NotebookLM_Capybaras_2026.md
   - notes/daily/2026-05-22.md
   - notes/state/STATE-agencia.md
   - notes/Biblioteca.md
   - notes/CLAUDE.md
   - notes/prompts/notebooklm/README.md
4. Confirmar check verde

---

### G) Pilot personal — Semana 1 (dias 1-7)

- Abrir intel-agencia-q2-2026 todos los dias
- 3-5 queries reales sustituyendo busqueda manual en vault
- Anotar tiempo ahorrado por query (estimado vs busqueda manual)
- Capturar los 5 prompts ganadores → popular `notes/prompts/notebooklm/`
- Decision Go/No-Go preliminar el dia 7 (2026-05-29)

---

## Gaps detectados

- **PDFs grandes en Drive:** los PDFs se generaron localmente pero no se subieron a Drive automaticamente (los archivos binarios son demasiado grandes para el contexto del MCP). Se suben con drag & drop en 10 min (paso C).

- **Git push:** el sandbox no tiene credenciales GitHub. El commit definitivo se hace manualmente en PowerShell (paso A). El checkpoint `15c5e81` ya esta committeado con el SOP.

- **Setex onboarding bloqueado parcialmente:** esperar confirmacion Neha (prefix STX + Atom 11 schedule). El notebook se puede crear con lo disponible y agregar el rules export cuando llegue.

- **Sin gaps en vault:** todos los archivos esperados existian. No hubo archivos faltantes que requirieran stop.

---

## Proximo milestone

**Dia 7 (2026-05-29):** Review pilot personal + decision Go/No-Go preliminar.  
**Dia 60 (2026-07-22):** Decision Go/No-Go formal. ROI target: >2 hs ahorradas por semana sostenido.

---

*Reporte generado por Claude Cowork — 2026-05-22*
