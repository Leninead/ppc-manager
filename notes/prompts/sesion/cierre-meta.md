---
tipo: prompt
actualizado: 2026-04-27
categoria: sesion
version: v5
---

# ⭐ Meta-prompt de cierre

## Cuándo usar

Al final de cada sesión de trabajo, antes de cerrar el chat. Este es el prompt que pegás para que Claude lea TODO el contexto de la sesión actual y te devuelva, listos para copiar:

1. **3 prompts personalizados del sop-writer** — daily + brand note + STATE quirúrgico
2. **El comando git exacto** con mensaje descriptivo
3. **Recordatorio del refresh en proyecto Claude** (paso que se olvida y rompe la próxima sesión)
4. **El prompt de arranque para el próximo chat** — formato v5 personalizado

## Por qué este prompt es la pieza clave

Antes de tener este meta-prompt, al cerrar sesión vos tenías que acordarte:
- Qué decir en el daily, en qué tono, con qué estructura
- Si tocaste un cliente, qué actualizar en su brand note
- Si cambió algo sustancial, cómo editar STATE-agencia sin pisar lo que ya está
- El comando git con un mensaje que tenga sentido
- El paso de "Add content from GitHub" en el proyecto (sin esto, próxima sesión arranca ciega)
- Cómo formatear el prompt de arranque para retomar mañana

Ahora pegás este prompt y Claude te genera los 6 artefactos de una. **De 5 minutos de mecánica al cierre → 30 segundos.**

## Prompt copiable

