# 🤝 Reunión con Edu — 2026-03-23

**Proyecto:** Amazon PPC Manager · Capybaras Agency OS  
**Participantes:** Lenin Acosta · Edu  
**Fecha:** 2026-03-23  
**Estado:** 🟡 Pendiente de completar

---

## 📌 Contexto previo

El PPC Manager arrancó como un archivo único (`app.py` de ~4.000 líneas) y hoy está completamente modularizado: `app.py` tiene ~200 líneas de router y el resto vive en `core/` y `modules/`. Se completaron 9 de 12 sesiones del roadmap inicial.

**Estado actual del producto:**

| Módulo | Estado |
|--------|--------|
| 🏠 Agency OS (inicio + sidebar) | ✅ rediseñado |
| 📊 Search Term Report + Negatives Mining + Harvest | ✅ completo |
| 🔍 Search Query Performance + Market Share | ✅ completo |
| 🔗 Análisis Cruzado STR vs SQP + Plan de Acción | ✅ completo |
| 📁 Bulk Campañas + Campaign Analyzer | ✅ completo |
| 🧠 Bid Optimizer | ✅ nuevo |
| 🚀 Campaign Builder | ✅ nuevo |
| 🔬 Atom 11 Reports | ✅ completo |
| 🛡️ MerchanSpring Reports | ✅ completo |
| 📊 Weekly Client Report | ✅ completo |
| ⏳ Atom11 Rules Builder | 🔲 pendiente |
| ⏳ Account Pulse | 🔲 pendiente |

---

## 🎯 Agenda propuesta

### 1. Demo del producto actual
- [ ] Recorrido por el sidebar oscuro y la pantalla de inicio (Agency OS)
- [ ] Demo módulos PPC: STR → SQP → Análisis Cruzado → Bid Optimizer
- [ ] Demo Campaign Builder (genera bulk listo para subir a Amazon)
- [ ] Demo Weekly Client Report (Love to Dream + M&B como ejemplos reales)

### 2. Revisión de clientes activos
- [ ] **DERMAGLOS** — Estado campañas, pendientes de negativización y harvest
- [ ] **LTD (Love to Dream)** — BuyBox issues activos, SBV con ACoS 148%
- [ ] **MB** — BuyBox masivo (21 ASINs), situación pricing

### 3. Roadmap — Próximas sesiones
- [ ] **Sesión 10 — Atom11 Rules Builder:** exportar reglas de automatización directamente desde el app
- [ ] **Sesión 11 — Account Pulse:** monitor de salud diaria de cuentas
- [ ] **Sesión 12 — SOP completo:** documentar todas las tabs como SOP Capybaras Agency

### 4. Decisiones pendientes
- [ ] ¿Priorizamos Account Pulse o Atom11 Rules Builder primero?
- [ ] ¿Sumamos algún cliente nuevo al Weekly Report?
- [ ] ¿Hay features que Edu usa en otras herramientas que queramos replicar acá?
- [ ] ¿Abrimos el acceso del app a más gente del equipo? (deploy en Streamlit Cloud)

---

## 💬 Notas de la reunión

> *(Completar durante / después de la reunión)*

### Decisiones tomadas
-
-
-

### Acciones definidas
| Acción | Responsable | Fecha límite |
|--------|-------------|--------------|
| | | |
| | | |

### Pendientes para la próxima sesión de dev
-
-

---

## 🔗 Referencias rápidas

- App local: `python -m streamlit run app.py` en `C:\proyectos\ppc-manager`
- Roadmap completo: `CLAUDE.md` en el proyecto
- Clientes: `DERMAGLOS.md` · `LTD.md` · `MB.md` · `setex.md`

---

#reunion #capybaras #ppc-manager #roadmap #2026
