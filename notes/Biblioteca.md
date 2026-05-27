
# SOP — Biblioteca de Conocimientos Capybaras Agency
## Obsidian + Claude: Setup y flujo de trabajo

**Versión:** 1.0  
**Fecha:** 2026-03-20  
**Autor:** Lenin Acosta  
**Equipo:** Capybaras Agency

> 🗓️ [[_cheat-sheet-diario]] — abrir TODAS las mañanas antes de empezar trabajo. Mecánica del workflow multi-frente diario.
> 🚀 [[arranque-universal]] — prompt único para pegar al primer mensaje de cualquier chat nuevo. El chat te conduce paso a paso.

---

## ¿Qué es esto y para qué sirve?

Tenemos una biblioteca de conocimiento estructurada donde guardamos:
- Tendencias de Amazon y eCommerce 2026
- Novedades de AI aplicada a PPC
- Análisis de posts de referentes del sector
- SOPs y frameworks propios de la agencia

Cada pieza de conocimiento se guarda como archivo `.md` (Markdown),
se organiza en Obsidian, y se sube al proyecto de Claude para que
el AI tenga contexto acumulado en todos los chats futuros.

---

## PARTE 1 — Instalación (una sola vez)

### Paso 1 — Descargar Obsidian
- Ir a https://obsidian.md
- Descargar e instalar (versión gratuita es suficiente)
- Ruta de instalación: `C:\Program Files\Obsidian` (default)

### Paso 2 — Abrir la vault del proyecto
Al abrir Obsidian por primera vez:
1. Click en **"Open folder as vault"** → Open
2. Navegar a `C:\proyectos\ppc-manager\notes`
3. Click en **"Select Folder"**

Obsidian va a mostrar las notas existentes en el panel izquierdo:
- DERMAGLOS
- LTD
- MB
- setex

### Paso 3 — Crear la carpeta knowledge
1. Click en el ícono de **carpeta nueva** (segundo ícono arriba a la izquierda)
2. Nombrarla `knowledge`
3. Esta carpeta es donde van TODAS las notas de la biblioteca

---

## PARTE 2 — Flujo de trabajo diario

### Cómo agregar una nota nueva a la biblioteca

**Origen:** post de LinkedIn, artículo, video, investigación propia

**Paso 1 — Mandar el contenido a Claude**
- Copiar el post o artículo
- Pegarlo en el chat del proyecto "Conocimientos + skills" en Claude
- Claude investiga, busca fuentes adicionales y genera el análisis completo

**Paso 2 — Claude genera el .md**
Claude entrega un archivo Markdown con esta estructura:
- Metadata (categoría, fecha, urgencia, fuente)
- Resumen ejecutivo
- Análisis detallado
- Aplicación práctica para Capybaras
- Fuentes con URLs
- Tags

**Paso 3 — Guardar en Obsidian**
1. Abrir Obsidian
2. Click derecho sobre la carpeta `knowledge`
3. Click en **"New note"**
4. Nombrar la nota con el formato: `YYYY-MM-DD-tema-corto`
   - Ejemplo: `2026-03-20-amazon-shop-direct-rufus-prompts`
5. Click dentro del área blanca de la nota
6. **Ctrl+A** para seleccionar todo → borrar
7. Pegar el contenido del .md que generó Claude
8. **Ctrl+S** para guardar

**Paso 4 — Subir al proyecto de Claude**
1. Ir al proyecto "Conocimientos + skills" en Claude
2. En el panel derecho, sección "Archivos" → click en **+**
3. Navegar a `C:\proyectos\ppc-manager\notes\knowledge\`
4. Seleccionar el archivo recién creado → Abrir
5. El archivo queda disponible para Claude en todos los chats futuros

---

## PARTE 3 — Convenciones y estándares

### Nomenclatura de archivos
```
YYYY-MM-DD-tema-en-minusculas-con-guiones.md

Ejemplos:
2026-03-20-amazon-shop-direct-rufus-prompts.md
2026-03-21-claude-mcp-servidores-disponibles.md
2026-03-25-sbv-sponsored-brand-video-estrategia.md
```

### Categorías disponibles
| Categoría | Subcategorías |
|-----------|--------------|
| Amazon | PPC / SEO Listing / Algoritmo / Ads Formats |
| AI | Claude / GPT / Agentes / MCP / RAG |
| AI × Amazon | Automatización PPC / Rufus / Prompts |
| Herramientas | Helium10 / Atom11 / MerchanSpring / DataDive |
| Estrategia | SOP / Frameworks / Clientes |
| eCommerce | DTC / Pricing / Tendencias |

### Niveles de urgencia
- 🔴 Alta — acción esta semana
- 🟡 Media — acción este mes
- 🟢 Baja — referencia futura

### Tags obligatorios en cada nota
Siempre incluir al menos:
- Plataforma: `#amazon` `#claude` `#google`
- Tipo: `#ppc` `#listing` `#ai` `#estrategia`
- Año: `#2026`

---

## PARTE 4 — Estructura de carpetas
```
C:\proyectos\ppc-manager\notes\
│
├── knowledge\          ← BIBLIOTECA (este SOP)
│   ├── 2026-03-20-amazon-shop-direct-rufus-prompts.md
│   └── ...
│
├── DERMAGLOS.md        ← notas de clientes (existente)
├── LTD.md
├── MB.md
└── setex.md
```

---

## PARTE 5 — Proyecto Claude configurado

**Nombre del proyecto:** Conocimientos + skills  
**URL:** claude.ai → Proyectos → Conocimientos + skills

**Archivos subidos al proyecto:**
- `app.py` — contexto del PPC Manager
- `CLAUDE.md` — arquitectura y estado del proyecto dev
- Notas de `knowledge/` — se agregan a medida que se crean

**Instrucciones del proyecto:**
El proyecto tiene configurado a Claude como investigador senior
especializado en AI, Amazon y PPC — no como asistente de desarrollo.

---

## PARTE 6 — Referentes a seguir para alimentar la biblioteca

### LinkedIn (postear contenido para analizar)
- **Bradley Sutton** — Helium 10 VP Education (tendencias Amazon semanales)
- **PPC Ninja** — automatización y AI en Amazon Ads
- **My Amazon Guy** — Steven Pope (estrategia Amazon USA)
- **Incrementum Digital** — Rufus y AI shopping

### Newsletters / blogs
- ppcninja.com/blog
- sellercentral.amazon.com (changelog oficial)
- retailtouchpoints.com
- techcrunch.com (sección Commerce)

---

## RESUMEN DEL FLUJO (versión corta)
```
Post/artículo interesante
        ↓
Pegarlo en Claude (proyecto Conocimientos + skills)
        ↓
Claude investiga + genera .md completo
        ↓
Guardar en Obsidian → knowledge/YYYY-MM-DD-tema.md
        ↓
Subir el .md al proyecto de Claude → Archivos +
        ↓
Biblioteca crece, Claude tiene contexto acumulado
```

---

## Tags
#sop #obsidian #biblioteca #workflow #capybaras #conocimiento #2026

---

## SOPs

- [[SOP_NotebookLM_Capybaras_2026]] — Adopción NotebookLM Google Workspace (v1.0, mayo 2026). 5 use cases priorizados, roadmap 60 días.