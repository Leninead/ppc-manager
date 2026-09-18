# Portal de integraciones — pruebas locales y deploy al VPS

## Pruebas locales (antes de pushear)

El objetivo es correr el flujo entero — portal → receptor → worker — contra
la DB local con la misma forma de URL que producción, para agarrar bugs de
prefijo/gateway que no aparecen apuntando al Postgres directo.

### Requisitos

- Docker Desktop corriendo.
- `.venv` según [SETUP-DEV.md](../../SETUP-DEV.md). Las **imágenes** corren
  Python 3.11 (`runtime.txt`, `Dockerfile`, `Jenkinsfile`); el venv local no
  tiene por qué coincidir.
- `.env` en la raíz. Copiá la plantilla y completá:

  ```
  cp deploy/integrations/env.example .env
  ```

  Los tres JWT los acuña un script — son el mismo algoritmo con distinto claim
  `role`, firmados con `PGRST_JWT_SECRET`:

  ```
  sh scripts/mint_jwt.sh web_user       # → SUPABASE_KEY y INTEGRATIONS_RECEIVER_JWT
  sh scripts/mint_jwt.sh integ_worker   # → INTEGRATIONS_WORKER_JWT
  ```

  `INTEGRATIONS_PUBLIC_KEY` queda **vacía** hasta el paso 2: todavía no existe.

### 1. Levantar el stack y migrar

El orden importa: las tablas del portal **no** están en `schema.sql` (que además
corre una sola vez, al inicializar el volumen). Nacen en `deploy/db/migrations/`,
y `migrate.sh` necesita el servicio `db` arriba — si no, sale limpio sin migrar.

```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.proxy.yml \
  -f docker-compose.db.yml \
  up -d

sh deploy/db/migrate.sh
```

Servicios que quedan corriendo:

| Servicio | Rol | Puerto host |
|---|---|---|
| `agency-db` | Postgres 16 | interno |
| `agency-postgrest` | REST sobre la DB | interno (sin `ports:`) |
| `agency-rest-gateway` | Caddy — strip `/rest/v1` → postgrest | `127.0.0.1:3002` |
| `ppc-manager` (app) | Streamlit | interno (Caddy publica) |
| `integrations-receiver` | FastAPI OAuth + webhooks | interno |
| `caddy` | Reverse proxy TLS | `443` (auto-cert local) |

El receiver arranca *unhealthy* a propósito hasta que exista
`INTEGRATIONS_PUBLIC_KEY` — su `/health` devuelve 503 nombrando lo que falta.
Eso se resuelve en el paso siguiente.

### 2. Generar el par de claves del worker

```
export INTEGRATIONS_KEY_FILE="$(pwd)/data/integrations/sealing_private.pem"
export SUPABASE_URL="http://127.0.0.1:3002"
export INTEGRATIONS_WORKER_JWT="$(sh scripts/mint_jwt.sh integ_worker)"
.venv/Scripts/python.exe -m core.integrations.worker keys
```

Deja la mitad privada en `data/integrations/sealing_private.pem` (gitignored) y
publica la pública en `integration_settings.sealing_public_key`.

**Pegá la pública en `.env`** — la app la usa para sellar el `client_secret` y
el receptor para sellar el code del callback. Sale de la base en una línea:

```
docker exec agency-db psql -U postgres -d agency_os -tAc \
  "select valor from integration_settings where clave='sealing_public_key'"
```

Con la variable puesta, recreá los dos servicios que la leen:

```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.proxy.yml \
  -f docker-compose.db.yml \
  up -d app integrations-receiver
```

Chequeo: los dos tienen que quedar `healthy`.

```
docker inspect --format '{{.Name}} {{.State.Health.Status}}' \
  ppc-manager integrations-receiver
```


### 2b. El AI provider: chats que consultan Amazon Ads

Los chats de STR, SQP y DataDive pueden preguntarle al MCP oficial de Amazon Ads
sobre la cuenta de cliente que el AM elige en la barra lateral. Quien abre esa
sesión es `capybaras-ai-provider` (repo hermano): lee el portal con su propio
rol `integ_provider` (migración 008) y abre el material sellado con la clave
privada del worker, que monta de sólo lectura desde `ppc-manager_integrations_keys`.
La app nunca ve un token: sólo manda `{account_id, profile_id}` y el secreto
compartido.

```
# 1. Migrar (008 crea el rol) — ver §1
# 2. Acuñar el JWT del rol y un secreto compartido
sh scripts/mint_jwt.sh integ_provider   # → PORTAL_PROVIDER_JWT   (.env del provider)
openssl rand -hex 32                    # → CLAUDE_PROVIDER_SECRET (acá)
                                        #   = PROVIDER_SHARED_SECRET (allá)
# 3. ../capybaras-ai-provider/.env: PORTAL_PROVIDER_JWT, PROVIDER_SHARED_SECRET
#    (PORTAL_REST_URL queda en http://rest-gateway: el provider se une a la red
#    ppc-manager_web y al volumen de claves; los nombres salen del proyecto
#    compose, PORTAL_NETWORK / PORTAL_KEYS_VOLUME si el proyecto no se llama así)
# 4. Levantar el provider (corre como uid 10001, el del worker) y recrear la app
(cd ../capybaras-ai-provider && docker compose up -d --build)
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d app
# 5. Chequeo
curl -s http://127.0.0.1:3111/health | grep -o '"amazon_ads":[a-z]*'   # true
```

En la app: barra lateral → **Cuenta Amazon Ads** → elegir cliente y marketplace
→ abrir el chat de STR, SQP o DataDive y preguntar por las campañas de hoy. Por
cada turno con herramientas queda una fila `ai_tools_used` en `integration_audit`
(cuenta, perfil y nombres de las tools; nunca argumentos).

