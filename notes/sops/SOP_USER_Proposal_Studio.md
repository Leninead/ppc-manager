---
tipo: sop
audiencia: usuario
modulo: M29
modulo_nombre: Proposal Studio
seccion: Sales Director
version: 1.0
fecha: 2026-06-21
autor: lenin-acosta
estado: activo
fuente_verdad: modules/pages/proposal_studio.py (_SOP_MD)
nota: SOP de USUARIO. El SOP técnico/dev es SOP_M29_Proposal_Studio.md (no confundir).
---

### Proposal Studio — cómo usarlo

Arma propuestas comerciales estructuradas para prospectos, combinando bloques que cargás a mano con bloques que se llenan importando archivos. Cada propuesta se guarda y versiona sola en la nube.

Dos pestañas: *Mis propuestas* (listado) y *Nueva propuesta* (asistente).

**PARTE A — Crear la propuesta (asistente, 3 pasos):**
1. Andá a *Nueva propuesta*.
2. **Paso 1 — Cliente:** nombre del cliente, industria (opcional), idioma (Español / Inglés). Siguiente.
3. **Paso 2 — Arquetipo:** elegí el tipo → *Launch* (marca nueva) · *Scale + SEO* (crecer / gap SEO) · *Defense* (defensa de marca) · *CVR* (mejorar conversión) · *Custom* (a medida).
4. **Paso 3 — Revisión:** revisás el resumen y tocás *Crear propuesta*. Se genera con sus bloques y queda guardada (versión 1).

**PARTE B — Completar los bloques (vista detalle):**
Abrí la propuesta desde *Mis propuestas* → *Abrir*.

**Manual vs importar — cómo se reparten los bloques (leé esto):**
No es 'todo a mano' ni 'todo por archivo': **cada bloque se llena por una sola vía** y se complementan. Son independientes — no hay orden obligatorio ni uno depende del otro; llenás cada bloque cuando tengas su data.
- **A mano** (los escribís vos, NO se importan): *Brand Overview* y *Category Overview*.
- **Solo por importación** (NO se pueden escribir a mano, son de solo lectura): *SEO Opportunity*, *Listing — estado actual*, *Listing — comparativa vs competidor* y *Plan de crecimiento*. Vienen del HTML de Ramiro; *SEO Opportunity* además puede venir de DataDive.

Una propuesta completa normalmente lleva **las dos cosas**: lo manual (Brand/Category) + lo importado (el resto).

*B.1 — Bloques manuales (los cargás vos):*
- **Brand Overview** y **Category Overview**: abrí el bloque, completá los campos, *Guardar* (*Descartar* deshace sin guardar). Cada guardado crea una versión nueva.

*B.2 — Importar HTML (auditorías de Ramiro):*
1. Arriba del detalle, abrí el importador de HTML.
2. Subí el HTML de las auditorías (amazon-brand-audit / digital-presence-audit).
3. Mirá la **vista previa**: bloques detectados, warnings y errores. Si hay errores bloqueantes, no aplica → corregí el HTML.
4. Si está OK: *Aplicar merge* → *Confirmar* (2 clics a propósito, para no aplicar sin querer).
5. Llena los bloques de Listing (estado actual / comparativa vs competidor) y el plan de crecimiento, según lo que traiga el HTML.

*B.3 — Importar SEO desde DataDive (Missing Keywords):*
1. Abrí el importador de DataDive.
2. Poné el **ASIN** del cliente (formato B0XXXXXXXX) — si ya importaste el HTML de Listing puede venir precargado, igual lo podés escribir. Hasta que no haya un ASIN válido, el uploader no aparece.
3. Subí el **MKL** (Master Keyword List) exportado de DataDive (.xlsx).
4. Vista previa → *Aplicar* → *Confirmar* (2 clics, igual que arriba).
5. Llena el bloque de SEO Opportunity con las keywords donde el cliente está flojo o no aparece.

**PARTE C — Estado y cierre:**
- Avanzá el estado a medida que progresa: Borrador → Lista para revisión → Enviada → (Ganada / Perdida / Archivada).
- Cada cambio guarda una versión nueva → tenés el historial completo.
- Para ver la propuesta entera, usá *Ver propuesta cruda*.

**Importante:**
- No edites a mano los bloques que se llenan por importación (SEO, Listing, comparativa): su contenido viene de los archivos.
- Si dejás los dos importadores abiertos a la vez y aplicás uno, el otro puede pedirte *Confirmar* — cancelalo, no pasa nada.
