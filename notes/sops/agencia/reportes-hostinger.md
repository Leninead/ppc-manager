# SOP — Publicar Reportes de Clientes en Hostinger

**Objetivo:** Subir reportes HTML mensuales al hosting de Capybaras para compartirlos con clientes via URL limpia, sin que vean código ni plataformas externas.

**Resultado final:** `capybarasagency.com/reportes/mb/marzo-2026.html`

---

## Contexto

Los reportes mensuales de clientes se generan como archivos `.html` desde la app PPC Manager. En vez de mandarlos como archivo adjunto o usar plataformas externas (Netlify, GitHub Pages), los hosteamos directamente en el dominio de Capybaras. El cliente recibe una URL limpia, ve el reporte en el browser como si fuera Looker Studio, y no tiene idea de que es un HTML estático.

---

## Pasos

**PASO 1 — Entrás a Hostinger**
- hpanel.hostinger.com → Login
- Panel principal → **File Manager**

**PASO 2 — Creás la estructura de carpetas**
- Entrás a `public_html`
- Click **New Folder** → `reportes`
- Entrás a `reportes` → **New Folder** → `mb`
- Entrás a `mb`

**PASO 3 — Renombrás el HTML antes de subir**
En tu PC renombrás el archivo a algo limpio:
```
marzo-2026.html
```
Sin espacios, sin paréntesis, sin mayúsculas.

**PASO 4 — Subís el archivo**
- Dentro de `public_html/reportes/mb/`
- Click **Upload** → seleccionás `marzo-2026.html`

**PASO 5 — URL lista para compartir**
```
capybarasagency.com/reportes/mb/marzo-2026.html
```

**PASO 6 — Para el cliente**
Lo mandás por WhatsApp o email así:
> "Hola, acá podés ver el reporte de Marzo:
> capybarasagency.com/reportes/mb/marzo-2026"

---

## Estructura de carpetas por cliente

```
public_html/
  reportes/
    mb/
      marzo-2026.html
      abril-2026.html
    ltd/
      marzo-2026.html
    moringa/
      marzo-2026.html
    pv/
      marzo-2026.html
```

Cada cliente tiene su carpeta. Cada mes se agrega un archivo nuevo. URLs siempre limpias.

---

## Privacidad de los reportes

Los reportes no aparecen públicamente en el sitio de Capybaras. Específicamente:

- No aparece en el sitio web de Capybaras
- No hay menú ni link que lleve ahí
- Nadie llega por accidente — solo quien tenga la URL

Sin embargo, cualquiera con la URL exacta puede verlo. Para mayor seguridad hay tres opciones:

**Opción A — Password por carpeta (`.htaccess`)** ✅ Recomendada
La más simple. Hostinger soporta esto nativamente.
- Entrás a File Manager → carpeta `mb`
- Agregás un archivo `.htaccess` con usuario y contraseña
- El cliente abre la URL → le pide password → ve el reporte
- Una contraseña por cliente, la cambiás cuando quieras

**Opción B — Carpeta con nombre secreto**
Sin password pero con URL imposible de adivinar:
```
capybarasagency.com/reportes/x9k2mb-private/marzo-2026.html
```
Nadie la encuentra si no la tenés. Simple pero no es seguridad real.

**Opción C — Google indexing bloqueado** ✅ Recomendada
Agregás un `robots.txt` que le dice a Google que no indexe `/reportes/`. Los humanos con la URL pueden entrar, pero no aparece en búsquedas.

**Recomendación: Opción A + C combinadas**
- `.htaccess` para que pida password → seguridad real
- `robots.txt` para que Google no lo indexe → privacidad extra

### Código listo para usar

**`.htaccess`** — va dentro de cada carpeta de cliente (ej: `public_html/reportes/mb/`):
```apache
AuthType Basic
AuthName "Capybaras Reports"
AuthUserFile /home/u123456789/public_html/reportes/mb/.htpasswd
Require valid-user
```

**`.htpasswd`** — mismo directorio, generás la contraseña en: https://www.web2generators.com/apache-tools/htpasswd-generator
```
mb_client:$apr1$xyz...hash...
```

**`robots.txt`** — va en `public_html/`:
```
User-agent: *
Disallow: /reportes/
```

---

## Mientras tanto (antes de tener acceso a Hostinger)

Usar **GitHub Pages** como solución transitoria:
- Repo: `github.com/Leninead/capybaras-reportes-mb`
- URL activa: `leninead.github.io/capybaras-reportes-mb/marzo-2026.html`
- Subir HTMLs directamente desde la interfaz de GitHub

---

*Creado por Lenin Acosta · Capybaras Agency · Abril 2026*
