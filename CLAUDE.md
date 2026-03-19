# CLAUDE.md
## Proyecto: Amazon PPC Manager
**Agencia:** Capybaras Agency
**Dev:** Lenin Acosta
**Ruta local:** C:\proyectos\ppc-manager
**Comando:** python -m streamlit run app.py
**Stack:** Python + Streamlit + Pandas + OpenPyXL + pdfplumber + anthropic
**Arquitectura:** app.py (~200 lineas router) + core/ + modules/

## Setup
pip install streamlit pandas openpyxl pdfplumber anthropic python-dotenv

API Key — configuracion permanente Windows:
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "tu-key", "User")

Si no funciona en la sesion, setear antes de arrancar:
$env:ANTHROPIC_API_KEY = "tu-key"
python -m streamlit run app.py

NUNCA mostrar la API key en el chat.

## BUG ACTIVO — API key no carga (2026-03-19)
Sintoma: "API key no configurada" aunque este seteada en Windows y en .env
Lo intentado: load_dotenv path absoluto, SetEnvironmentVariable User, override=False, leer .env manualmente — nada funcionó
Hipotesis: Streamlit corre en subproceso que no hereda variables de entorno del usuario Windows
Proximo paso: cerrar VS Code completamente, reabrir, y probar:
python -c "import os; print(os.environ.get('ANTHROPIC_API_KEY', 'NO ENCONTRADA')[:20])"
Si dice NO ENCONTRADA — Windows no propago la variable. Reabrir VS Code resuelve.

## Estructura de navegacion — Estado 2026-03-19
1 Inicio — completo
2 Search Term Report — completo + Negatives Mining + Harvest + Analisis IA
3 Search Query Performance — completo + Market Share + Gap Analysis + Analisis IA
4 Bulk Campanas — completo
5 Business Report — completo
6 Analisis Cruzado STR vs SQP — completo
7 Tendencia Multi-Semana — completo
8 Analisis de Funnel — completo
9 Reportes Atom 11 — completo
10 Reportes MerchanSpring — completo
11 Weekly Client Report — completo + Analisis IA

## Modulos extraidos
core/i18n.py | core/constants.py | core/helpers.py | core/business_report.py
core/ai_analyze.py — _claude_analyze, _build_sqp_prompt, _build_str_prompt
modules/atom11/ | modules/merchanspring/ | modules/pages/ (todos)
modules/pages/weekly_client_report.py — con Analisis IA

Pendiente: Bug tendencia_multisemana.py KeyError con SQPs iguales

## Claude API — core/ai_analyze.py
Modelo: claude-sonnet-4-6
_claude_analyze(prompt, max_tokens=800) — retorna string analisis
_build_sqp_prompt(market_df, gap_df, client_name, brand) — 5 secciones
_build_str_prompt(neg_df, harv_df, client_name, cvr, target_acos) — 4 secciones
Costo: menos de $0.01 por analisis. 10 cuentas = ~$3/mes

## STR — 4 Sub-tabs
Tab 2 Negatives Mining:
clicks_threshold = max(10, round((1 / (cvr/100)) * 2))
spend_threshold = precio_producto * 0.50
imp_threshold = 2500 | ctr_threshold = 0.18
NUNCA negar dentro de Exact Match propia

Tab 3 Harvest Candidates:
harvest_main = orders >= 3 and acos <= 25.0
harvest_cvr = cvr >= 10.0 and clicks >= 15
harvest_vol = orders >= 5
bid_sugerido = (cvr/100) * precio * (target_acos/100)

Tab 4 Analisis IA: llama _build_str_prompt, output 4 secciones, botones txt + Slack

## SQP — 4 Sub-tabs
Tab 2 Market Share: IS > 30% Dominando | 10-30% Competitivo | <10% Oportunidad
Tab 3 Gap Analysis: Tipo1 brand_imp==0 | Tipo2 market_cvr > brand_cvr*1.5 | Tipo3 IS<5%
Tab 4 Analisis IA: llama _build_sqp_prompt, output 5 secciones

