# SETUP-DEV — Montar el entorno de Agency OS

Guía para desarrolladores. Si sos usuario final (no tocás código), la guía es
`SETUP-MARCOS.md`. Esta es para levantar el repo y desarrollar.

## TL;DR — el camino rápido

### Windows (PowerShell)

```powershell
# 1. Configurar git ANTES de clonar (evita ruido de fin de línea en Windows)
git config --global core.autocrlf false

# 2. Clonar
git clone https://github.com/Leninead/ppc-manager.git
cd ppc-manager

# 3. Crear el venv con Python 3.12 (NO 3.11, NO 3.14 — ver abajo)
py -3.12 -m venv .venv
.venv\Scripts\activate

# 4. Instalar dependencias + pytest
pip install -r requirements.txt
pip install pytest

# 5. Correr la app en modo local (sin secrets)
$env:AGENCY_OS_LOCAL_MODE = "1"; python -m streamlit run app.py
```

### macOS (zsh)

```bash
# 1. Instalar uv, que trae Python 3.12 sin Homebrew ni sudo (con Homebrew: brew install uv).
#    Si después `uv` no aparece, abrí una terminal nueva.
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# 2. Clonar (en macOS no hace falta tocar core.autocrlf: git ya deja todo en LF)
git clone https://github.com/Leninead/ppc-manager.git
cd ppc-manager

# 3. Crear el venv con Python 3.12 (NO 3.11, NO 3.14 — ver abajo)
uv venv --seed --python 3.12 .venv
source .venv/bin/activate

# 4. Instalar dependencias + pytest
pip install -r requirements.txt
pip install pytest

# 5. Correr la app en modo local (sin secrets)
AGENCY_OS_LOCAL_MODE=1 python -m streamlit run app.py
```

Si la app levanta y ves el sidebar con módulos, estás listo.

## Python: 3.12 local, 3.11 en la nube (a propósito)

Hay una asimetría intencional que tenés que conocer:
- **Local: Python 3.12** (obligatorio). Creá el venv con `py -3.12` en Windows o con
  `uv venv --seed --python 3.12 .venv` en macOS.
- **Streamlit Cloud: Python 3.11** (lo fija `runtime.txt`).
- **NUNCA uses Python 3.14** — segfault a nivel C por incompatibilidad de ABI
  entre NumPy/pyarrow y CPython 3.14.

Consecuencia práctica: podés escribir sintaxis válida en 3.12 que rompe en 3.11
(ya pasó con un f-string con backslash). Si tu código va a producción, probá
mentalmente que sea compatible con 3.11.

## Dependencias — por qué los pins

`requirements.txt` tiene versiones clavadas por razones concretas, no por
capricho. **No las subas sin entender por qué:**
- `streamlit==1.43.2` + `numpy<2.2` + `pyarrow<19` → se mueven JUNTOS. Streamlit
  1.43.2 hace segfault en serialización Arrow con numpy≥2.2 o pyarrow≥19.
- `svglib==1.5.0` → la última versión antes de que dependa de pycairo, que no
  compila en Streamlit Cloud.

`pytest` no está en `requirements.txt` (es dep de desarrollo) — instalalo aparte
con `pip install pytest`.

## Secrets — el camino seguro

Para desarrollar NO necesitás secrets: corré en modo local con
`$env:AGENCY_OS_LOCAL_MODE = "1"` (en macOS, `AGENCY_OS_LOCAL_MODE=1` delante del comando),
que bypassea el login.

Si necesitás secrets reales (para probar auth o Supabase):

**Sobre `gen_secrets.py`:** podés correrlo. Desde el commit `18ecf52` tiene un
guard que aborta si `.streamlit/secrets.toml` ya existe — no pisa nada — y emite
el `[cookie]` completo (antes le faltaba `name` y la app moría con `KeyError` en
el arranque).

Pero genera **un solo usuario** y escribe el archivo desde cero. Para el
`secrets.toml` del equipo (con varios usuarios cargados), usá la plantilla:

```powershell
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# editá secrets.toml: cambiá el hash de password y el cookie.key
```
En macOS: `cp .streamlit/secrets.toml.example .streamlit/secrets.toml`.
Asegurate de que el bloque `[cookie]` tenga las 3 claves: `name`, `key`,
`expiry_days`. Si falta `name`, la app no arranca.

## Correr los tests — la baseline esperada

```powershell
python -m pytest -q
```
En macOS es el mismo comando, con el venv activado (`source .venv/bin/activate`).

**Resultado esperado hoy (2026-09-03): `1370 passed, 24 skipped, 5 failed,
2 errors`.**

Los rojos son **esperados** en local: dependen de fixtures y de config de
entorno que no tenés. NO rompiste nada. El número total cambia cada vez que
alguien suma un test — mirá las familias, no el conteo:
- `test_m29_ui_e2e.py` (3) + `test_b7_importer.py` (2 errores) +
  `test_datadive_to_v3_mapper.py` (1) — fixtures de propuestas que no están en el repo
- `test_knowledge_base_smoke.py` (1) — espera el fallback sin `secrets.toml`;
  como vos sí tenés uno, el selectbox trae los nombres del equipo y el test no
  encuentra su opción. Pasa solo en CI.

Si falla un archivo que NO está en esa lista, ahí sí revisá.

## Correr la app

```powershell
# Modo local (sin login, para desarrollo):
$env:AGENCY_OS_LOCAL_MODE = "1"; python -m streamlit run app.py

# Con auth (necesita secrets.toml válido):
python -m streamlit run app.py
```
En macOS, el modo local es `AGENCY_OS_LOCAL_MODE=1 python -m streamlit run app.py`; con auth,
el mismo comando que arriba.

Desde el panel de preview de Claude, `.claude/launch.json` trae las mismas tres formas de
arrancar para cada sistema: `agency-os`, `agency-os-e2e-local` y `agency-os-e2e-bridged` en
Windows, y sus versiones `-macos`.

`app.py` es un router Streamlit top-level (no tiene `if __name__ == "__main__"`).

## Git en Windows — evitar ruido de fin de línea

El repo fuerza LF (`.gitattributes`), pero Windows usa CRLF. Si no configurás
git, vas a generar commits de "ruido" que cambian solo los fin de línea.

**Antes de clonar:** `git config --global core.autocrlf false`

Si ya clonaste con `autocrlf=true` y ves diffs raros de líneas enteras sin
cambios reales, es esto.

## Estructura del repo — dónde está qué

- `app.py` — router principal (~420 líneas) + sidebar + auth
- `core/` — helpers, persistencia, i18n
- `modules/pages/` — los módulos (uno por archivo)
- `modules/mercado_libre/` — M36, único módulo fuera de `pages/`
- `tests/` — la suite
- `notes/` — el vault de Obsidian (el "cerebro": arquitectura, estado, SOPs).
  Empezá por `notes/README.md`.

## Próximos pasos

1. Leé `notes/README.md` → `notes/CLAUDE.md` → `notes/state/STATE-agencia.md`.
2. Para el flujo de trabajo con git (branches, PRs), ver `notes/sops/dev/`.
3. Tu primera tarea la definimos en la meet.