```
docker exec agency-db psql -U postgres -d agency_os -c \
  "select actor, resultado, detalle from integration_audit where accion='ai_tools_used' order by id desc limit 5"
```


### 3. Smoke end-to-end (portal → receiver → worker)

```
.venv/Scripts/python.exe scripts/smoke_integrations_e2e.py
```

El script hace las 7 fases del flujo, con MELI stubbeado con `responses`:

1. Reset del estado (borra credenciales / pendientes / conexiones de MELI).
2. Portal guarda un `client_secret` sellado.
3. Portal abre un `pending_grant` con verifier sellado.
4. HTTP GET real a `/oauth/callback` del receptor (uvicorn en background).
5. Verifica que el code queda sellado en `integration_pending_grants`.
6. Worker `grants` unsella y hace token exchange con MELI (mock).
7. Worker `refresh` rota el refresh token, verifica que la generación
   anterior se conserva.

Salida esperada: 7 pasos con `✓` verde y `all steps passed`.

### 4. Prueba HTTP viva contra Caddy (verifica path splitting)

Streamlit responde en `/`; el receptor debería responder en `/oauth/callback`
y `/notifications`. Verificar desde adentro del container de Caddy para saltear
el TLS de host:

```
docker exec caddy wget -qO- --no-check-certificate \
  "https://app.localhost/oauth/callback?code=X&state=NONEXISTENT"
# Devuelve el HTML "Autorización recibida" (200 aunque el state no exista,
# por seguridad — no se filtra qué states están en vuelo).
```

Si en su lugar aparece HTML de Streamlit, el path splitting está mal en el
Caddyfile o el receptor no está corriendo (`docker ps | grep receiver`).

### 5. E2E real con MELI (opcional, vía ngrok)

Para probar el flujo completo con MELI de verdad antes del push, se expone el
Caddy local con ngrok y se registra la URL temporal como Redirect URI.

```
# 1. Instalar ngrok, configurar authtoken (una vez)
ngrok config add-authtoken <TU_TOKEN>

# 2. Tunelizar el puerto 443 local de Caddy
ngrok http https://localhost:443
```

Ngrok devuelve un hostname del estilo `xxxx-yyyy.ngrok-free.app`. Con eso:

```
# 3. En .env, apuntar el hostname a lo que ngrok expone
APP_DOMAIN=xxxx-yyyy.ngrok-free.app
INTEGRATIONS_REDIRECT_URI=https://xxxx-yyyy.ngrok-free.app/oauth/callback

# 4. Registrar la MISMA URL en el DevCenter de MELI (temporalmente)
#    tu app → Redirect URI → Agregar → https://xxxx-yyyy.ngrok-free.app/oauth/callback

# 5. Recrear caddy + receiver para que tomen el APP_DOMAIN nuevo
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d --force-recreate caddy integrations-receiver

# 6. Abrir Streamlit en el browser (https://xxxx-yyyy.ngrok-free.app)
#    Portal Integraciones → Mercado Libre → Cargar credencial (client_id + secret reales)
#    → Conectar cuenta → Preparar autorización → Abrir el proveedor
#    → autorizar en MELI con la cuenta del cliente
#    → volver a la app; en 2 min (o corriendo grants manualmente) la cuenta aparece conectada

# 7. Correr el worker inmediatamente para no esperar el cron
docker compose ... run --rm integrations-worker python -m core.integrations.worker grants

# 8. Al terminar, SACAR la URL ngrok del DevCenter (para que un ngrok random
#    del futuro no pueda interceptar el flujo del cliente real)
```

**Cuando el E2E ngrok pasa**, el DEPLOY al VPS es sólo cambiar `APP_DOMAIN` por
`app.capybaras.agency` y registrar esa URL como Redirect URI en el DevCenter.

### 5b. E2E real con Amazon Ads (vía cloudflared, sin cuenta)

Mismo truco con `cloudflared`, que no pide token para un quick tunnel y no
obliga a tocar `APP_DOMAIN`: el Host se fija en `app.localhost` para que el
Caddy local rutee igual.

```
# 1. Túnel hacia el Caddy local (el hostname *.trycloudflare.com cambia en cada arranque)
cloudflared tunnel --url https://localhost:443 --no-tls-verify \
  --http-host-header app.localhost --origin-server-name app.localhost

# 2. En .env, SOLO la redirect URI (APP_DOMAIN queda en app.localhost)
INTEGRATIONS_REDIRECT_URI=https://<hostname>.trycloudflare.com/oauth/callback

# 3. Registrar esa misma URL en Login with Amazon: developer.amazon.com →
#    Login with Amazon → engranaje del Security Profile → Web Settings → Edit →
#    Allowed Return URLs (no Allowed Origins) → Save

# 4. Recrear la app para que tome la redirect URI
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d --force-recreate app

# 5. Abrir la app POR EL TÚNEL (Chrome no siempre llega a localhost:8501):
#    Integraciones → Amazon Ads → Agregar credential (Client ID + Secret del Security Profile)
#    → Cuentas conectadas → Autorizar con mi cuenta de Amazon → consentir con el usuario
#    de Amazon de Capybaras → "Autorización recibida"

# 6. Canjear YA (el code vive 5 minutos) y listar las cuentas
docker compose ... run --rm integrations-worker python -m core.integrations.worker grants

# 7. Al terminar, sacar la URL del túnel de Allowed Return URLs y volver .env a
#    https://app.localhost/oauth/callback
```

Un quick tunnel pierde la conexión QUIC cada pocos minutos por inactividad y
reconecta solo con el mismo hostname; si el redirect de Amazon cae justo en un
corte, reintentar el link alcanza.

### 5c. Ingesta del Search Term Report (Amazon Ads) en local

