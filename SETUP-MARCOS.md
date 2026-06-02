# SKU Progress Report — Guía de instalación local (Marcos)

Esta guía te deja corriendo el **SKU Progress Report** en tu PC para la prueba
de 2 semanas. Es para Windows. No hace falta que sepas git ni Python — seguí
los pasos en orden.

Si algo falla, andá al final: **"Si algo no anda"**.

---

## Lo que vas a necesitar (una sola vez)

1. **Python 3.12** — esta es la única versión que funciona. **NO uses 3.14**
   (rompe con un error feo de memoria).
   - Descargalo de https://www.python.org/downloads/release/python-3120/ →
     bajá *"Windows installer (64-bit)"*.
   - Al instalar, **tildá la casilla "Add python.exe to PATH"** abajo de todo.

2. **Git para Windows** — para bajar el proyecto.
   - https://git-scm.com/download/win → instalá con todas las opciones por
     defecto (siguiente, siguiente, siguiente).

---

## Paso 1 — Bajar el proyecto

Abrí **PowerShell** (botón inicio → escribí "PowerShell" → Enter) y pegá:

```powershell
cd C:\proyectos
git clone https://github.com/Leninead/ppc-manager.git
cd ppc-manager
git checkout feature/m28-soak-local
```

> Esto crea la carpeta `C:\proyectos\ppc-manager` y se para en la rama de la
> prueba. **Acordate de esta ruta** — vas a volver acá cada vez que abras la app.
> Si elegiste otra carpeta para clonar, usá esa en todos los pasos siguientes.

---

## Paso 2 — Preparar Python (una sola vez)

Parado en la carpeta del proyecto (seguís en `C:\proyectos\ppc-manager`), pegá
línea por línea:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> La última línea baja todo lo que la app necesita. Puede tardar 1–2 minutos.
> Cuando termine sin errores en rojo, ya está instalada.

**Si la línea del `Activate.ps1` te tira un error de "execution policy"**, corré
esto una vez y volvé a intentar:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Paso 3 — Abrir la app (esto lo repetís cada día)

**Siempre** desde la carpeta raíz del proyecto (`C:\proyectos\ppc-manager`):

```powershell
cd C:\proyectos\ppc-manager
.\.venv\Scripts\Activate.ps1
$env:AGENCY_OS_LOCAL_MODE="1"
python -m streamlit run app.py
```

> La línea `$env:AGENCY_OS_LOCAL_MODE="1"` desactiva el login para la
> prueba local — vas a ver un banner "🔓 MODO LOCAL" arriba, es normal.
> Tenés que ponerla cada vez que abrís una terminal nueva (no queda guardada).

Se abre solo en el navegador. En la barra de la izquierda buscá:
**Account Health → SKU Progress Report**.

> ⚠️ **IMPORTANTE — siempre arrancá desde `C:\proyectos\ppc-manager`.**
> Si lanzás la app parado en otra carpeta, tus datos se guardan en otro lado y
> la próxima vez "no aparecen". No es que se borraron — es que estás mirando
> desde el lugar equivocado. Mantené siempre el mismo punto de arranque.

Para cerrar: en la ventana de PowerShell apretá **Ctrl + C**.

---

## Cómo cargar tus datos cada semana

1. En Seller Central: **Business Reports → Detail Page Sales and Traffic By
   Child Item** → exportá el CSV.
2. **No abras ese CSV en Excel ni lo re-guardes como .xlsx** — la app solo lee
   CSV. (Si lo abrís en Excel solo para mirar, está bien; pero subí el archivo
   original que bajaste, no una versión re-guardada.)
3. En la app: pestaña **📤 Importar CSV** → subí el archivo → revisá el preview
   (te muestra cuántos SKUs reconoció y cuántas variantes consolidó) → confirmá.

---

## Dónde viven tus datos (y cómo respaldarlos)

Todo lo que cargás se guarda **en tu PC**, en:

```
C:\proyectos\ppc-manager\data\account-health\<tu-cliente>\sku-progress\
```

Ahí adentro vas a ver archivos `.parquet` (uno por semana) y un
`tracked-skus.json`. **Esa carpeta es toda tu data.**

**Backup recomendado (viernes):** copiá la carpeta `data\account-health\`
entera a tu Drive. Si algún día reinstalás o cambiás de PC, pegás esa carpeta de
vuelta en el mismo lugar y recuperás todo.

---

## Si algo no anda

| Síntoma | Qué hacer |
|---|---|
| `py` no se reconoce / Python no anda | No instalaste Python 3.12 o no tildaste "Add to PATH". Reinstalá Python 3.12 con esa casilla tildada. |
| Error de "execution policy" en `Activate.ps1` | Corré el comando `Set-ExecutionPolicy` del Paso 2 y reintentá. |
| La app abre pero "perdí" datos de la semana pasada | Casi seguro arrancaste desde otra carpeta. Cerrá (Ctrl+C), volvé a `cd C:\proyectos\ppc-manager` y abrí de nuevo desde ahí. |
| El uploader no me deja subir el .xlsx | Es a propósito — solo CSV/TSV/TXT. Bajá el CSV original de Seller Central sin re-guardarlo. |
| Cualquier otra cosa rara | Anotá qué hiciste y qué error salió (sacale captura) y pasámelo. No toques los `.parquet` a mano. |

---

*Prueba local — 2 semanas. Cualquier fricción que encuentres anotala: es justo
lo que queremos detectar antes de pasarlo a la nube.*
