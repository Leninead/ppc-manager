---
tipo: prompt
actualizado: 2026-05-25
categoria: sesion
subcategoria: cierre
version: v1.0
---

> ⚠️ **REGLA OPERATIVA — sop-writer suspendido**
>
> Tras incidentes 25-26/05 (sop-writer destruyó STATE-agencia −1255 líneas),
> sop-writer NO se usa para:
> - `notes/state/STATE-agencia.md` (cualquier operación)
> - Cualquier archivo >500 líneas
>
> Para esos casos, Edit quirúrgico obligatorio con validación textual:
> - `git diff --stat` ANTES (esperable <50 líneas modificadas)
> - `grep "^## " <archivo>` (verificar headers post-edit)
> - Si `git diff --stat` muestra -200+ líneas → PARAR y `git restore`

# Cierre acotado por chat (multi-frente)

## Cuándo usar

Al final de una sesión que es UNO de N chats paralelos del día. Cada chat
hijo cierra SOLO su frente sin tocar archivos compartidos. El chat
consolidador (último del día) hace el merge final del STATE-agencia + push.

Si la sesión NO es multi-frente (1 solo chat del día), usar `cierre-meta.md`
en lugar de este.

## Prompt copiable

```xml
<role>
Sos asistente senior de Capybaras Agency cerrando una sesión que fue UNO de
N chats paralelos del día. Lenin trabajó múltiples frentes en simultáneo.
Tu trabajo es cerrar SOLO este frente sin pisar el trabajo de los otros chats.
</role>

<tone>
Factual, en español rioplatense. Salida concreta para ejecutar.
</tone>

<background>
Datos que necesitás identificar del contexto del chat:
- ¿Cuál es el slug de TU frente? (m27, m29, dermaglos, setex, etc)
- ¿Qué archivos se modificaron o crearon HOY en este chat?
- ¿Qué decisiones se tomaron?
- ¿Qué quedó pendiente para mañana?
- ¿Qué archivos NO son tuyos? (los otros chats están escribiendo sus
  propios fragments — no toques sus paths)
</background>

<rules_duras>
1. NUNCA tocar `notes/state/STATE-agencia.md` — eso lo hace el consolidador
2. NUNCA hacer `git push` — eso lo hace el consolidador
3. NUNCA hacer `git add .` — siempre `git add <path-específico>`
4. NUNCA pisar archivos de otros frentes (otros arranques, otros brand notes)
5. APPEND al daily — si la sección de TU frente no existe en el daily de
   hoy, crearla. Si existe (porque ya cerraste antes), append al final
   de tu sección, no reescribir
</rules_duras>

<output_format>
Razoná dentro de <thinking>...</thinking>.

Después devolvé exactamente esta estructura, con bloques copiables:

## 📝 1. Prompt para sop-writer — Daily fragment de TU frente

[Apendear a notes/daily/YYYY-MM-DD.md una sección con header
"## {Feature/Cliente}" (ej: "## M29 Proposal Studio" o "## Setex").
Si la sección ya existe, append al final con sub-header de hora.

Contenido a embeber:
- Foco de la sesión
- Commits del frente con SHA + mensaje
- Decisiones cerradas
- Bugs/gotchas nuevos descubiertos
- Pendientes para mañana
- Wikilinks al arranque correspondiente

NO tocar otras secciones del daily (otros frentes están escribiendo en
paralelo).]

## 🎯 2. Prompt para sop-writer — Update arranque del frente

[Editar notes/prompts/sesion/{tipo}/arranque-{slug}.md donde:
- {tipo} = "features" si es módulo M##, "clientes" si es cliente
- {slug} = m27, m29, dermaglos, setex, etc

Update SOLO las secciones dinámicas (NO tocar bloque XML estable ni
"Conocimiento operativo"):

A) "Estado actual": último commit + % avance + sub-bloques cerrados/pendientes
B) "Pendientes activos": re-prioritizar P0→P3 con lo nuevo
C) "Próxima sesión propuesta": bloque concreto a ejecutar + estimación +
   pre-flight
D) "Historial de sesiones": APPEND una línea con fecha + resumen 1 oración
   + wikilink al daily

NO reescribir el archivo, solo editar las 4 secciones dinámicas.]

## 🏷️ 3. Prompt para sop-writer — Brand note (solo si tocó cliente)

[Si TU frente es un cliente (dermaglos/setex/ltd/mb/optipet): apendear
sección "## YYYY-MM-DD — {Resumen}" a notes/brands/{cliente}/{ARCHIVO_PRINCIPAL}.md

Contenido: detalle operativo del día (bulks ejecutados, decisiones tácticas,
ASINs tocados, próximos pasos cliente).

Si TU frente es una feature (M##): saltear este bloque (escribir "N/A —
frente es feature, no cliente").]

## 🔄 4. Git commit ACOTADO (sin push)

cd C:\proyectos\ppc-manager

# IMPORTANTE: paths específicos, NO `git add .`
git add notes/daily/YYYY-MM-DD.md
git add notes/prompts/sesion/{tipo}/arranque-{slug}.md
# si tocó cliente:
git add notes/brands/{cliente}/

git status  # mostrar para verificar que NO hay nada de otros frentes

git commit -m "docs({slug}): cierre {frente} {fecha}

- Daily fragment {frente}
- Update arranque-{slug}.md (estado + pendientes + próxima sesión)
- Brand note {cliente} (si aplica)"

# NO push — el consolidador hace el push al final del día

## 📋 5. Resumen para el consolidador

[{Frente}: {resumen 1 oración}
SHA commit: {hash}
Daily section: notes/daily/YYYY-MM-DD.md ## {sección}
Arranque actualizado: notes/prompts/sesion/{tipo}/arranque-{slug}.md
Brand note: {path} (si aplica) | N/A
Pendientes críticos para mañana: {bullets}]

---
Cierre: una línea final tipo "Frente {slug} cerrado y commiteado local.
Push lo hace el consolidador al final del día."
</output_format>

<task>
Generá los 5 bloques de cierre acotado para ESTE frente.
</task>
```

## Cómo lo dispara el consolidador (chat #N al final del día)

Cuando todos los chats hijos hicieron commit local de su parte, abrís un
chat consolidador con `arranque-libre.md` y le pasás:

```
Hoy 2026-05-25 cerré N frentes paralelos. Los chats hijos commitearon
local (NO push). Working tree debería estar limpio salvo posibles cambios
en STATE-agencia.md o conflictos cross-frente.

1. Leé el daily de hoy completo (todas las secciones)
2. Leé los N arranques actualizados (m27, m29, dermaglos, setex, etc)
3. Generá update quirúrgico de STATE-agencia.md con "Última sesión —
   YYYY-MM-DD" sintetizando los N frentes
4. Verificá wikilinks cruzados (arranques ↔ daily ↔ brand notes)
5. Generá commit final + `git push`
6. Generá reporte: 4 arranques listos para próximas sesiones, qué refrescar
   en Claude project, próximo milestone
```

## Histórico

- 2026-05-25 — v1.0 creado. Resuelve gap del flujo multi-frente que
  cierre-meta original no contemplaba (asumía 1 chat por día).

## Referencias

- [[cierre-meta]] — versión completa para sesiones de 1 solo chat
- [[arranque-libre]] — para el chat consolidador
- [[feature-lifecycle]] — SOP del ciclo de vida de arranques
