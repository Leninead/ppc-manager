---
tipo: sop
actualizado: 2026-04-27
---

# notes/prompts/ — Biblioteca de prompts de Capybaras Agency

Prompts reutilizables versionados, escritos siguiendo los **10 pilares de Anthropic Applied AI** ([Prompting 101](https://docs.claude.com)). Todos los prompts en esta carpeta están en versión v5: rol explícito, tono, background cacheado, reglas paso a paso, output formatting con XML, prefill cuando aplica.

## Tabla de decisión — qué prompt usar

| Situación | Carpeta | Archivo |
|---|---|---|
| Arrancar chat sin cliente específico | `sesion/` | [[arranque-libre]] |
| Arrancar chat con cliente específico | `sesion/` | [[arranque-cliente]] |
| Continuar trabajo de la sesión anterior | `sesion/` | [[arranque-continuar]] |
| Generar reporte semanal de la agencia | `sesion/` | [[arranque-reporte-semanal]] |
| **Cerrar sesión** (genera daily + brand + STATE + git + arranque siguiente) | `sesion/` | ⭐ [[cierre-meta]] |
| Crear módulo nuevo en Streamlit | `codigo/` | [[modulo-nuevo]] |
| Reportar bug y pedir fix | `codigo/` | [[fix-bug]] |
| Actualizar .md de cliente desde Claude Code | `codigo/` | [[update-md-cliente]] |
| Tarea operativa específica que ya resolviste antes | `operativos/` | varios |

## Estructura de carpetas

- **`sesion/`** — meta-flujo de cada chat. Arranque + cierre. Se usa en cada sesión sin excepción.
- **`codigo/`** — prompts para pegar en Claude Code (VS Code) cuando hay que tocar el repo.
- **`operativos/`** — prompts cliente × herramienta × tarea. Ej: anti-borrado de Cowork en Atom11 LTD.

## Convenciones de escritura

Todo prompt nuevo en esta carpeta cumple los 10 pilares de Anthropic en orden:

1. **`<role>`** — quién es Claude en este contexto
2. **`<tone>`** — cómo debe sonar (factual, en español, sin inventar)
3. **`<background>`** — qué archivos del vault leer antes de responder
4. **`<rules>`** — pasos numerados de cómo razonar
5. **`<examples>`** — few-shot cuando hay ambigüedad recurrente (opcional)
6. *Conversation history* — N/A en chats fresh
7. **`<task>`** — el immediate task description, al final del prompt
8. *Thinking* — pedir `<thinking>` cuando la tarea tiene lógica multi-paso
9. **`<output_format>`** — JSON, XML wrapper, o forma específica
10. *Prefill* — sugerir prefill del assistant message cuando se quiere garantizar formato

No todo prompt necesita los 10. Pero si falta alguno, **falta por decisión, no por descuido**.

## Frontmatter obligatorio

```yaml
---
tipo: prompt
actualizado: YYYY-MM-DD
categoria: sesion | codigo | operativo
version: v5
---
```

## Cómo agregar un prompt nuevo

1. Identificá la carpeta correcta (sesión / código / operativo).
2. Copiá la plantilla v5 de un prompt existente de la misma carpeta.
3. Llenalo siguiendo los 10 pilares en orden.
4. Probalo en un chat real antes de mergear — la prueba empírica > la teoría.
5. Actualizá este README si la categoría cambia.

## Histórico

- **2026-04-27** — creada la biblioteca con 5 prompts de sesión + 1 operativo migrado desde raíz de prompts/. Metodología v5 (10 pilares Anthropic Applied AI).

## Referencias cruzadas

- [[CLAUDE]] del vault — convenciones generales
- [[prompts-arranque-sesion]] en `notes/sops/` — versión v3 deprecated, mantener por histórico
- `.claude/agents/sop-writer.md` — agente que ejecuta el cierre de sesión