## Weekly Client Report
Inputs: BR diario 14d + BR by Child + Atom 11 ASIN + Campaign CSV
Analisis IA: boton post-Excel, output SITUACION/HIGHLIGHTS/ATENCION/PROXIMOS PASOS
Clientes probados: LTD ACoS 22.7% | M&B ACoS 8.6%

## SOP Thresholds 2026
clicks_neg = max(10, round((1/cvr)*2)) | spend_neg = precio*0.50
imp_ctr = 2500 | ctr_min = 0.18
harvest: orders>=3 acos<=25 | cvr>=10 clicks>=15 | orders>=5
Placement: Exact Ranking ToS+50% | Exact Harvest ToS+25% | PAT PDP+50%

## Clientes activos 2026-03-19
Love To Dream MX — ACoS 22.7% TACoS 17.4% | notes/LTD.md
M&B Mott & Bow MX — ACoS 8.6% TACoS 5.4% | notes/MB.md
Setex Technologies MX — revision 27/03 | notes/setex.md
Dermaglos USA — ACoS 76.1% CVR 11.5% nicho vitamin a cream | notes/DERMAGLOS.md

## Dermaglos Plan de ataque 2026-03-19
Fase 1 COMPLETADA: listing optimizado STR+SQP+Rufus
B0CYLMJJJC nuevo titulo: Dermaglos Vitamin A Cream | Overnight Skin Renewal with Allantoin & Vitamin E | Moisturizer for Stretch Marks, Tattoo Aftercare, Scar Treatment & Dry Skin | Fragrance Free | 1.76 oz
B0CYLM4L23 nuevo titulo: Dermaglos Vitamin A Body Lotion | Daily Moisturizer with Allantoin & Vitamin E | Lightweight Hydration for Dry Skin, Stretch Marks, Tattoo Aftercare & Scar Treatment | Fragrance Free | 13.52 Fl Oz
PDF: Dermaglos_Listing_Optimization_2026.pdf
Fase 2 PENDIENTE: estructura campanas + bulk Campaign Manager
Fase 3 PENDIENTE: rules Atom 11 formato bulk

## Roadmap Next Steps
0 FIX URGENTE: API key bug — Analisis IA no funciona | URGENTE
1 Health Check en Bulk | pendiente
2 Accion sugerida + Bulk output en Cruzado | pendiente
3 Account Pulse tab nueva | pendiente
4 Bid Optimizer tab nueva | pendiente
5 Funnel Builder upgrade | pendiente
6 Bulk Upload Builder | pendiente
7 Automation Rules Builder Atom 11 | pendiente
8 Dermaglos Fase 2 campanas | pendiente
9 Dermaglos Fase 3 rules Atom 11 | pendiente
10 Deploy equipo completo | pendiente
11 Slack integration Weekly Report | pendiente

Vision SaaS: $99-299/mes por agencia. 20 agencias = $2,000-6,000 MRR.

## Reglas de trabajo

Flujo codigo:
1. Claude chat disena y redacta el prompt
2. Lenin copia en Claude Code VS Code
3. Claude Code ejecuta con autonomia absoluta
4. Claude Code confirma que modifico

Flujo actualizacion .md de clientes:
1. Claude chat genera el contenido nuevo
2. Claude chat redacta UN prompt para Claude Code
3. Lenin pega en Claude Code (10 segundos)
4. Claude Code escribe en C:\proyectos\ppc-manager\notes\
5. git add + commit + push
NUNCA usar scripts update_X.py ni copiar manualmente.

Formato prompt actualizar .md:
Crear o reemplazar C:\proyectos\ppc-manager\notes\[Cliente].md
con el contenido exacto entre ---INICIO--- y ---FIN---
No tocar ningun otro archivo. Confirmar lineas escritas.

## Git
Inicio sesion: git add . && git commit -m "checkpoint: antes de [tarea]"
Final sesion: git add . && git commit -m "feat/fix/docs: [desc]" && git push
Rompio algo: git checkout . | git diff app.py
