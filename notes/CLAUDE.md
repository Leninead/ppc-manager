# CLAUDE.md — Vault de Capybaras Agency

Guía para que Claude Code use este vault como memoria persistente de la agencia. Aplica siempre que trabajés desde la carpeta notes/ o cualquier subcarpeta.

## Propósito del vault

Este vault es el cerebro operativo de Capybaras Agency. Acá vive:

- SOPs y procesos operativos.
- Estado actual de cada cliente activo.
- Diario de sesiones de trabajo.
- Knowledge base de research, tendencias Amazon/eCommerce, learnings del equipo.
- Prompts reutilizables.

Existe en paralelo al repo de código (C:\proyectos\ppc-manager). El CLAUDE.md de la raíz del repo cubre la app Streamlit; este cubre el vault.

## Estructura de carpetas

- Biblioteca.md — índice maestro del vault (homepage)
- brands/ — una carpeta por cliente activo
- daily/ — resúmenes por sesión, nombre YYYY-MM-DD.md
- knowledge/ — research, tendencias, hallazgos
- personal/ — contenido personal de Lenin (LinkedIn, etc.)
- prompts/ — prompts maestros reutilizables
- sops/ — procesos operativos de agencia
- state/ — estado actual (STATE-agencia + STATE por cliente)

## Reglas de escritura

### Convenciones de nombre

- Archivos nuevos: kebab-case (dermaglos-q2-2026.md, no DermaglosQ22026.md).
- Dailies: YYYY-MM-DD.md (2026-04-24.md).
- Knowledge dated: YYYY-MM-DD-slug.md (2026-03-21-amazon-ads-mcp-server.md).
- Archivos existentes con MAYÚSCULAS o espacios (DERMAGLOS.md, PPC-SOP-Manager.md) se dejan como están. No renombrar.

### Frontmatter mínimo obligatorio

Toda nota nueva empieza con un bloque YAML al inicio:

- tipo: uno de (state, sop, daily, knowledge, brand, prompt, personal)
- actualizado: YYYY-MM-DD
- cliente: opcional — solo si la nota es de un cliente específico (dermaglos, ltd, setex, mb, pura-vida-moringa, 360essentials)

Sin otros campos salvo razón específica.

### Wikilinks para conectar notas

Claude usa wikilinks estilo Obsidian al referenciar otras notas:

- Bien: ver [[DERMAGLOS_DATA]] para el detalle histórico
- Bien: aplicamos la regla de [[atom11-template]] con ajustes
- Mal: usar links markdown con rutas relativas

Los wikilinks no necesitan ruta completa ni extensión .md — Obsidian los resuelve por nombre único.

### Notas atómicas

Una idea = una nota. Si estás escribiendo sobre dos temas distintos, son dos notas conectadas por wikilink. Excepción: STATE y brand notes son agregadores por definición.

## Acciones que Claude Code debe ejecutar sin pedir permiso

### 1. Al iniciar una sesión de trabajo

Leer en este orden:

1. notes/Biblioteca.md — índice maestro.
2. notes/state/STATE-agencia.md — estado general.
3. Si hay cliente específico en la tarea: notes/state/STATE-[cliente].md + notes/brands/[cliente]/*.
4. Último daily en notes/daily/ — qué se hizo en la sesión previa.

Responder al usuario con un resumen de 3-5 bullets de dónde quedó el trabajo y cuál es el siguiente paso lógico.

### 2. Al cerrar una sesión de trabajo

Crear o actualizar:

1. Daily de hoy en notes/daily/YYYY-MM-DD.md con: tareas completadas, decisiones tomadas, bloqueos, próximos pasos. Si ya existe el archivo, agregar al final (no pisar).
2. STATE relevante (agencia o cliente específico) si cambió algo sustancial.

Es parte del flujo estándar, no requiere que el usuario lo pida explícitamente.

### 3. Al descubrir un concepto nuevo reutilizable

Crear nota atómica en notes/knowledge/YYYY-MM-DD-slug.md con frontmatter, explicación, ejemplo, y wikilinks a conceptos relacionados si ya existen.

### 4. Al escribir un SOP nuevo

Crear en notes/sops/slug.md. Estructura mínima: propósito, cuándo aplica, pasos numerados, ejemplo, excepciones conocidas.

## Reglas duras

- Nunca pisar un archivo sin leerlo primero. Especialmente STATE y brand notes.
- Nunca crear duplicados. Antes de crear una nota, buscar si ya existe usando Grep/Glob sobre notes/. Si existe, actualizar la existente.
- Validar con git diff --stat antes de anunciar cambios. Regla que aplicamos en código, aplica igual acá.
- Nunca hacer push automático. Los commits se hacen durante la sesión, el push lo hace Lenin al final.

## Excepciones y casos especiales

- Untitled.md — si Obsidian crea uno, eliminarlo inmediatamente, son basura.
- .env y .gitignore dentro de notes/ — no tocar, son config del vault.
- .obsidian/ — no tocar, es config de Obsidian.
- Archivos fuera de las 8 carpetas definidas — reportar antes de crear nada nuevo en raíz. La raíz solo tiene Biblioteca.md + archivos de sistema.

## Reglas LTD MX (actualizado 02/06)

- **Heroes LTD oficial**: 35 ASINs activos (actualizado de 10). Fuente única de verdad: `notes/brands/ltd/LTD.md` sección 🦸 **Heroes oficiales (canónico)** al inicio. NO consultar listas viejas en sesiones previas.
- **Brand notes path canónico**: `notes/brands/{slug}/{BRAND}.md` (subcarpeta), nunca flat `notes/brands/{slug}.md`. Bug detectado 02/06: el path flat causó duplicado de marca LTD.

## Reglas operacionales bulk sheets Amazon (actualizado 02/06)

- **Antes de cualquier bulk Negative PT/KW**: validar dtype de Ad Group ID con `.astype("Int64").astype(str)` o cross-check fallará silenciosamente. Ver `notes/knowledge/2026-06-02-gotcha-bulk-export-adgroup-id-float.md`.
- **Amazon "already exists" en CREATE**: no es falla real, es duplicado preexistente, descartar. Ver `notes/knowledge/2026-06-02-amazon-bulk-error-already-exists.md`.
- **CREATE vs UPDATE rollback**: CREATE procesa row-a-row (falla aislada); UPDATE rollback completo si una row falla. Filtrar `State != archived` antes de UPDATE bulks.