La migración `009_amazon_ads_sync.sql` crea las tablas de la ingesta y del registro de
solicitudes (`sh deploy/db/migrate.sh`, como el resto). El worker es un servicio más del
overlay de base, siempre prendido:

```
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml build
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d ads-sync-worker
docker logs -f agency-ads-sync-worker        # una línea por tick: perfiles, jobs, reportes, filas, errores
```

Necesita lo mismo que el `integrations-worker`: `INTEGRATIONS_WORKER_JWT` en `.env` y la clave de
sellado ya creada en el volumen `integrations_keys` (paso 2). Mientras falte algo, loguea una vez
que no está configurado y espera, sin reiniciarse en bucle. Sin autorizaciones de Amazon en la base
local no hay nada que bajar: para usar las de producción, ver 5d.

### 5d. Puente: usar en local las autorizaciones de Amazon de la VPS

`scripts/amazon_ads_bridge.py` evita el túnel y la URL nueva en Amazon. En la VPS abre la
credencial de Amazon Ads, las autorizaciones activas y sus cuentas con la clave de producción, y las
vuelve a sellar para la **clave pública local**. Lo único que viaja es texto cifrado que sólo abre tu
máquina. En producción sólo lee; en local escribe esas filas (credencial, autorizaciones con id
remapeado, cuentas). Queda en el repo para futuras pruebas; no tiene paso de borrado.

Desde Git Bash (PowerShell 5 no tiene `<` para redirigir):

```
cd /c/Users/<vos>/Desktop/Capybaras/ppc-manager
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml"

# 1) Clave pública local (es pública: se puede mover)
PUB_B64=$(docker exec agency-db psql -U postgres -d agency_os -tAc \
  "select valor from integration_settings where clave='sealing_public_key'" | base64 -w0)

# 2) Exportar en la VPS: el script entra por ssh y el paquete sale por el mismo pipe.
#    sudo porque /srv/ppc-manager/.env es de root (los cron del worker también corren como root).
ssh -i <clave-ssh> ubuntu@<vps> \
  "cd /srv/ppc-manager && sudo -n $COMPOSE run --rm -T -e BRIDGE_TARGET_PUBLIC_KEY_B64=$PUB_B64 integrations-worker python - export" \
  < scripts/amazon_ads_bridge.py > /c/tmp/amazon_ads_bundle.json

# 3) Importar en local
MSYS_NO_PATHCONV=1 $COMPOSE run --rm -T -e BRIDGE_ALLOW_IMPORT=local \
  -v C:/tmp/amazon_ads_bundle.json:/tmp/bundle.json:ro \
  integrations-worker python - import --bundle /tmp/bundle.json < scripts/amazon_ads_bridge.py

# 4) Refrescar las cuentas (trae zona horaria y moneda de cada perfil)
$COMPOSE run --rm integrations-worker python -m core.integrations.worker discover
```

- Las guardas están en el script: aborta si la clave de la VPS no coincide con la publicada, si la
  clave destino es la misma que la de origen, si falta `BRIDGE_ALLOW_IMPORT=local`, o si algún valor
  del paquete no abre con la clave local.
- El token de Login with Amazon no rota, así que usarlo en local no rompe producción. Tu máquina
  queda con acceso de lectura/escritura de campañas de esos clientes: disco cifrado y no compartir el
  paquete (tiene nombres de clientes aunque no tenga secretos en claro).
- Los reportes que pida el worker local son pedidos reales a Amazon (sólo lectura) y comparten los
  límites de la cuenta con producción.

### 5e. Análisis IA guardados (`ads-ai-worker`) en local

La migración `010_ai_analyses.sql` agrega `ai_analyses`, `ai_analysis_settings`, el rol `ai_worker` y la
cola de análisis sobre `integration_sync_jobs`. El worker necesita su JWT y el AI provider en la red
`ai-net`:

```
sh scripts/mint_jwt.sh ai_worker          # → AI_WORKER_JWT en .env
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d ads-ai-worker
docker logs -f agency-ads-ai-worker       # loguea sólo los ticks que encolan, corren o fallan
```

Para probar sin generar todas las cuentas (cada análisis es una llamada real al modelo contra la cuota del
provider), un tick acotado desde el venv:

```
SUPABASE_URL=http://127.0.0.1:3002 AI_WORKER_JWT=<jwt> CLAUDE_PROVIDER_URL=http://127.0.0.1:3111 \
  python -m core.ai_analysis.worker tick --profile-id <profile_id>
```

---

## Deploy al VPS

Qué falta hacer del lado del VPS y del DevCenter de cada proveedor para que el
flujo OAuth funcione en producción. **El código ya está en la rama** — lo que
sigue son configuraciones que sólo el dueño del VPS puede hacer.

Orden estricto: si te salteás un paso, el siguiente no arranca.

## 0. Asegurar que exista al menos un admin

⚠️ **Sin esto el portal queda inutilizable.** `Sistema → Integraciones` (donde
se cargan las credenciales del sistema) es admin-only, y el rol sale de
`.streamlit/secrets.toml`: si ningún usuario declara `role = "admin"`, nadie
puede cargar el `client_id`/`client_secret` de Mercado Libre y ninguna cuenta
de cliente se puede conectar.

Verificar en el VPS:

```sh
grep -c 'role *= *"admin"' /srv/ppc-manager/.streamlit/secrets.toml
```

Si devuelve `0`, agregar la clave al bloque del usuario que corresponda:

```toml
[credentials.usernames.lenin]
name     = "Lenin Acosta"
password = "$2b$12$..."
email    = "lenin@capybaras.agency"
role     = "admin"          # ← sin esta línea es rol `usuario`
```

