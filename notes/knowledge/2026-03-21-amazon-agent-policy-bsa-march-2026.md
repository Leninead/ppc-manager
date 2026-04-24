# Amazon Agent Policy BSA — nueva ley para herramientas de automatización

## Metadata
- **Categoría:** Amazon · Compliance
- **Subcategoría:** Agent Policy · BSA · Automatización
- **Fecha de relevancia:** Vigente desde 4 marzo 2026
- **Fuente original:** Amazon Seller Central · PPC.land · EcommerceBytes
- **Fecha de captura:** 2026-03-21
- **Urgencia:** 🟡 Media

## Resumen ejecutivo
El 4 de marzo de 2026, Amazon actualizó su Business Solutions Agreement para incluir la primera Agent Policy formal en la historia de la plataforma. Cualquier software automatizado o AI que acceda a Amazon en nombre de un seller ahora tiene obligaciones contractuales explícitas: identificarse como sistema automatizado, cumplir la política en todo momento, y cesar acceso si Amazon lo solicita. Afecta a Atom 11, repricers, herramientas de restock, PPC platforms y cualquier app con acceso programático.

## Análisis detallado

### Qué cambió en el BSA
**Nueva Sección 19:** define y restringe el uso de software automatizado y agentes AI al acceder a Amazon Services.

**Tres obligaciones para todo agente:**
1. Identificarse claramente como sistema automatizado en todo momento
2. Cumplir la Agent Policy de forma continua
3. Cesar el acceso inmediatamente si Amazon lo solicita

**Nueva subsección 4.2:** prohíbe usar materiales o servicios de Amazon para desarrollar o mejorar modelos de AI/machine learning. Restricciones sobre data mining, ingeniería inversa y derivación de código fuente.

**Aceptación automática:** continuar vendiendo en Amazon después del 4 de marzo constituye aceptación de los cambios — sin formulario ni checkbox.

### Alcance real
Está en scope todo lo que interactúa programáticamente con Seller Central o Amazon Ads API:
- Herramientas de repricing
- Plataformas de gestión de PPC (Atom 11, Perpetua, Pacvue)
- Servicios de reembolso FBA (GETIDA, etc.)
- Herramientas de restock e inventario
- Browser automation y scraping tools
- Cualquier script que acceda a la API de Amazon

### Contexto estratégico
Según análisis de Vanessa Hung (CEO Online Seller Solutions), la Agent Policy + el límite de reviews visibles son movimientos coordinados para cerrar el pipeline de datos que permitía a herramientas de terceros construir sistemas de inteligencia usando datos del marketplace sin autorización ni compensación. Amazon lanzó simultáneamente su propio MCP Server (infraestructura controlada) y cerró el acceso no regulado.

## Aplicación práctica — Capybaras Agency

### Estado del PPC Manager
El PPC Manager actual trabaja con archivos CSV/Excel descargados manualmente — **no se conecta a la API de Amazon**. Riesgo de compliance: **cero** en el estado actual.

Si en el futuro se integra con el Amazon Ads MCP Server, esa integración queda bajo la Agent Policy — y el path correcto es usar el MCP Server oficial de Amazon, que cumple por diseño.

### Acciones para clientes
1. Preguntar a Atom 11 en forma escrita si su producto cumple la Agent Policy del 4 de marzo
2. Mismo ejercicio con cualquier otra herramienta de automatización que usen los clientes
3. Tener claro el "kill switch" — cómo desactivar herramientas automatizadas si Amazon lo requiere

### Lo que NO cambia
- Usar Campaign Manager manualmente: sin impacto
- Descargar reportes CSV manualmente: sin impacto
- El PPC Manager de Capybaras en su estado actual: sin impacto

## Fuentes
- [PPC.land — análisis completo](https://ppc.land/amazons-new-ai-agent-rules-shake-up-sellers-before-march-4-deadline/)
- [EcommerceBytes](https://www.ecommercebytes.com/2026/02/18/amazon-sellers-have-2-weeks-to-ensure-compliance-of-tools-they-use/)
- [Amazon Seller Central — anuncio oficial](https://sellercentral.amazon.com/seller-forums/discussions/t/84e3f6b1-42f7-4cf3-a189-a5cc8d78d838)
- [ecombrainly — policy tracker](https://ecombrainly.com/amazon-marketplace-policy-updates/)

## Tags
#amazon #politica #ai #agentes #automatización #compliance #bsa #atom11 #2026
