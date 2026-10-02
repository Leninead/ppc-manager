# Bot de Slack — el chat de PPC Manager en Slack

`services/slack_bot/` conecta Slack con el chat de la app. Usa el mismo agente (`orchestrator`), las mismas
reglas, skills y herramientas (MCP de ppc-manager, Amazon Ads, DataDive) y los mismos componentes. Las respuestas
salen iguales que en el panel; lo único que cambia es cómo se dibujan. PPC Manager no se modifica: el bot importa
`ai.runtime`, `ai.client` y `core.chat.*` tal como están, y `tests/test_slack_bot_contract.py` falla si algo de eso
cambia por debajo.

## Cómo responde

- **Solo cuando lo mencionan** con `@capyassistant` en un canal habilitado. En los mensajes directos no hace
  falta mencionarlo.
- **Siempre en un hilo.** Una mención en la raíz del canal abre una conversación nueva, y el debate sigue en ese
  hilo. Cada hilo tiene su propia sesión en el provider.
- **Lee el debate.** Cuando le toca responder, relee el hilo desde su última respuesta. Las menciones son las
  preguntas; lo demás es contexto. Por eso cuentan también las ediciones y lo que se dijo sin arroba.
- **Junta lo que llega mientras responde.** Si le preguntan cinco cosas mientras contesta una, cuando termina
  responde las cinco en un solo turno. Devuelve una respuesta por pregunta, cada una en su mensaje y mencionando a
  quien preguntó. Si dos personas preguntan lo mismo, o una pregunta corrige a otra, responde una sola vez.
  Si se juntan más de 8 preguntas, las que sobran pasan al turno siguiente y el bot lo avisa.
- **Espera 3 s antes de arrancar**, para juntar las menciones que llegan casi al mismo tiempo.
- **Formato:** text, kpis, alert y action salen como Block Kit; la tabla, como el bloque `table` de Slack; bars,
  pie y trend, como imágenes PNG generadas en memoria con los colores del panel. Las fuentes que consultó van arriba
  ("Leyó: …"), como los chips del panel.

### Lo que muestra mientras trabaja

| Señal | Significado |
|---|---|
| 👀 en la pregunta | Recibida, en cola o respondiéndose |
| Estado del hilo ("está leyendo: Campañas · Amazon Ads") | Lo que consulta en este momento |
| ✅ | Respondida |
| 👌 | Lo mencionaron, pero no era una pregunta |
| ❌ | No se pudo responder; el bot explica por qué en el hilo |
| ⛔ | La persona llegó a su tope de preguntas en 24 horas |

Si no hay lugar libre, avisa cuántas conversaciones tiene por delante. Si llega al límite de la IA, avisa en cuántos
minutos reintenta (el dato sale del provider). Reintenta dos veces; si vuelve a fallar, avisa y deja de reintentar.
Si al modelo se le pasa una pregunta, se la vuelve a pedir una vez más en el turno siguiente; si tampoco la
responde, lo dice en el hilo.

## Perímetro

El MCP lee todas las cuentas con un token de servicio, así que el control de acceso vive en el bot:

- Solo responde en los canales de `SLACK_ALLOWED_CHANNELS` (con `*`, en cualquier canal donde lo hayan invitado), y
  nunca en un canal compartido con otra organización
  (Slack Connect), aunque esté en la lista. Lo verifica al recibir la mención y otra vez, preguntándole a Slack,
  justo antes de responder: si el canal se compartió afuera mientras la pregunta esperaba, no responde.
- Solo responde a miembros del workspace de la agencia: nunca a invitados ni a usuarios de otro workspace. Sus
  mensajes se descartan del lote, ni siquiera entran como contexto.
- Las herramientas son de solo lectura: el bot no cambia nada en las cuentas.
- Los mensajes del hilo viajan a Claude a través del provider, igual que lo que se escribe en el chat de la app.

## Puesta en marcha

1. **Crear la app** en <https://api.slack.com/apps> → *Create New App* → *From a manifest*, y pegar
   `services/slack_bot/slack_app_manifest.json`.