Los demás usuarios quedan como `usuario`: ven `Sistema → Cuentas conectadas`
y pueden conectar cuentas de clientes, pero no tocan credenciales del sistema.
Requiere reiniciar el contenedor `app` para releer el archivo.

⚠️ **El archivo lo tiene que poder leer el uid 10001, no el usuario del host.**
`secrets.toml` se monta dentro del contenedor, que corre como `appuser` (uid
10001, fijo en el Dockerfile). Si el archivo queda `600` y es de `ubuntu`, la app
entra en crash-loop con `PermissionError: /app/.streamlit/secrets.toml` y el
health gate del deploy lo rechaza — un `644` funciona por accidente, porque lo
lee "otros". Lo correcto es dárselo al uid del contenedor:

```sh
sudo chown 10001:10001 /srv/ppc-manager/.streamlit/secrets.toml
sudo chmod 600 /srv/ppc-manager/.streamlit/secrets.toml
```

En el host va a figurar como `UNKNOWN:UNKNOWN`: ese uid no existe afuera del
contenedor, y está bien. `rsync` del pipeline excluye el archivo, así que la
propiedad sobrevive a los deploys.

## 1. Registrar la Redirect URI en el DevCenter de cada proveedor

**Mercado Libre** (única activa hoy): DevCenter → tu app → Redirect URI:
`https://app.capybaras.agency/oauth/callback` — la barra final NO se pone,
tiene que ser byte-a-byte lo que después va en `INTEGRATIONS_REDIRECT_URI`.

**Amazon Ads**: developer.amazon.com → Login with Amazon → el Security Profile
cuyo Client ID va a cargar el admin → ⚙️ Web Settings → Allowed Return URLs:
**la misma URL**, byte a byte. El receptor es genérico (ver el docstring de
`services/integrations_receiver/app.py`), no hay que levantar otro.

Dos cosas que son de Amazon y no del stack:

- La app de la agencia tiene que estar **aprobada para la Ads API y con el
  acceso asignado a ese Client ID** (el link del mail de aprobación, abierto en
  incógnito con la cuenta que aplicó). Hasta ese paso la pantalla de
  consentimiento responde `unknown scope` para `advertising::campaign_management`.
- Quien autoriza es un **empleado de Capybaras con su usuario de Amazon**, al
  que cada cliente invitó a su cuenta de Ads. Una autorización alcanza todas
  las cuentas que ese usuario ve, en NA, EU y FE; el worker las escribe en
  `integration_accounts` (migración 006). No hay nada que mandarle al cliente.
- Los refresh tokens de Amazon **vencen a los 365 días fijos** desde el
  consentimiento. La pantalla avisa 45 días antes y ofrece Reautorizar; el
  worker marca `needs_reauth` al vencer.

**Walmart** (cuando se active): mismo criterio.

## 2. Completar `.env` (todo menos la clave pública)

**Un solo archivo.** Compose lee `.env` para resolver `${...}` y sólo de ahí:
una variable puesta en un `.env.integrations` aparte no alimenta la
interpolación y el stack no arranca. Ningún contenedor monta el archivo —
cada servicio nombra en su `environment:` sólo lo que usa, y por eso el
contenedor `app` no tiene la contraseña de Postgres ni el JWT del worker.

```
cp deploy/integrations/env.example /srv/ppc-manager/.env
chmod 600 /srv/ppc-manager/.env
```

Los tres JWT son el mismo algoritmo con distinto claim `role`, firmados con
`PGRST_JWT_SECRET`. Los acuña el script del repo:

```
sh scripts/mint_jwt.sh web_user       # → SUPABASE_KEY y INTEGRATIONS_RECEIVER_JWT
sh scripts/mint_jwt.sh integ_worker   # → INTEGRATIONS_WORKER_JWT
```

`INTEGRATIONS_PUBLIC_KEY` queda **vacía** hasta el paso 4: la genera el worker
y todavía no corrió. Todo lo demás se completa ahora, porque el paso 3 no
levanta sin `POSTGRES_PASSWORD`, `PGRST_JWT_SECRET`, `SUPABASE_KEY` e
`INTEGRATIONS_RECEIVER_JWT`, y el paso 4 necesita el JWT del worker.

## 3. Levantar el stack

```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.proxy.yml \
  -f docker-compose.db.yml \
  up -d
```

Servicios que deberían estar corriendo después:

- `app` (Streamlit)
- `integrations-receiver` (FastAPI, el nuevo)
- `caddy` (con path splitting: `/oauth/*` y `/notifications` van al receptor)
- `db`, `postgrest`, `rest-gateway`

El receiver queda *unhealthy* a propósito: su `/health` devuelve 503 mientras
falte `INTEGRATIONS_PUBLIC_KEY`, y nombra lo que falta. Se resuelve en el paso 4.

## 4. Correr la migración

Va **después** de levantar el stack, no antes: `migrate.sh` habla con el
servicio `db` por compose y, si no está corriendo, sale limpio imprimiendo
`db service is not running — skipping migrations`. Correrlo primero deja la
base sin las tablas del portal y sin ningún error a la vista.

```
cd /srv/ppc-manager
sh deploy/db/migrate.sh
```

Idempotente. Deja las migraciones del portal —
`002_integrations.sql`, `003_meli_api.sql`, `004_meli_ads_unique.sql`,
`005_notifications_insert.sql`, `006_integration_accounts.sql` (cuentas de
clientes por autorización, Amazon Ads) y `007_receiver_records_provider_error.sql`
(el receptor puede escribir `error` en el grant) — aplicadas y registradas en
`schema_migrations`. Jenkins corre este mismo script en cada deploy (etapa
`DB migrate`), así que a mano sólo hace falta en una instalación nueva.

