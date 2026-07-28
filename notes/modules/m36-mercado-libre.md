---
tipo: modulo
modulo: M36
seccion: Marketplaces
actualizado: 2026-07-25
---

# M36 — Mercado Libre

Módulo de operación de cuentas de Mercado Libre. Tres features pedidas por el equipo de cuentas (Cleimery Bravo, Josefina Mastromatteo): seguimiento de cambios en publicaciones, sugerencia de reposición de stock y alertas de campañas de Product Ads. Multi-cuenta, carga manual de Excel.

## 2026-07-24 — Build inicial de las 3 features + instalación

Módulo completo montado sobre core/persistence.py (misma capa que M28/M30, sin construir storage nuevo). AREA=marketplaces, cliente=slug de cuenta, tres módulos de persistencia separados: meli-rendimiento, meli-publicaciones, meli-ads.

- **Feature 1 — Change Tracker** (equivalente MELI del M28): cruza el log de cambios contra el histórico de snapshots de rendimiento, compara ventana de 14 días pre/post sobre visitas y conversión, clasifica por tipo de cambio. Umbrales confirmados por Josefina: mejoró ≥+10%, empeoró ≤-10%, sin datos <30 visitas. Necesita 2 períodos cargados para mostrar resultados.
- **Feature 2 — Stock Advisor**: velocidad de venta sobre días reales del reporte × 30 días de cobertura − stock − tránsito a tiempo. Prioriza por facturación, ordena urgencia por días de cobertura. Excluye FULL/pausadas/inactivas.
- **Feature 3 — Ads Alerts**: semáforo ACOS>15 (amarillo) / ROAS<3 (rojo), min 20 clics. Tres poblaciones separadas: con tráfico, sin impresiones, pocos clics. Nivel anuncio y campaña.
- **Parsers**: resuelven el bug de formato numérico español (punto de miles que pandas lee como decimal → 1.564 visitas se leían como 1,564) y la normalización de IDs (rendimiento sin prefijo MLA, publicaciones/ads con prefijo).
- Period en YYYY-MM-DD (fecha fin del reporte), no YYYY-WW: los períodos de MELI no caen en semanas ISO.
- El log de cambios (cambios.parquet vía _append_log) reemplaza al Google Sheet de modificaciones. Sin tracked-skus.json: se cargan todas las publicaciones del reporte.
- Instalado en app.py (sección MARKETPLACES nueva), registrado, AppTest verde. Commit 4ef2100.

## 2026-07-24 — Fix schema publicaciones vs output derivado

Hallazgo en test: el schema meli-stock documentaba la salida del advisor (sugerido, urgencia, velocidad) pero lo que se persiste es el crudo de publicaciones (mla, titulo, estado, stock, precio, variantes), y no se validaba. Renombrado a meli-publicaciones-v1, validación agregada en el import, lógica de reposición movida a sección derived_output. Criterio: se persiste el dato de origen, no el derivado — si cambia el horizonte 30→45 días se recalcula sobre el histórico. Dato adicional: el dtype de `unidades` en la salida es data-dependent (int64/float64 según haya publicaciones sin match en el merge), razón extra para no validarla. Commit 6ae7566.

## 2026-07-25 — Pulido de presentación

Correcciones de fricción tras prueba manual en UI con datos reales: placeholders de multiselect en español (stock, tracker), color+emoji en la columna Urgencia de Stock (patrón de alerts.py, colores de config), aviso cuando "En tránsito" está vacío, help= en español en los uploaders. Commits 17e9a05, f3c4486.

**Limitación conocida**: el texto interno del file_uploader ("Drag and drop file here" / "Limit 200MB") no es traducible — Streamlit no soporta i18n de ese componente y ningún módulo del repo lo resuelve. Se dejó con help= en español. Override de CSS descartado por frágil (se rompe con updates de Streamlit).

## Estado

- Branch feat/modulo-mercado-libre (worktree ppc-manager-meli), 5 commits, sin pushear. Push sale del consolidador.
- Código terminado y probado. E2E con los 7 números de negocio OK (247/206/43.153/323/4/9/17), AppTest sin excepciones.
- Umbrales de ads NO independientes: ROAS<3 ⟺ ACOS>33%, así que todo rojo también es amarillo. Es lo pedido; editable en config.py. A mostrar a las chicas en la primera corrida.

## Pendientes

- Exports de las otras 3 cuentas → verificar parsers contra todos los formatos (único punto que puede obligar a tocar código).
- Confirmar filtro de estados: en el export de referencia ninguna publicación salió pausada/inactiva.
- Segundo reporte de rendimiento (~31/07) → primera validación real del Change Tracker.
- Backlog: vista simplificada para cliente.
