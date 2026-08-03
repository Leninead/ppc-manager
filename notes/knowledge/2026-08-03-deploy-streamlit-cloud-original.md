---
tipo: knowledge
actualizado: 2026-08-03
tags: [deploy, streamlit-cloud, setup, auth, historico]
---

# Deploy a Streamlit Cloud — know-how del setup original

> Extraído de `setup_deploy.py` antes de archivarlo (Fase 2 orden vault). El
> script era destructivo; esta nota conserva el conocimiento sin el riesgo.
> Volcar a `SETUP-DEV.md` cuando se cree.

## Qué era

`setup_deploy.py` fue el script que armó el deploy original a Streamlit Cloud en
abril de 2026 (`14/04`). Se corría **una sola vez** desde la raíz del repo y
dejaba la app lista para publicar en `share.streamlit.io`. Es el origen de la
autenticación, del `config.toml` y del primer `requirements.txt` con pins.

**No se puede volver a correr.** Sobrescribe sin preguntar el `requirements.txt`
(perdiendo los pins de `numpy`/`pyarrow` que hoy evitan un segfault en Cloud) y
parchea `app.py` con un bloque de login que ya no es el que usa la app. Por eso
se archiva: el conocimiento sirve, la ejecución rompe.

## Qué hacía, paso a paso

**1 — `.gitignore`.** Si no existía, lo creaba desde cero con un set mínimo:
`.streamlit/secrets.toml` primero de todo, más `__pycache__/`, `*.py[cod]`,
`.env`, `.venv`, `env/`, `venv/`, `.vscode/`, `.idea/`, `.DS_Store`,
`Thumbs.db`, `*.log` y `.streamlit/cache/`. Si el archivo ya existía, era
conservador: solo appendeaba `.streamlit/secrets.toml` bajo un comentario
`# ── Agregado por setup_deploy.py ──`, y si esa línea ya estaba, no tocaba
nada. **Ese comentario sigue vivo en el `.gitignore` de hoy** — es la huella
del script.

**2 — `requirements.txt`.** Lo sobrescribía siempre, sin backup. El set original
eran 7 paquetes, todos con pin exacto:

```
streamlit==1.43.2      pandas==2.2.3       openpyxl==3.1.5
pdfplumber==0.11.4     streamlit-authenticator==0.3.3
bcrypt==4.2.1          Pillow==11.1.0
```

De esos, 6 siguen vigentes hoy con la misma versión. `Pillow` se cayó en algún
momento posterior. Todo lo demás que hay hoy (`numpy`/`pyarrow` acotados,
`Jinja2`, `xhtml2pdf`, `svglib`, `anthropic`, `python-dotenv`, `plotly`,
`requests`, `beautifulsoup4`) se agregó después, a mano.

**3 — `.streamlit/config.toml`.** Lo escribía completo. Vale la pena marcarlo:
**el `config.toml` de hoy es byte-idéntico al que generaba este script.** Nadie
lo tocó desde abril. Lo que fija:

- `[server]` — `runOnSave = false`, `fileWatcherType = "none"` (importante en
  Cloud: el file watcher consume recursos y no sirve en un contenedor inmutable),
  `maxUploadSize = 200` MB, que es el techo real de subida de archivos de toda la
  app (los BR, bulks y flat files pasan por acá).
- `[browser]` — `gatherUsageStats = false`.
- `[theme]` — paleta Capybaras hardcodeada: `base = "light"`,
  `primaryColor = "#E84000"` (el naranja de la agencia), fondo `#FFFFFF`,
  secundario `#F5F5F5`, texto `#1A1A1A`, `font = "sans serif"`.
- `[logger]` — `level = "warning"`.

**4 — `.streamlit/secrets.toml`.** Paso interactivo. Instalaba `bcrypt` y
`streamlit-authenticator==0.3.3` con pip si faltaban, después pedía por consola
username / nombre / email / password en un loop (permitía cargar varios usuarios
seguidos), hasheaba cada password con `bcrypt.hashpw(...gensalt())` y generaba
un `cookie.key` aleatorio con `secrets.token_hex(32)` — 64 caracteres hex.
Si el archivo ya existía, no lo tocaba y avisaba que había que editarlo a mano.
De paso escribía un `secrets.toml.example` con placeholders para versionar.

⚠️ **La estructura que generaba ya no sirve.** Emitía `[cookie]` con solo `key`
y `expiry_days = 30`. El `app.py` de hoy lee además `_cookie["name"]`, que el
script nunca escribía: un `secrets.toml` generado por él revienta con `KeyError`
en el arranque actual. La plantilla vigente es `.streamlit/secrets.toml.example`,
y el generador vigente es `gen_secrets.py` (que tiene su propio problema: escribe
un solo usuario y pisa el archivo entero).

**5 — Parche de `app.py`.** Insertaba un bloque de login delimitado por
`# ── CAPYBARAS LOGIN BLOCK ──`, justo después del `import streamlit as st`, y
metía un `_authenticator.logout(...)` en el sidebar buscando como ancla un
`st.divider()` seguido del botón `🏠 Inicio`. Antes de tocar nada copiaba
`app.py` a `app.py.backup_pre_login`. Era idempotente: si encontraba el marker,
no volvía a parchear.

**Nada de eso sobrevive.** El `app.py` actual no tiene el marker, ni el backup
existe en el repo, y la llamada a `stauth.Authenticate` se reescribió: el script
usaba keyword args (`credentials=`, `cookie_name="capybaras_ppc"` hardcodeado,
`cookie_key=`, `cookie_expiry_days=`) y hoy es posicional, con el nombre de la
cookie viniendo de secrets. También se sumó después el bypass
`AGENCY_OS_LOCAL_MODE=1` y el manejo defensivo de
`StreamlitSecretNotFoundError`, que el script no contemplaba.

## Qué asumía del entorno

- Correr desde `C:\proyectos\ppc-manager` con el `app.py` presente (si no,
  abortaba con exit 1).
- `pip` disponible en el intérprete activo, con permiso para instalar.
- Consola interactiva — el paso 4 bloquea esperando `input()`.
- Terminal con soporte de códigos ANSI de color.
- **No creaba `runtime.txt`.** La versión de Python (`python-3.11`) la fijó
  `fix_deploy.py` recién después, cuando Streamlit Cloud empezó a resolver a
  Python 3.14 y rompía.

## El flujo de publicación que documentaba

1. Probar local con `python -m streamlit run app.py`.
2. Commit y push a `main`.
3. `share.streamlit.io` → New app → conectar el repo → branch `main` → `app.py`.
4. **Advanced settings → pegar el contenido de `secrets.toml`** — así es como
   los secrets llegan a Cloud, no viajan por el repo. Sigue siendo el mecanismo
   vigente para las credenciales y para los flags de backend.

## Para el dev que llega hoy

- El deploy vive en `capybaras-os.streamlit.app`, branch `main`, entrypoint
  `app.py`.
- Los secrets se cargan **a mano en el panel de Streamlit Cloud**, no por git.
- `config.toml` está versionado y no requiere setup.
- Para levantar local no hace falta nada de esto: alcanza con el venv y
  `AGENCY_OS_LOCAL_MODE=1`, o un `secrets.toml` propio copiado del `.example`.
- Ver también: `SETUP-MARCOS.md` (setup local, audiencia no técnica) y
  `SETUP-DEV.md` cuando exista.