Ojo: `deploy/db/schema.sql` corre **una sola vez**, al inicializar el volumen
`pgdata`. Una base que ya existía de antes de esta rama nunca lo vuelve a
correr, así que todo lo del portal llega por acá.

Este paso es manual sólo la primera vez. Después lo corre el pipeline: el
Jenkinsfile tiene una etapa `DB migrate` entre `Deploy` y `Health gate`, así
que cada deploy aplica lo que falte antes de que el health gate mire la app.

## 5. Generar el par de claves del worker

**Una sola vez, en el VPS.** El worker crea el par, guarda la mitad privada en
su volumen `integrations_keys`, y publica la mitad pública en la tabla
`integration_settings.sealing_public_key`. Nadie tipea ni pega la privada.

```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.proxy.yml \
  -f docker-compose.db.yml \
  run --rm integrations-worker python -m core.integrations.worker keys
```

⚠️ El volumen `integrations_keys` es el activo más frágil del portal: si se
pierde la privada, **ninguna credencial ni refresh token sellado se puede
volver a abrir**. Está cubierto por `deploy/db/backup.sh` con su propia
rotación — verificá que ese backup corra antes de conectar la primera cuenta.

La salida imprime dónde quedó la privada. La pública se lee de la base:

```
docker exec agency-db psql -U postgres -d agency_os -tAc \
  "select valor from integration_settings where clave='sealing_public_key'"
```

Pegala en `INTEGRATIONS_PUBLIC_KEY` en `/srv/ppc-manager/.env`, en una sola
línea con `\n` literal entre encabezado y cuerpo. La leen la app (sella el
`client_secret` que carga el admin) y el receptor (sella el code del callback);
el worker no la necesita porque tiene la privada en su volumen.

Recreá los dos servicios que la leen:

```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.proxy.yml \
  -f docker-compose.db.yml \
  up -d app integrations-receiver
```

Chequeo — los dos tienen que quedar `healthy`:

```
docker inspect --format '{{.Name}} {{.State.Health.Status}}' \
  ppc-manager integrations-receiver
docker logs integrations-receiver 2>&1 | tail -5
```

⚠️ **No sirve `curl https://<dominio>/health`.** Caddy sólo rutea `/oauth/*` y
`/notifications` al receptor; `/health` cae en el `handle` final y lo contesta
Streamlit, así que un 200 ahí no dice nada del receptor. El `/health` del
receptor es interno (`localhost:8600`) y es justo lo que consulta su propio
healthcheck — por eso el chequeo va por `docker inspect`. Es el mismo par de
contenedores que gatea el pipeline en `Health gate`.

Para probarlo de punta a punta desde afuera, usá una ruta que Caddy sí le rutee:

```
curl -sk -o /dev/null -w '%{http_code}\n' \
  "https://app.capybaras.agency/oauth/callback?code=PROBE&state=NOEXISTE"   # 200
```

Los **dos** parámetros, no sólo `state`: el handler responde `400 callback
missing code or state` cuando falta cualquiera, así que un `?state=probe` solo
devuelve 400 y parece un receptor roto cuando en realidad está perfecto. Con los
dos, un `state` inexistente igual da 200 y el HTML "Autorización recibida" — es
deliberado, para no filtrar qué states están en vuelo.


## 5b. Conectar el AI provider al portal (chats con Amazon Ads)

`capybaras-ai-provider` vive en `/srv/capybaras-ai-provider` con su propio
compose. Para que los chats consulten Amazon Ads necesita tres cosas de este
stack, y ninguna se copia a mano: la red `ppc-manager_web` (ahí responde
`rest-gateway`), el volumen `ppc-manager_integrations_keys` (lo monta de sólo
lectura; por eso su imagen corre como uid 10001, el del worker) y un JWT del
rol `integ_provider`, que crea la migración 008.

```
cd /srv/ppc-manager
sh scripts/mint_jwt.sh integ_provider   # → PORTAL_PROVIDER_JWT
openssl rand -hex 32                    # → CLAUDE_PROVIDER_SECRET acá = PROVIDER_SHARED_SECRET allá
```

En `/srv/ppc-manager/.env`: `CLAUDE_PROVIDER_SECRET`. En
`/srv/capybaras-ai-provider/.env`: `PORTAL_PROVIDER_JWT`, `PROVIDER_SHARED_SECRET`
(y `PORTAL_REST_URL=http://rest-gateway`, que es el default). Después:

```
cd /srv/capybaras-ai-provider
# una sola vez: los volúmenes creados por la imagen vieja son de uid 1000
docker compose run --rm --user root --entrypoint sh provider \
  -c 'chown -R 10001:10001 /app/data /home/provider'
docker compose up -d --build
# sin curl en la imagen: el health se lee con python
docker compose exec provider python -c "import urllib.request as u;print(u.urlopen('http://localhost:3111/health').read().decode())" \
  | grep -o '"amazon_ads": *[a-z]*'   # true

cd /srv/ppc-manager
docker compose -f docker-compose.yml -f docker-compose.proxy.yml -f docker-compose.db.yml up -d app
```

Qué puede hacer ese rol, y nada más: leer la cuenta del cliente y sus perfiles,
la autorización que la sostiene (con su refresh token sellado) y la credencial
de sistema; marcar `needs_reauth` una autorización cuando Login with Amazon la
da por muerta; e insertar en `integration_audit`. El provider expone al modelo
sólo las herramientas de lectura de Amazon (más las que inician reportes):
ninguna crea, modifica ni borra.


## 5c. Worker de Amazon Ads (`ads-sync-worker`)

Es el que mantiene al día el Search Term Report de cada perfil de Amazon Ads. A diferencia del
`integrations-worker`, **no va por cron**: es un servicio siempre prendido del overlay de base
(`docker-compose.db.yml`), así que el deploy de Jenkins lo levanta y lo actualiza solo con
`docker compose up -d`, con el mismo `IMAGE_TAG` fijado que la app.

