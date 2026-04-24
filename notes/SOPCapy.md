**🦫 CAPYBARAS AGENCY**

**LAUNCH SOP**

Amazon PPC Management Framework

Versión 2026 | Actualizado: Marzo 2026

*Este documento contiene la metodología oficial de lanzamiento y gestión
de campañas PPC de Capybaras Agency, actualizada con las mejores
prácticas de la industria para 2026.*

## 0. FUNDAMENTOS PPC 2026 --- Lo que cambió

El ecosistema de Amazon Ads cambió de forma fundamental entre 2024 y
2026. Estos son los cambios clave que impactan directamente cómo
ejecutamos campañas:

**Cambios estructurales del algoritmo**

-   Rufus AI: El nuevo motor de búsqueda conversacional de Amazon
    procesa queries como preguntas ('What's the best swaddle for a
    3-month-old?'). Los listings y keywords deben responder intención,
    no solo matchear términos.

-   CPC promedio superó $1.00 USD en 2025 (+18-32% vs 2023). Gestión
    manual de bids ya no es viable a escala.

-   Learning periods: Amazon tiene períodos de aprendizaje similares a
    Meta/Google. Cambiar bids más de 1 vez por semana reinicia el
    aprendizaje y desestabiliza el rendimiento.

-   60%+ de los resultados de búsqueda en Amazon ahora están
    personalizados por el algoritmo. La relevancia de persona importa
    tanto como la relevancia de keyword.

-   ASIN targeting superó en muchas categorías a keyword-only campaigns
    para adquisición de clientes nuevos.

**Principios que NO cambiaron**

-   La métrica de lanzamiento sigue siendo ranking y velocity --- no
    ACoS.

-   El ACoS de lanzamiento SIEMPRE es más alto. El objetivo real es
    TACoS a 90 días.

-   Estructura antes que bids: primero negativos correctos, luego ajuste
    de bids.

-   Fixed bid en las primeras 2 semanas de cualquier campaña nueva.

-   Harvesting a partir de 3 órdenes + ACoS ≤ 25% (regla Capybaras ---
    se mantiene).

## 1. PRE-LANZAMIENTO --- Semana -1

**Checklist de listing**

-   Título optimizado: incluir keywords conversacionales al estilo Rufus
    (ej: 'para bebés 0-3 meses')

-   A+ Content terminado --- mandatorio ANTES de encender ads

-   Imágenes principales competitivas --- si CTR es bajo, las imágenes
    son el problema

-   Fecha de lanzamiento configurada via flat file a futuro

-   Mínimo 5 reseñas planeadas (Vine o red de contactos)

**Definición de métricas objetivo**

> *⚠️ Hacer este ejercicio ANTES de tocar ninguna campaña. Sin estas
> métricas no hay forma de saber si el performance es bueno o malo.*

  -----------------------------------------------------------------------
  **Métrica**              **Fórmula**                 **Ejemplo**
  ------------------------ --------------------------- ------------------
  Break-Even ACoS          Margen bruto % = (Precio -  Precio $50, COGS
                           COGS - FBA fees) / Precio   $15, FBA $8 → BE
                                                       ACoS = 54%

  Target ACoS Launch (Sem  Hasta 1.5× Break-Even ACoS  BE 54% → Target
  1-4)                                                 launch = hasta 81%

  Target ACoS Profit (Sem  ≤ Break-Even ACoS           ≤ 54%
  5+)                                                  

  Clicks threshold         (1 / CVR_producto) × 2      CVR 10% → 20
  negativización                                       clicks; CVR 5% →
                                                       40 clicks

  Spend threshold          50% del precio de venta     Producto $30 →
  negativización                                       negativizar si
                                                       gastó $15 sin
                                                       ventas
  -----------------------------------------------------------------------

**Configuración de Portfolios (obligatorio desde día 1)**

Crear 4 portfolios en Campaign Manager antes de lanzar cualquier
campaña:

-   \[Marca\] | RANKING --- campañas de posicionamiento, tolerancia
    ACoS alta

-   \[Marca\] | PROFIT --- campañas en fase de escala rentable

-   \[Marca\] | BRAND DEFENSE --- siempre encendido, budget fijo

-   \[Marca\] | DISCOVERY --- autos + broads, harvesting constante

## 2. SEMANA 0 --- Preparación final

-   Verificar inventario distribuido correctamente en FBA (fully
    received)

-   Precio de lanzamiento definido (puede ser mayor al target para dar
    margen a cupones)

-   Cupones 10-15% activados para boost de conversión en primeras 2
    semanas

-   Precio target para semana 6 definido y agendado

-   Objetivo #1 New Release Badge --- PRIORITARIO --- verificar
    categoría y sub-categoría correcta

## 3. SEMANA 1 --- Lanzamiento Exact + Product Targeting

Estrategia de bid: FIXED BID en todo el lanzamiento hasta semana 3. El
Dynamic bidding en fase launch gasta presupuesto en placements de baja
calidad.

### 3.1 Exact Match --- Ranking Campaigns

  -----------------------------------------------------------------------
  **Parámetro**               **Configuración**
  --------------------------- -------------------------------------------
  Bidding Strategy            Fixed Bid (NO Dynamic)

  Bid base                    1.5× suggested bid

  Top of Search Modifier      +50%

  Product Pages Modifier      0%

  Budget diario               $10-15 USD por campaña

  Portfolio                   \[Marca\] | RANKING
  -----------------------------------------------------------------------

**Estructura de keywords por volumen de búsqueda (SV):**

-   KWs con SV < 1,000: Single Keyword Campaign (SKC) --- máximo
    control de bid y placement

-   KWs con SV 1,000-5,000: clusters de 3-5 keywords de intent similar

-   KWs con SV > 5,000: evaluar caso por caso --- alto gasto, lanzar
    solo si el ROI lo justifica

> *⚠️ IMPORTANTE: Si hay múltiples variaciones en el mismo Parent, meter
> TODAS en el mismo Ad Group la semana 1. A los 7 días analizar cuál
> convierte mejor. Si hay wasted spend sin conversiones, reducir al hero
> ASIN. Verificar siempre el indexing antes de cortar variantes.*

### 3.2 Product Targeting --- Competitor Attack (lanzar desde Día 1)

En 2026, el ASIN targeting enseña al algoritmo de Amazon qué tipo de
shopper compra tu producto. NO esperar al 80% de indexing para lanzar
estas campañas.

-   Targets: top 15 ASINs más relevantes del nicho (competidores
    directos)

-   Budget: $10-12 USD/día | Portfolio: \[Marca\] | RANKING

-   Bid: higher end del bid range sugerido

-   Optimizar a los 7 días: apagar todo lo que tenga ACoS > 2× target
    ACoS o 0 clicks en 7 días

## 4. SEMANA 2 --- Método Cascada Completo

La lógica del método cascada es cubrir todos los placements con bids
distintos. Cada match type tiene diferente probabilidad de aparecer en
Top of Search:

  --------------------------------------------------------------------------
  **Match Type**  **Bid           **Placement más       **Función
                  (cascada)**     probable**            principal**
  --------------- --------------- --------------------- --------------------
  Exact           100% (base)     Top of Search (alta   Ranking + conversión
                                  prob.)                directa

  Phrase          80% del Exact   Rest of Search,       Expansión controlada
                  bid             eventual ToS          

  Broad / BMM     60% del Exact   PDP y Rest of Search  Discovery y
                  bid                                   harvesting

  Auto (4 camps)  Bid             Todos los placements  Datos + harvest new
                  independiente                         terms
  --------------------------------------------------------------------------

**Phrase Match**

-   Tomar KWs con CVR% más alto del STR de semana 1

-   Bid: 80% del bid de Exact Match

-   Opción: agregar negative exact de esas mismas KWs para canalizar
    tráfico hacia Exact

> **🔴 NUNCA negativizar la keyword en la campaña Exact Match. En Exact,
> el control es via bid, no via negativos.**

**Broad Match**

-   Tomar KWs con CVR% más alto

-   Bid: 60% del bid de Exact Match

-   Función: harvesting de nuevos search terms --- NO rentabilidad
    directa

**Auto Campaigns --- 4 campañas separadas**

-   SP Auto --- Close Match | Budget $8-10 | Portfolio: DISCOVERY

-   SP Auto --- Loose Match | Budget $6-8 | Portfolio: DISCOVERY

-   SP Auto --- Complements | Budget $6-8 | Portfolio: DISCOVERY

-   SP Auto --- Substitutes | Budget $8-10 | Portfolio: DISCOVERY

> *⚠️ Fixed bid en todas las autos durante semana 1-2. Revisar STR a los
> 3-4 días para primeros candidatos a harvest o negativización.*
>
## 5. SEMANA 3 --- Primera Optimización y Negativización

Cambiar bidding strategy a Dynamic Down-Only para campañas que ya tienen
historial. Mantener Fixed Bid solo en campañas donde el ranking aún no
está consolidado.

### 5.1 Reglas de Negativización 2026

IMPORTANTE: Las reglas anteriores (≥3 clicks, >500 impresiones) estaban
mal. Con 3 clicks no hay suficiente data estadística para sentenciar una
keyword. Las reglas correctas son:

  ----------------------------------------------------------------------------
  **Regla**      **Criterio**           **Acción**            **Tipo
                                                              negativo**
  -------------- ---------------------- --------------------- ----------------
  1 ---          1-2 clicks en término  Negar inmediatamente  Negative Exact
  Irrelevancia   claramente fuera del   sin esperar más data  
  obvia          nicho                                        

  2 --- No       Clicks sin conversión  Negar Ej: CVR 10% →   Negative Exact
  conversión por ≥ (1/CVR) × 2 Mínimo   esperar 20 clicks Ej: 
  CVR            absoluto: 10 clicks    CVR 5% → esperar 40   
                                        clicks                

  3 --- Gasto    Gasto acumulado > 50% Negar inmediatamente  Negative Exact
  sin conversión del precio de venta    Ej: producto $30 →   
                 del producto           negar si gastó $15   
                                        sin ventas            

  4 --- ACoS     ACoS > 70% con < 5   Bajar bid primero. Si Negative Phrase
  extremo        órdenes NO aplicar si  persiste y no es      (patrón) o Exact
                 es ranking keyword     ranking KW, negar     

  5 --- CTR bajo > 2,500 impresiones Y Negar por             Negative Phrase
  por            CTR < 0.18% Y 0       irrelevancia (500     
  irrelevancia   conversiones           impresiones es        
                                        insuficiente)         
  ----------------------------------------------------------------------------

> **🔴 NUNCA agregar negativos dentro de una campaña Exact Match propia.
> Si una keyword en Exact rinde mal, la solución es bajar el bid o
> pausarla --- nunca negativizar.**
>
> **🔴 NUNCA negativizar un search term que está en Exact activo, aunque
> tenga ACoS alto en Broad/Phrase. El ranking se construye con ventas,
> no solo con eficiencia.**

### 5.2 Limpieza del STR --- Campaña por campaña

-   Apagar search terms en Broad/Phrase con ACoS > 70% y pocas órdenes
    --- EXCEPTO si ese término está en Exact activo

-   Apagar campañas donde no hay movimiento de ranking y solo hay gasto

-   Aplicar negativos solo a Auto, Broad y Phrase --- nunca a Exact o
    PAT

-   Mantener cualquier término que esté moviendo ranking, aunque el ACoS
    sea alto

### 5.3 Trending ACoS

Trending ACoS = ¿Si el siguiente click fuera una venta, cuál sería el
ACoS?

Si Trending ACoS > Break-Even ACoS Y la keyword no es de ranking →
evaluar bajar bid o negativizar.

## 6. SEMANA 4 --- Harvesting

**Reglas de Harvesting Capybaras 2026**

  ------------------------------------------------------------------------
  **Regla**        **Criterio**       **Acción**         **Nota**
  ---------------- ------------------ ------------------ -----------------
  Principal (se    ≥ 3 órdenes Y ACoS Harvest a Exact    ACoS ≤ 25%
  mantiene)        ≤ 25%              Match con          generalmente
                                      suggested bid      implica CVR ≥ 10%

  Por CVR alto     CVR ≥ 10% Y clicks Harvest a Exact    Alta intención de
                   ≥ 15               aunque no haya 3   compra confirmada
                                      órdenes aún        

  Por volumen 2026 ≥ 5 órdenes        Harvest a Exact    El volumen de
  (nuevo)          (independiente del --- impacta        ventas importa
                   ACoS)              ranking orgánico   más que el ACoS
                                                         en esta regla

  CVR 7-10%        ≥ 3 órdenes con    Analizar caso por  Si el precio es
                   CVR 7-10%          caso --- puede     alto, puede ser
                                      convenir igual     rentable igual

  CVR < 7%        < 7% CVR          No harvest salvo ≥ Posible problema
                                      5 órdenes totales  de listing, no de
                                                         targeting
  ------------------------------------------------------------------------

**Proceso de harvesting**

1.  Exportar STR de las últimas 2-4 semanas

2.  Filtrar por criterios de la tabla anterior

3.  Para cada término a harvestear: crear Exact Match campaign dedicada
    en Portfolio PROFIT

4.  Bajar bid en la campaña de origen para ese término (evitar
    canibalización)

5.  Opcional: agregar el término como negative exact en la campaña de
    origen --- NO en la Exact nueva

6.  Monitorear 2 semanas: escalar si funciona, pausar si no

> *⚠️ Si el search term estaba en Phrase → también se puede lanzar en
> Broad para más datos. Si tenía buen rendimiento en Phrase → lanzar en
> Exact y Broad simultáneamente.*
>
> **✅ Tip: conectar Scale Insights para automatizar los criterios de
> optimización una vez pasado el período de warm-up (2 semanas).**
>
## 7. SEMANA 5 --- Expansión

Requisito: mínimo 20-25 reviews antes de escalar.

### 7.1 Expansión de targeting

-   Category Targeting: apuntar a categorías y sub-categorías relevantes

-   Product Targeting adicional: competidores secundarios, productos
    complementarios, listings débiles (pocas reviews, precio mayor)

-   Phrase y Broad en términos nuevos descubiertos en las autos

### 7.2 Sponsored Brands --- PRIORITARIO (no opcional en 2026)

SBV (Sponsored Brand Video) tiene el CTR más alto de todos los formatos
de Amazon en 2026. Ya no es un extra --- es obligatorio en cualquier
estrategia competitiva.

-   SBV: llevar tráfico al listing (NO al storefront si no está
    optimizado)

-   El storefront solo convierte si tiene tráfico propio --- de lo
    contrario, mandar al listing directamente

-   Budget inicial SBV: $15-20 USD/día

-   Objetivo: presencia en Top of Search con video → reduce CPC en
    Sponsored Products

-   Keyword en headline: usar la keyword de mayor conversión

-   Mensaje: benefit-driven, no feature-driven ('Para que tu bebé
    duerma mejor' vs 'Material 100% algodón')

### 7.3 Sponsored Display --- Retargeting

-   Audiencia principal: visitantes del listing que NO compraron
    (últimos 14 días)

-   Audiencia secundaria: compradores de productos complementarios
    (cross-sell)

-   Budget: $5-10 USD/día como inicio

-   Estrategia: Optimize for Conversions

> *⚠️ El horario pico de conversión en Amazon es 9AM-12PM y 7PM-11PM.
> Los bids de SD se pueden ajustar por horario si se usa una herramienta
> de dayparting.*
>
## 8. SEMANA 6+ --- Scaling y Optimización Continua

-   Precio en target price definitivo

-   Reviews objetivo: 30+ para competir en la mayoría de nichos

-   Análisis de keyword gaps via SQP (Search Query Performance report)
    --- ver share of voice vs competidores

-   Reverse ASIN de top 3 competidores con Helium 10 para descubrir
    keywords no encontradas

-   Testear nuevos nichos donde el producto puede adaptarse

-   Evaluar DSP si el presupuesto mensual de ads supera $5,000 USD

-   Correr experimentos A/B en listings (título, imágenes, A+) una vez
    que el volumen sea suficiente

## 9. REGLAS GLOBALES 2026

  -----------------------------------------------------------------------------
  **#**   **Regla**                         **Razón**
  -------- --------------------------------- ----------------------------------
  1        No cambiar bids más de 1 vez por  Amazon tiene learning periods ---
           semana                            cambios frecuentes reinician el
                                             aprendizaje y desestabilizan
                                             impresiones

  2        Fixed bid las primeras 2 semanas  Dynamic bidding en fase inicial
           de cualquier campaña nueva        desperdicia presupuesto en
                                             placements de baja calidad

  3        No pausar campañas en ranking     El ranking se construye con
           activo aunque ACoS esté alto      ventas. Pausar destruye el
                                             momentum

  4        Optimizar estructura antes que    Orden correcto: 1° negativos
           bids                              correctos, 2° ajuste de bids, 3°
                                             presupuesto

  5        NUNCA negativizar dentro de Exact Si Exact rinde mal → bajar bid o
           Match propia                      pausar. Nunca negar dentro de
                                             Exact

  6        Top of Search Modifier: +50% en   ToS tiene el mayor impacto en
           ranking Exact, +25% en harvest    ranking orgánico --- vale pagar el
           Exact                             premium

  7        Product Pages Modifier: 0% en     No desperdiciar budget de ToS en
           todo lo que no sea PAT dedicado   placements de PDP fuera de product
                                             targeting

  8        La métrica de lanzamiento es      El ACoS de lanzamiento siempre es
           ranking y velocity --- no ACoS    alto. El objetivo real es TACoS a
                                             90 días

  9        Minimum 2.500 impresiones para    500 impresiones es insuficiente
           juzgar CTR                        para tomar decisiones de
                                             negativización por CTR

  10       Threshold de negativización =     Con menos data, se están matando
           (1/CVR) × 2 clicks mínimo         keywords por falta de estadística,
                                             no por mal rendimiento
  -----------------------------------------------------------------------------

## 10. PLACEMENT MODIFIERS --- Guía de referencia

Los placement modifiers son una de las palancas más subutilizadas en
PPC. En 2026 son obligatorios en cualquier cuenta bien estructurada.

  ------------------------------------------------------------------------
  **Tipo de campaña** **Top of Search **Product Pages **Razón**
                      Modifier**      Modifier**      
  ------------------- --------------- --------------- --------------------
  Exact --- Ranking   +50%            0%              Maximizar ToS para
  (semana 1-4)                                        construir ranking

  Exact ---           +25%            0%              Mantener ToS con
  Harvest/Profit                                      menor inversión
  (semana 5+)                                         

  Phrase ---          +10%            0%              Algo de ToS sin
  Discovery                                           gastar demasiado

  Broad --- Discovery 0%              0%              Dejar que Amazon
                                                      optimice sin
                                                      preferencia

  Auto --- All types  0%              0%              Discovery puro ---
                                                      no forzar placements

  PAT --- Competitor  0%              +50%            PDP es el placement
  Attack                                              correcto para PAT

  Sponsored Display   N/A             N/A             SD no usa estos
  --- Retargeting                                     modifiers
  ------------------------------------------------------------------------

## 11. ESTRUCTURA DE PORTFOLIOS --- Referencia

  ----------------------------------------------------------------------------
  **Portfolio**   **Tipo de          **Bid        **Target       **KPI
                  campaña**          strategy**   ACoS**         principal**
  --------------- ------------------ ------------ -------------- -------------
  \[Marca\] |    SP Exact match     Fixed Bid    Hasta 1.5× BE  Ranking
  RANKING         ranking SP PAT                  ACoS           position +
                  Competitor                                     velocity

  \[Marca\] |    SP Exact harvest   Dynamic      ≤ BE ACoS      ACoS + ROAS
  PROFIT          SP Phrase          Down-Only                   
                  refinadas                                      

  \[Marca\] |    SP Exact brand     Fixed Bid    < 10% ACoS    Impression
  BRAND DEFENSE   terms SB/SBV brand                             Share en
                                                                 brand terms

  \[Marca\] |    SP Auto (4 camps)  Fixed Bid    Tolerante      Nuevos search
  DISCOVERY       SP Broad           luego        (harvesting)   terms +
                                     Down-Only                   nuevos ASINs
  ----------------------------------------------------------------------------

## 12. NAMING CONVENTION --- Capybaras Standard

Formato estándar para todas las campañas:

> **\[Marca\] | \[ASIN/Producto\] | \[Marketplace\] |
> \[Tipo\]-\[SubTipo\] | \[Match/Target\] | \[Cluster/Tema\] |
> \[KW/Target\]**

**Ejemplos por tipo:**

  -----------------------------------------------------------------------
  **Tipo**              **Ejemplo**
  --------------------- -------------------------------------------------
  SP Exact Ranking      Setex | B081GB8F89 | MX | SP-KWS | EXACT |
                        almohadillas lentes | almohadillas para anteojos

  SP Auto Close Match   LTD | B09MG1PM6L | MX | SP-AUTO | CLOSE |
                        swaddle discovery

  SP PAT Competitor     M&B | B0F6LB9T22 | MX | SP-PAT | ASIN | COMP
                        TOP15

  SP Phrase Expansion   Setex | B081GB8F89 | MX | SP-KWS | PHRASE |
                        nose pads cluster

  SBV Brand             LTD | MX | SBV | BRAND | sacos dormir bebe

  SD Retargeting        M&B | MX | SD | RETARGET | visitors 14d
  -----------------------------------------------------------------------

## 13. SEÑALES DE ALARMA --- Cuándo actuar inmediatamente

  ------------------------------------------------------------------------
  **Señal**          **Umbral**         **Acción inmediata**
  ------------------ ------------------ ----------------------------------
  ACoS campaña       > 100% por 7+     Revisar search terms, bajar bid
                     días               20%, verificar que el listing
                                        convierte

  BuyBox perdido     < 80% en ASIN con Revisar precio vs competidores ese
                     > 30              mismo día
                     sesiones/semana    

  CVR caída brusca   Baja > 30% semana Revisar si el listing cambió, si
                     a semana           hay review negativa, si competidor
                                        bajó precio

  Budget agotado     100% budget        Subir budget o reorganizar
  todos los días     consumido 7 días   campañas --- se están perdiendo
                     seguidos           impresiones

  Impresiones caen a 0 impresiones en   Revisar bid vs sugerido, verificar
  cero               campaña activa     que el ASIN no esté suprimido

  TACoS > 30% en    Semana 6+ con      Auditoria de estructura:
  cuenta madura      TACoS > 30%       identificar campañas que gastan
                                        sin ventas

  Keyword en warm-up Campaña < 2       NO optimizar --- es warm-up
  con ACoS > 40%    semanas de vida    normal. Esperar 14 días antes de
                                        juzgar
  ------------------------------------------------------------------------

## 14. CALENDARIO DE OPTIMIZACIÓN

  --------------------------------------------------------------------------
  **Frecuencia**   **Tarea**                          **Fuente de datos**
  ---------------- ---------------------------------- ----------------------
  Cada 3-4 días    Revisar STR de autos/broads para   Search Term Report
                   negativos urgentes                 

  Semanal          Ajuste de bids (máx 1 vez/semana   Bulk file + Atom 11
                   por campaña)                       

  Semanal          Negativización formal (reglas 1-5  STR + reglas de
                   de sección 5)                      thresholds

  Semanal          Harvesting de nuevos search terms  STR + reglas sección 6

  Semanal          Revisión de budget: campañas       Campaign Manager
                   agotando diariamente               

  Quincenal        Análisis SQP --- share of voice vs SQP Report
                   competidores                       

  Mensual          Auditoría de estructura: campañas  Bulk file + STR
                   con 0 ventas en 30 días            

  Mensual          Reverse ASIN de top 3 competidores Helium 10 / Data Dive

  Mensual          Revisión de naming convention y    Campaign Manager
                   portfolios                         
  --------------------------------------------------------------------------

## 15. GLOSARIO

  -----------------------------------------------------------------------
  **Término**        **Definición**
  ------------------ ----------------------------------------------------
  ACoS               Advertising Cost of Sale = Spend / Ad Sales × 100.
                     Métrica de eficiencia publicitaria.

  TACoS              Total ACoS = Spend / Total Sales × 100. Incluye
                     ventas orgánicas. La métrica real de salud de
                     cuenta.

  Break-Even ACoS    El ACoS máximo que podés tener sin perder dinero =
                     Margen bruto %

  Target ACoS        El ACoS que querés alcanzar según el objetivo
                     (launch vs profit)

  Trending ACoS      ¿Si el siguiente click fuera una venta, cuál sería
                     el ACoS? Indica si vale la pena seguir.

  CVR                Conversion Rate = Orders / Clicks × 100. Tasa de
                     conversión de clicks a ventas.

  SV                 Search Volume. Volumen de búsqueda mensual estimado
                     de una keyword.

  SKC                Single Keyword Campaign. Una campaña con un solo Ad
                     Group y una sola keyword.

  ToS                Top of Search. El placement más premium y de mayor
                     impacto en ranking orgánico.

  PDP                Product Detail Page. El placement que aparece en la
                     página de un competidor.

  Warm-up            Las primeras 2 semanas de una campaña nueva donde el
                     algoritmo está aprendiendo.

  Velocity           Velocidad de ventas. Unidades/día promedio. Impacta
                     directamente el ranking orgánico.

  Harvest            El proceso de tomar search terms que convirtieron en
                     Auto/Broad y agregarlos como Exact Match.

  Rufus AI           El nuevo motor de búsqueda conversacional de Amazon
                     que procesa queries como preguntas naturales.

  Learning period    El período en que el algoritmo de Amazon necesita
                     para optimizar una campaña. Cambios frecuentes lo
                     reinician.
  -----------------------------------------------------------------------

Capybaras Agency --- Confidencial --- v2026