```xml
<role>
Sos el asistente de cierre de sesión de Lenin Acosta (Capybaras Agency).
Tu único trabajo en este momento es generar los artefactos exactos que necesita
para cerrar este chat de forma profesional y arrancar el siguiente sin fricción.
</role>

<tone>
Operativo, en español rioplatense. Cero relleno. Los artefactos son para copiar
y pegar — si metés explicación de más, Lenin tiene que limpiarla.
</tone>

<background>
Lenin trabaja con el repo C:\proyectos\ppc-manager conectado al proyecto Claude
vía GitHub (Leninead/ppc-manager rama main). El vault Obsidian vive en notes/.

Carpetas críticas que tienen que quedar actualizadas al cierre:
- notes/daily/YYYY-MM-DD.md (resumen de la sesión)
- notes/brands/{cliente}/*.md (si la sesión tocó un cliente)
- notes/state/STATE-agencia.md (si cambió algo sustancial)

Convenciones del vault:
- Frontmatter YAML obligatorio (tipo, actualizado)
- Wikilinks estilo [[Obsidian]] para referenciar otras notas
- Kebab-case para archivos nuevos
- Una idea = una nota (atómicas), excepto STATE y brand notes (agregadores)

Flujo de sincronización tiene 3 puntos de fallo:
1. commit local → 2. push a GitHub → 3. refresh manual en proyecto Claude
Si saltás cualquiera, el próximo chat no ve los cambios.

Slugs de cliente válidos: dermaglos, ltd, mb, setex, 360essentials, pura-vida-moringa.
</background>

<rules>
1. Leé el contexto de ESTE chat. Identificá:
   - ¿Qué cliente(s) tocamos? (si ninguno, marcá "agencia")
   - ¿Qué archivos se modificaron o crearon?
   - ¿Qué decisiones técnicas/negocio se tomaron?
   - ¿Qué bugs/gotchas aparecieron?
   - ¿Qué quedó pendiente para próxima sesión?

2. Generá 3 prompts del sop-writer YA PERSONALIZADOS — no plantillas vacías.
   Cada uno debe tener el contenido específico de hoy embebido.

3. Generá el comando git con mensaje descriptivo en formato:
   `feat/fix/improve/docs: [resumen concreto de la sesión]`
   El mensaje debe ser legible meses después.

4. Generá el prompt de arranque para el próximo chat. Si la sesión tocó un
   cliente, usar formato de [[arranque-cliente]] con el slug embebido. Si fue
   agencia/repo, usar [[arranque-libre]]. Si quedó algo a medias y la próxima
   sesión es continuación, agregar contexto específico.

5. Si la sesión NO tocó código ni clientes (ej: solo lectura, sin cambios),
   indicalo y omití el daily — respetá la regla "decidir por valor, no por ritual".
</rules>

<output_format>
Razoná dentro de <thinking>...</thinking>.

Después devolvé exactamente esta estructura, con bloques de código copiables:

## 📝 1. Prompt para sop-writer — Daily de hoy

```
[prompt completo personalizado, listo para pegar al chat]
```

## 🏷️ 2. Prompt para sop-writer — Brand note (si aplica)

```
[prompt para actualizar notes/brands/{cliente}/*.md, o "N/A — sesión sin cliente"]
```

## 🎯 3. Prompt para sop-writer — STATE-agencia quirúrgico

```
[prompt con instrucciones de qué editar EXACTO en STATE-agencia, o "N/A — sin cambios sustanciales"]
```

## 🔄 4. Git commit + push

```bash
cd C:\proyectos\ppc-manager
git add .
git commit -m "[mensaje descriptivo concreto de hoy]"
git push
```

## ⚠️ 5. Refresh proyecto Claude (CRÍTICO)

Después del push:
1. Ir a claude.ai → proyecto ppc-manager
2. Panel derecho → "Add content from GitHub"
3. Seleccionar/refrescar los archivos modificados:
   [lista de archivos específicos modificados hoy]
4. Confirmar que aparece check verde de sincronización

**Sin este paso, el próximo chat arranca con contexto desactualizado.**

## 🚀 6. Prompt de arranque para el próximo chat

```xml
[prompt v5 completo personalizado, embebido con contexto de continuidad si aplica]
```

---
Cierre: una línea final del tipo "Sesión cerrada. Próximo arranque: [fecha estimada o 'cuando puedas']."
</output_format>

<task>
Generá los 6 bloques de cierre para esta sesión.
</task>
```

## Cómo se ve en práctica — ejemplo real

Imaginá que cerrás una sesión de 2 horas trabajando con LTD donde ejecutaste Fase 4 del plan, encontraste un bug en `campaign_builder.py` y agregaste una nueva regla de negocio. El meta-prompt te devuelve:

```
## 📝 1. Prompt para sop-writer — Daily de hoy

Actualizá notes/daily/2026-04-27.md con esta sesión. Frontmatter:
tipo=daily, actualizado=2026-04-27.

Contexto inicial: continuación del plan 6 fases LTD. Sesión enfocada en Fase 4
(push hard heroes) + bug fix en campaign_builder.py.

Commits del día:
- abc1234 — feat(ltd): bulk EXACT 5 héroes con queries SQP-validadas
- def5678 — fix(campaign-builder): _validate_brand_entity() corregido para SBV

Decisiones tomadas:
- ...
[etc, ya pre-completado por Claude con la data real del chat]

## 🏷️ 2. Prompt para sop-writer — Brand note

Apendear a notes/brands/ltd/LTD.md sección "27/04/2026 — Fase 4 ejecutada"
con: [lista de campañas creadas, bids aplicados, owners pendientes]
[etc]

## 🎯 3. Prompt para sop-writer — STATE-agencia quirúrgico

Editar notes/state/STATE-agencia.md sección "LTD progreso 25/04 cierre completo":
- BUSCAR: "⏳ Fase 4 push hard héroes (60-90 min)" 
- REEMPLAZAR POR: "✅ Fase 4 cerrada 27/04 — bulk 5 EXACT subido (Batch UUID xxx)"
[etc]

## 🔄 4. Git commit + push

cd C:\proyectos\ppc-manager
git add .
git commit -m "feat(ltd): cierre Fase 4 plan 6 fases + fix _validate_brand_entity SBV"
git push

## ⚠️ 5. Refresh proyecto Claude

Archivos a refrescar:
- notes/daily/2026-04-27.md
- notes/brands/ltd/LTD.md
- notes/state/STATE-agencia.md
- modules/pages/campaign_builder.py

## 🚀 6. Prompt de arranque para el próximo chat

[prompt arranque-cliente v5 con cliente=ltd y contexto "venimos de cerrar Fase 4,
próximo paso es Fase 6 (compliance + cliente) delegada a equipo"]
```

## Histórico

- **2026-04-27** — creado. Es la pieza nueva que no existía en el flujo anterior. Reemplaza el "checklist de cierre" de `CLAUDE.md` raíz por un meta-prompt automatizable.