**Qué hace, cada minuto** (`python -m core.amazon_ads.worker run`, `ADS_TICK_SECONDS` para cambiarlo):
- Sincroniza `ads_profile_sync` desde `integration_accounts` (zona horaria, moneda, estado de la autorización).
- Planifica por perfil, en su hora local: diaria de 14 días a las 03:00 (lunes a sábado), 42 días los
  domingos, carga inicial de 65 días apenas aparece un perfil (incluidos los que ya estaban conectados
  al primer deploy), nombres de portfolio una vez por día.
- Pide los reportes a Amazon en tramos (14 días, 7 para perfiles muy grandes), los consulta, los
  descarga, guarda el crudo en `ads_raw` y reemplaza cada día en una sola transacción.
- Reintenta con espera creciente hasta las 23:00 del perfil y deja todo en `integration_sync_jobs`,
  que es lo que muestra ⚙️ Sistema → 🧾 Registro de solicitudes.
- Escribe un latido en `integration_worker_heartbeats`: si pasa más de 5 minutos sin latido, el
  registro lo marca como alerta.

**Primer deploy.**
1. Nada que instalar a mano: Jenkins aplica `009_amazon_ads_sync.sql` en *DB migrate* y el servicio
   arranca en *Deploy*. Como el deploy levanta los contenedores antes de migrar, el worker puede
   arrancar sin tablas: loguea que faltan y sigue esperando.
2. Necesita `INTEGRATIONS_WORKER_JWT` en `/srv/ppc-manager/.env` (ya está, lo usa el cron) y la clave de
   sellado en el volumen `integrations_keys`, que monta **de sólo lectura** (nunca crea claves).
3. Verificar:
   ```
   docker logs --tail 20 agency-ads-sync-worker
   docker exec agency-db psql -U postgres -d agency_os -tAc \
     "select last_tick_at, summary->>'profiles_active', summary->>'jobs_planned' from integration_worker_heartbeats"
   docker exec agency-db psql -U postgres -d agency_os -tAc \
     "select status, count(*) from integration_sync_jobs group by 1"
   ```
   A los pocos minutos tiene que haber jobs `backfill` en curso por cada perfil activo.

**Operación.**
- Cambiar o quitar la credencial de Amazon en Integraciones no necesita reiniciar: el worker la vuelve a
  leer en cada refresh de token.
- Frenarlo: `docker compose stop ads-sync-worker`. Termina el paso en curso (hasta 2 minutos,
  `stop_grace_period`) y al volver retoma los reportes pedidos por su `reportId`. Un tramo cuyo guardado se corta
  dos veces falla como `SaveCrashed` y hay que reintentarlo desde el Registro.
- Rollback: si Jenkins vuelve a una imagen anterior a este worker, el pipeline lo frena (una imagen vieja
  no tiene `core.amazon_ads`). A mano: `docker compose stop ads-sync-worker` antes de
  `IMAGE_TAG=<tag> docker compose up -d`.
- Logs: rotan a 10 MB × 5 (`logging:` del servicio).
- Crudo: los reportes originales quedan 180 días en el volumen `ads_raw` y se borran sólo desde
  `ads_report_requests` (nunca recorriendo carpetas). Es una excepción documentada a "sin borrados
  automáticos": son copias secundarias; lo normalizado nunca se borra solo. `deploy/db/backup.sh` los
  espeja en `/srv/backups/ads_raw`, porque Amazon guarda los search terms sólo 65 días.
- Una cuenta que falla hoy aparece en el Registro de solicitudes con su error; "Reintentar" crea una
  solicitud nueva. Un perfil sin la carga inicial completa también queda marcado ahí.

## 5d. Worker de análisis IA (`ads-ai-worker`)

Genera el análisis IA del Search Term Report (M2) cuando llegan datos nuevos por API y lo guarda en
`ai_analyses`. M2 muestra el análisis de exactamente los datos y parámetros en pantalla; si no existe,
ofrece generarlo con un clic y nunca muestra uno anterior.

**Qué hace, cada minuto** (`python -m core.ai_analysis.worker run`, `AI_TICK_SECONDS` para cambiarlo):
- Por cada perfil activo con datos, cuando cambió su último sync o sus parámetros guardados, arma lo que
  leería la IA para los últimos 30 días con los parámetros de la cuenta y calcula su huella. Si ya hay un
  análisis (o un pedido en curso) con esa huella, no hace nada; si no, encola `ai_str_analysis`.
- Espera a que termine la ingesta en curso del perfil. Las cuentas sin precio cargado (monedas distintas de
  USD) también se generan, sin la regla R3 ni bids sugeridos; el perfil sin filas cuenta como "nada que
  analizar".
- Corre hasta `AI_ANALYSIS_CONCURRENCY` (2) análisis a la vez en hilos propios; el latido
  (`worker_name='ai_analysis'`) se escribe cada tick y el Registro alerta si pasan 5 minutos sin él.
- Los pedidos de la pantalla ("Generar análisis IA") y los reintentos entran por la misma cola.

**Primer deploy.**
1. Jenkins aplica `010_ai_analyses.sql` en *DB migrate*.
2. `sh scripts/mint_jwt.sh ai_worker` y dejarlo como `AI_WORKER_JWT` en `/srv/ppc-manager/.env`. Sin él,
   el servicio loguea una vez que no está configurado y espera.
3. El AI provider tiene que estar en `ai-net` (ya lo está para la app) y, si usa secreto compartido,
   `CLAUDE_PROVIDER_SECRET` en el mismo `.env`. Su `REQUEST_TIMEOUT_S` tiene que ser de al menos 3600: el
   worker espera hasta 60 minutos por análisis (la cuenta más grande tardó 14). Al 2026-09-15 la VPS tiene 3600.