2. **Generar el token de la app**: *Basic Information* → *App-Level Tokens* → *Generate*, con el scope
   `connections:write`. Es el `xapp-…`.
3. **Instalar la app en el workspace**: *Install App*. Eso da el token del bot, `xoxb-…`.
4. **Invitar al bot** a cada canal donde va a responder: `/invite @capyassistant`. Al arrancar, el bot lista en su log
   los canales donde está y si cada uno está habilitado, con su ID para `SLACK_ALLOWED_CHANNELS`.
5. **Cargar en el `.env` del VPS** (`/srv/ppc-manager/.env`) las variables de abajo y desplegar. Sin los dos tokens,
   el contenedor `agency-slack-bot` registra un aviso y queda en espera, así que se puede desplegar antes de crear
   la app.

| Variable | Default | Qué hace |
|---|---|---|
| `SLACK_BOT_TOKEN` | — | Token del bot (`xoxb-…`) |
| `SLACK_APP_TOKEN` | — | Token de Socket Mode (`xapp-…`) |
| `SLACK_ALLOWED_CHANNELS` | vacío | IDs de canal separados por coma, o `*` para cualquier canal interno donde lo inviten. Vacío: solo mensajes directos |
| `SLACK_CHANNEL_ACCOUNTS` | vacío | JSON `{"C0123": {"client": "Love To Dream", "country": "MX"}}`. Es el cliente por defecto del canal; el país elige la región de Amazon Ads en vivo |
| `SLACK_ALLOW_DIRECT_MESSAGES` | `true` | Responder por mensaje directo |
| `SLACK_MAX_PARALLEL_TURNS` | `2` | Turnos simultáneos para todo Slack. El provider y la cuota de Claude son los mismos que usa la app |
| `SLACK_DAILY_QUESTIONS_PER_USER` | `40` | Tope por persona en 24 horas móviles |
| `SLACK_BATCH_MAX_QUESTIONS` | `8` | Preguntas por turno; las que sobran van al siguiente |
| `SLACK_BATCH_MAX_CHARS` | `12000` | Tope del debate que entra en un turno (el mismo que usa la app para la conversación previa) |
| `SLACK_GATHER_SECONDS` | `3` | Espera antes de arrancar, para juntar menciones casi simultáneas |
| `SLACK_EFFORT` | el del agente | Esfuerzo de los turnos (`low`, `medium`, `xhigh`); vacío usa el del orchestrator, igual que la app |
| `SLACK_RECOVERY_HOURS` | `12` | Al arrancar, cuántas horas hacia atrás busca menciones que se perdieron |

## Operación

- **Logs:** `docker logs agency-slack-bot`.
- **Costo y uso:** cada turno queda en `chat_turns` con `page = 'slack'`, con el costo que reporta el provider y las
  herramientas que usó.
- **Reinicios:** el estado de cada hilo (sesión, hasta dónde leyó, preguntas pendientes) vive en
  `/app/data/slack_bot/state.sqlite3`, en el volumen `slack_bot_state`, que pesa unos pocos KB. Al arrancar, el bot
  retoma los hilos que tenían preguntas pendientes y relee los canales habilitados desde el último evento que
  escuchó, porque Socket Mode no garantiza reenviar los eventos de una desconexión.
- **Respuestas que no llegaron a Slack:** las respuestas de cada turno se guardan en la misma transacción que la marca
  de agua y se publican paso a paso, anotando cada paso. Si el proceso se cae o Slack falla a mitad de camino, el bot
  sigue desde el paso donde quedó, sin volver a preguntarle al modelo. Un paso que falla tres veces se descarta.
  Lo único que se repite es un turno que todavía no tenía respuesta cuando se cortó.
- **Una sola instancia por app de Slack.** Si dos procesos usan los mismos tokens, Slack reparte los eventos entre
  los dos y cada uno tiene su propio estado. Para probar en local hay que crear otra app de Slack con el mismo
  manifiesto.
- **Desactivarlo:** borrar `SLACK_BOT_TOKEN` del `.env` y redesplegar.
