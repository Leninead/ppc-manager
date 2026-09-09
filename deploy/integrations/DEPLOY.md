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
#    → volver a la app; en 5 min (o corriendo grants manualmente) la cuenta aparece conectada

# 7. Correr el worker inmediatamente para no esperar el cron
docker compose ... run --rm integrations-worker python -m core.integrations.worker grants

# 8. Al terminar, SACAR la URL ngrok del DevCenter (para que un ngrok random
#    del futuro no pueda interceptar el flujo del cliente real)
```

**Cuando el E2E ngrok pasa**, el DEPLOY al VPS es sólo cambiar `APP_DOMAIN` por
`app.capybaras.agency` y registrar esa URL como Redirect URI en el DevCenter.

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

## 1. Registrar la Redirect URI en el DevCenter de cada proveedor

**Mercado Libre** (única activa hoy): DevCenter → tu app → Redirect URI:
`https://app.capybaras.agency/oauth/callback` — la barra final NO se pone,
tiene que ser byte-a-byte lo que después va en `INTEGRATIONS_REDIRECT_URI`.

**Amazon Ads** (cuando se active): LWA console → Security Profile → Web
settings → Allowed Return URLs: **la misma URL**. El receptor es genérico
(ver el docstring de `services/integrations_receiver/app.py`), no hay que
levantar otro.

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

Idempotente. Deja las cuatro migraciones que esta rama trae —
`002_integrations.sql`, `003_meli_api.sql`, `004_meli_ads_unique.sql` y
`005_notifications_insert.sql` — aplicadas y registradas en `schema_migrations`.

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
  "https://app.capybaras.agency/oauth/callback?state=probe"   # 200
```


## 6. Programar los cron del worker

```
# /etc/cron.d/integrations-worker (root o el usuario que corre docker)
*/5  * * * * root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm integrations-worker python -m core.integrations.worker grants  >>/var/log/integrations-worker.log 2>&1
*/20 * * * * root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm integrations-worker python -m core.integrations.worker refresh >>/var/log/integrations-worker.log 2>&1
# Ingesta MELI: 1 vez al día, al cierre. Se corre tarde porque las métricas
# del día quedan firmes cuando MELI cierra su ventana (visitas/ventas/ads);
# los reportes que la app muestra a la mañana siguiente ya son definitivos.
# Sin este cron el portal conecta cuentas pero nunca trae datos.
30 23 * * *  root docker compose -f /srv/ppc-manager/docker-compose.yml -f /srv/ppc-manager/docker-compose.proxy.yml -f /srv/ppc-manager/docker-compose.db.yml run --rm integrations-worker python -m core.meli_api.worker ingest    >>/var/log/meli-api-worker.log 2>&1
```

El cron **no** pasa `IMAGE_TAG`: lo resuelve de `/srv/ppc-manager/.env`, donde
el pipeline lo fija en cada deploy (y lo revierte si el health gate rueda atrás).
Eso importa más de lo que parece: el worker rota refresh tokens **de un solo
uso**, así que si corriera sobre `latest` —un tag que el build mueve aunque los
tests fallen, aunque `DEPLOY=false`, y aunque el gate haya rechazado esa
imagen— una rotación con bug quema los tokens de toda la flota en una noche, y
el rollback no los devuelve. Si levantás el stack a mano, poné el tag:
`IMAGE_TAG=<sha> docker compose … up -d`.

- `grants` cada 5 min: canjea los codes que dejó el receptor.
- `refresh` cada 20 min: rota los refresh tokens con margen de 30 días.
- `ingest` 1 vez al día 23:30: trae items, visitas, ventas y métricas de
  ads. Corre al cierre porque las métricas del día quedan firmes recién
  ahí; el AM abre el módulo a la mañana con el día anterior completo.

Si el AM conecta una cuenta y quiere ver el resultado ya, `docker compose
… run --rm integrations-worker … grants` manual lo cierra al toque. Lo
mismo con `… ingest --client=<slug>` para forzar una sync puntual.

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
5. La próxima corrida de `worker grants` (≤5 min) canjea el code, consulta
   `/users/me` a Mercado Libre y guarda nickname + site_id + refresh token
   cifrado en `integration_connections`. Por eso el operador nunca tipea el
   nombre de la cuenta ni el país.
6. La cuenta aparece en 🔑 Cuentas conectadas con su nickname real y el
   chip del marketplace (`MLA`, `MLM`, …), estado **Activa**.
7. Esa misma noche (23:30) `worker ingest` trae items, visitas, ventas y
   ads. A la mañana siguiente el módulo 🛒 Mercado Libre muestra
   `🔌 datos vía API · actualizado <fecha>` sobre las pestañas.

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
  quedan ilegibles y hay que reautorizar TODOS los clientes de MELI. El
  `deploy/db/backup.sh` de hoy hace `pg_dump` de la base pero NO toca ese
  volumen — agregarlo al backup es una tarea aparte.