4. Verificar:
   ```
   docker logs --tail 20 agency-ads-ai-worker
   docker exec agency-db psql -U postgres -d agency_os -tAc \
     "select last_tick_at, summary->>'analyses_queued', summary->>'jobs_running' from integration_worker_heartbeats where worker_name='ai_analysis'"
   docker exec agency-db psql -U postgres -d agency_os -tAc \
     "select status, count(*) from ai_analyses group by 1"
   ```
   Al primer tick encola un análisis por cuenta con candidatos, tenga o no precio cargado (en la copia local
   del 2026-09-15: 7 cuentas USD y 4 de otras monedas); cada uno tarda de 3 a 14 minutos
   (medido: Dermaglós US 3-4 min, Shapermint US 14 min con 120 negativos y 60 harvest).

**Operación.**
- Costo: un análisis por cuenta cuando cambian sus datos (con la ventana de 30 días que avanza, casi uno por
  día por cuenta), más los que se pidan desde M2 con otros parámetros, período o idioma. Nunca dos veces la
  misma huella.
- Frenarlo: `docker compose stop ads-ai-worker`. Devuelve a la cola los análisis en curso; la llamada al
  provider se corta y se vuelve a pagar al retomar.
- Rollback: igual que el worker de ingesta; el pipeline lo frena si la imagen anterior no tiene
  `core.ai_analysis`.
- Los análisis guardados no se borran solos (sin borrados automáticos).

## 6. Programar los cron del worker

```
# /etc/cron.d/integrations-worker (root o el usuario que corre docker)
*/5  * * * * root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm --no-deps integrations-worker python -m core.integrations.worker grants   >>/var/log/integrations-worker.log 2>&1
*/20 * * * * root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm --no-deps integrations-worker python -m core.integrations.worker refresh  >>/var/log/integrations-worker.log 2>&1
7 * * * *    root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm --no-deps integrations-worker python -m core.integrations.worker discover >>/var/log/integrations-worker.log 2>&1
# Ingesta MELI: 1 vez al día, al cierre. Se corre tarde porque las métricas
# del día quedan firmes cuando MELI cierra su ventana (visitas/ventas/ads);
# los reportes que la app muestra a la mañana siguiente ya son definitivos.
# Sin este cron el portal conecta cuentas pero nunca trae datos.
30 23 * * *  root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm --no-deps integrations-worker python -m core.meli_api.worker ingest    >>/var/log/meli-api-worker.log 2>&1
```

`--no-deps` no es opcional. Jenkins corre `docker compose` desde su contenedor y
el cron desde el host, con versiones distintas que calculan distinto la huella de
cada servicio: sin `--no-deps`, la primera corrida del cron después de cada deploy
ve la base y el gateway "desactualizados" y los recrea, y el worker de análisis y la
app pierden la base unos segundos (verificado el 2026-09-18: compose 5.4.0 en
Jenkins, 2.35.1 en el host). Los servicios de los que depende ya corren siempre;
el cron no tiene por qué tocarlos.

El cron **no** pasa `IMAGE_TAG`: lo resuelve de `/srv/ppc-manager/.env`, donde
el pipeline lo fija en cada deploy (y lo revierte si el health gate rueda atrás).
Eso importa más de lo que parece: el worker rota refresh tokens **de un solo
uso**, así que si corriera sobre `latest` —un tag que el build mueve aunque los
tests fallen, aunque `DEPLOY=false`, y aunque el gate haya rechazado esa
imagen— una rotación con bug quema los tokens de toda la flota en una noche, y
el rollback no los devuelve. Si levantás el stack a mano, poné el tag:
`IMAGE_TAG=<sha> docker compose … up -d`.

- `grants` cada 2 min: canjea los codes que dejó el receptor **y sincroniza
  de una la cuenta de Mercado Libre que acaba de conectarse**. Sin ese primer
  sync la cuenta quedaba Activa y vacía hasta las 23:30 — hasta un día entero
  mirando una conexión que anda y no muestra nada. Cada 2 y no cada 5 porque
  un code de Login with Amazon vence a los **5 minutos** y cada corrida
  arranca un contenedor: con `*/5` el peor caso llegaba tarde y el grant
  quedaba `fallido` con un mensaje que parecía otra cosa.
- `refresh` cada 20 min: rota los refresh tokens con margen de 30 días
  (Mercado Libre) o sólo comprueba que sigan vivos (Amazon no rota), y marca
  `needs_reauth` los consentimientos que pasaron su vida útil.
- `discover` cada hora (minuto 7): vuelve a listar las cuentas de clientes que cada
  autorización de Amazon alcanza. Es lo que hace aparecer un cliente nuevo que
  invitó al empleado sin pedirle que autorice de nuevo, y ahora también trae la zona
  horaria y la moneda de cada perfil. Pasó de diario a cada hora porque
  `ads-sync-worker` le arranca la carga inicial a un perfil apenas aparece: con el cron
  diario un cliente nuevo esperaba hasta 24 h. **Este cambio se hace a mano en
  `/etc/cron.d/integrations-worker`** (Jenkins no toca el cron).
- `ingest` 1 vez al día 23:30: trae items, visitas, ventas y métricas de
  ads de TODAS las cuentas. Corre al cierre porque las métricas del día
  quedan firmes recién ahí; el AM abre el módulo a la mañana con el día
  anterior completo. También es el reintento del primer sync: si el de
  conexión falló, esta corrida lo levanta sin que nadie haga nada.

