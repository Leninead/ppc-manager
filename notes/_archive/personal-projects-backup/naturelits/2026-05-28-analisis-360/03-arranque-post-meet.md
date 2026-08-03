# Arranque sesión #2 — Naturelits · Post-meet con Roger

> Copiá este bloque entero como primer mensaje del próximo chat de Claude.
> Generado en cierre de sesión #1 (2026-05-28).

═══════════════════════════════════════════════════════════════
ARRANQUE SESIÓN — NATURELITS · POST-MEET CON ROGER
═══════════════════════════════════════════════════════════════

CONTEXTO PREVIO
La sesión #1 (2026-05-28) cerró con análisis 360 ES completo, auditoría
profunda de 4 listings, HTML deliverable entregado, y meet con Roger
agendada para 29-may 10:00 AM. La sesión terminó SIN ejecutar bulks
porque la decisión fue tratarla como descubrimiento puro, no como venta.

ESTADO AL CIERRE DE LA SESIÓN #1
- ✅ Análisis 360 ES hecho
- ✅ HTML deliverable revisado y limpio (sin referencias a bugs internos
     del software, con proyección mayo a mes completo €54k como cover)
- ✅ Daily `daily/2026-05-28.md` documentado
- ✅ Archivo maestro `naturelits.md` inicializado con KPIs, heroes,
     sangrado, decisiones (DEC-001 a DEC-004), bloqueos (B-001 a B-005)
- ⏳ Backup cruzado en repo Capybaras (DEC-004) — verificar si se ejecutó
- ⏳ Meet con Roger ejecutada (esta sesión arranca POST-meet)
- 🔒 Cero cambios en la cuenta — todo a la espera de Roger

OBJETIVO DE ESTA SESIÓN
Capturar respuestas de Roger a las 5 preguntas críticas y decidir
si avanzamos a propuesta formal de proyecto.

TIPO DE SESIÓN A REGISTRAR EN EL DAILY
Elegir según resultado de la meet:
- `tipo_sesion: ejecución` si Roger autoriza quick wins y se aplican bulks
- `tipo_sesion: mixta` si hay quick wins + diseño de propuesta formal
- `tipo_sesion: estratégica` si no se ejecuta nada en la cuenta y solo
  se diseña la propuesta formal

GUARDIA DE INICIO (correr ANTES de cualquier comando git/cambios)
```
cd C:\proyectos\naturelits-ppc
pwd
git remote -v
git branch --show-current
git status
```
(Si no hubo cambios de código pendientes desde ayer, debería estar limpio.)

PRIMER PASO — CAPTURAR LA MEET
Voy a contarte qué dijo Roger en la meet. Por favor:
1. Leeme el archivo `naturelits/naturelits.md` del vault (en
   C:\obsidian\marcas-personales\) y refrescate las 5 preguntas
   críticas + los 5 bloqueos (B-001 a B-005).
2. Esperá a que te transmita las respuestas pregunta por pregunta.
3. NO generes análisis hasta tener las 5 respuestas. Si Roger no
   respondió alguna, marcala como pendiente y seguimos.

LAS 5 PREGUNTAS CRÍTICAS (recap)
1. ¿Por qué exactamente están OOS los 3 SKUs Serene? (B-001)
2. ¿Quién/qué controla el algoritmo de pricing del Serene? (B-002)
3. ¿La línea Serene Espuma Compacta tiene problema conocido de
   producción/proveedor? (B-003)
4. ¿NATURELITS vs NATURE LITS Exclusive — cuál es la identidad
   oficial? (B-004)
5. ¿Hay budget de proyecto para reabastecimiento + pricing audit
   + listing refresh? (B-005)

DESPUÉS DE CAPTURAR RESPUESTAS — DECIDIR NEXT
Tres caminos posibles según lo que diga Roger:

A) "Sí a todo, avancen" → preparar propuesta formal de proyecto en
   4 fases (Validación + Quick Wins / Pricing + Stock + Listings /
   Construcción PPC / Expansión IT-DE-FR). Definir SOW, timelines,
   pricing del servicio. Avanzar también con los 3 quick wins
   inmediatos (liberar OOB, pausar SP_KT_DEF_MIX, subir 61 negatives).

B) "Sí a algunas cosas, no a otras" → re-scope. Identificar qué
   acciones quedan dentro del alcance posible y cuáles se diferen.
   Priorizar quick wins ejecutables sin las decisiones bloqueadas.

C) "Necesito pensarlo / volvé en X días" → cerrar la sesión solo
   con los 3 quick wins (si autorizó al menos eso) y agendar
   follow-up.

REGLAS DURAS PARA ESTA SESIÓN
- NO push automático del repo Naturelits — Lenin decide cada commit
- NO tocar el vault Capybaras (C:\proyectos\ppc-manager\notes\)
- NO ejecutar bulks sin autorización explícita de Roger sobre cada uno
- Reglas Amazon Bulk siguen vigentes: Campaign ID = Campaign Name,
  Portfolio ID vacío, "Sponsored Products Campaigns" como sheet name,
  filtrar State != archived en UPDATE
- Cualquier bulk a subir → primero copia en `naturelits/bulks/` con
  fecha + descriptor + nota de qué se subió
- Métrica de caída: SIEMPRE −57% acompañado del cover "(proyectado a
  mes completo: ~€54k = −51%)". Nunca presentar −57% solo, nunca
  presentar −51% solo.

CIERRE DE ESTA SESIÓN (modo mega-prompt)
Al terminar, generar UN MEGA-PROMPT PARA CLAUDE CODE que ejecute
todo el cierre de forma atómica:
1. Daily `naturelits/daily/2026-05-29.md` con tipo_sesion correcto
2. Update de `naturelits/naturelits.md`:
   - Resolver los bloqueos B-NNN con la info de Roger
   - Agregar DEC-NNN nuevas que surjan
   - Agregar sesión #2 al histórico
3. Si hubo bulks subidos: registrar en `naturelits/bulks/` con copia
4. Git: commit del vault Obsidian si aplica (sin push)

NO entregar bloques markdown para copy-paste manual. Esa metodología
quedó deprecated desde el cierre de sesión #1.

═══════════════════════════════════════════════════════════════