**El intervalo de `grants` es ahora la espera que siente el operador.** Con 2
minutos, conectar y ver datos es cuestión de minutos; si querés que se sienta
inmediato, bajalo a `* * * * *`. Correrlo más seguido es barato: cuando no hay
autorizaciones pendientes el comando sale al toque sin tocar la API de Mercado
Libre ni cargar el pipeline de ingest.

El primer sync corre **después** de canjear todos los grants de esa corrida, y
su fallo se loguea sin mover el exit code: la cuenta ya quedó conectada, así que
un catálogo lento no puede hacer que el cron reporte como rota una conexión que
funciona. En el log aparece como `sync mercado_libre · <slug> (first sync)`, y
un fallo como `warn first sync failed for <slug>`.

Para forzar cosas a mano sigue estando `docker compose … run --rm
integrations-worker … grants`, y `… ingest --client=<slug>` para una sync
puntual de una cuenta ya conectada.

⚠️ No hay locking: `meli_locks` existe en el schema pero nadie la usa todavía.
Conectar una cuenta a las 23:29 puede solapar su primer sync con el ingest
nocturno de esa misma cuenta. Es la misma exposición que ya tenía un `ingest
--client` manual, no una que traiga esta feature, pero conviene tenerla
presente si algún día aparecen filas duplicadas.

### Tablas declaradas sin consumer todavía

`meli_notifications` y `meli_job_queue` existen desde `003_meli_api.sql`.
El receptor escribe notificaciones en la primera; **nada las drena aún**. La
segunda está vacía. No bloquean el deploy — son la base del modo push
(webhooks de Mercado Libre) que reemplaza al polling cuando se implemente.
Si aparecen filas acumuladas en `meli_notifications`, es esperado, no un
incidente.

Que se escriban depende de `005_notifications_insert.sql`: `003` había dejado
a `web_user` con sólo `select` sobre esa tabla, y el receptor corre con ese
rol. Sin la `005`, PostgREST contesta 403, el receptor loguea el error y
igual devuelve 200 a Mercado Libre (correcto: reintentar no arregla un
permiso), así que **cada webhook se perdía en silencio**. Para confirmar que
quedó bien, después del deploy:

```
docker exec agency-db psql -U postgres -d agency_os -tAc   "select has_column_privilege('web_user','meli_notifications','topic','insert')"
```

## 7. Prueba end-to-end

1. **Admin**, en Streamlit → ⚙️ Sistema → 🔌 Integraciones → Mercado Libre →
   **Agregar credencial** (client_id + client_secret de la app del
   DevCenter). El secret se sella con la clave pública y se guarda cifrado.
2. **Cualquier empleado**, en ⚙️ Sistema → 🔑 Cuentas conectadas → bloque
   Mercado Libre → **Conectar cuenta nueva**. No pide campos: el link de
   consentimiento se arma al abrir el diálogo.
3. **Abrir Mercado Libre para autorizar** → el vendedor entra con SU cuenta
   y da consentimiento.
4. Redirige a `/oauth/callback` del receptor, que sella el code y lo deja
   en `integration_pending_grants.code_sealed`.
5. La próxima corrida de `worker grants` (≤2 min) canjea el code, pregunta la
   identidad al resolver del proveedor (`/users/me` en Mercado Libre;
   `/user/profile` + `/v2/profiles` en Amazon) y guarda nombre + marketplace +
   refresh token cifrado en `integration_connections`. Por eso el operador
   nunca tipea el nombre de la cuenta ni el país.
6. La cuenta aparece en 🔑 Cuentas conectadas con su nickname real y el
   chip del marketplace (`MLA`, `MLM`, …), estado **Activa**.
7. **Esa misma corrida** sincroniza la cuenta recién conectada: trae items,
   visitas, ventas y ads sin esperar a la noche. Al terminar, el módulo
   🛒 Mercado Libre ya muestra `🔌 datos vía API · actualizado <fecha>`
   sobre las pestañas. El `ingest` de las 23:30 sigue corriendo para
   mantener los datos al día y para reintentar si este primer sync falló.

Si algo falla en (4) o (5), el vendedor ve "Autorización recibida" pero la
cuenta nunca figura conectada. Diagnóstico:

```
# ¿El code llegó al receptor?
docker exec agency-db psql -U postgres -d agency_os -tAc \
  "select id, integration_slug, estado, created_at from integration_pending_grants order by created_at desc limit 5"
# ¿El worker corrió?
tail -50 /var/log/integrations-worker.log
```

## Notas de operación

- **`/oauth/callback` es provider-agnostic.** Cuando Amazon Ads y Walmart se
  activen no hay que agregar rutas nuevas: sólo cargar sus credenciales en
  el portal y registrar la misma URL en sus DevCenters.
- **`/notifications` es MELI-específico.** Amazon usa SNS y va a necesitar su
  propio handler (`/notifications/amazon` o un endpoint SNS). Walmart no
  tiene webhook: se polea.
- **Backup de la clave privada del worker.** Vive en el volumen Docker
  `integrations_keys`. Si se pierde, todos los refresh tokens actuales
  quedan ilegibles y hay que reautorizar TODOS los clientes de MELI y todas
  las autorizaciones de Amazon. `deploy/db/backup.sh` lo empaqueta junto con
  el `pg_dump` (ver paso 5); lo que hay que verificar es que ese script esté
  en el cron del VPS.
- **El sellado v2 no se puede deshacer con un rollback.** Desde esta versión
  `crypto.seal` escribe `v2:` (envelope AES-GCM + RSA) y la imagen anterior
  sólo abre `v1:`. Si hace falta volver a una imagen previa después de que el
  worker nuevo corrió, lo sellado entre medio (verifiers, codes, la credencial
  de Amazon, tokens de MELI rotados) queda ilegible para el worker viejo:
  frenar el cron del worker antes del rollback y reautorizar lo afectado.
