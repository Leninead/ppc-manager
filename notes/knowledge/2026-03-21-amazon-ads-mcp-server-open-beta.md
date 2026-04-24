# Amazon Ads MCP Server — Claude ya puede manejar tus campañas

## Metadata
- **Categoría:** AI × Amazon
- **Subcategoría:** MCP · Automatización PPC
- **Fecha de relevancia:** Q1 2026
- **Fuente original:** Amazon Ads oficial · AdExchanger · MCP Playground
- **Fecha de captura:** 2026-03-21
- **Urgencia:** 🔴 Alta

## Resumen ejecutivo
El 2 de febrero de 2026, Amazon lanzó el Amazon Ads MCP Server en open beta. Claude, ChatGPT o Gemini pueden conectarse directamente a la API de Amazon Ads mediante lenguaje natural — sin integraciones custom. Crea campañas, ajusta bids, genera reportes y expande a nuevos marketplaces con un solo prompt. Es la infraestructura que convierte la gestión manual de PPC en gestión agentiva.

## Análisis detallado

### Qué es
El Amazon Ads MCP Server es la implementación oficial de Amazon del Model Context Protocol — el estándar abierto creado por Anthropic que permite a modelos AI conectarse a herramientas externas con acceso autenticado en tiempo real. Actúa como capa de traducción entre el agente AI y la Amazon Ads API.

### Capacidades actuales (open beta)
- **+50 herramientas** que abarcan Sponsored Products, Sponsored Brands, Sponsored Display, DSP y AMC
- Prefijos de herramientas: `cp_` campañas · `sp_` Sponsored Products · `dsp_` DSP · `amc_` AMC workflows · `ac_` perfiles
- Crear campaña completa de Sponsored Products (campaign + ad group + ads) en un solo prompt — reemplaza 15-20 minutos de trabajo manual
- Expandir campaña a otro marketplace con un prompt
- Pausar todas las campañas con ROAS bajo X con un prompt
- Acceso disponible globalmente para Amazon Ads partners con API credentials activos

### Impacto documentado
- Tareas de reporting que tomaban 8 horas semanales → 45 minutos
- Reducciones de ACoS de 12%+ por mayor frecuencia de optimización
- Compatibilidad nativa con Claude, ChatGPT y Gemini sin integraciones custom adicionales

### Contexto estratégico
Amazon construyó el MCP Server para resolver el problema N×M: antes, conectar Claude a Amazon Ads requería una integración custom. Conectar ChatGPT requería otra. Con MCP, cualquier AI que hable el protocolo se conecta con una sola integración. Amazon hostea la infraestructura; el advertiser trae su propio LLM o agente.

## Aplicación práctica — Capybaras Agency

### Acciones inmediatas
1. Verificar si los clientes (LTD, M&B, Setex, Dermaglos) tienen API credentials de Amazon Ads activados
2. Probar el MCP Server desde Claude Desktop con una cuenta de prueba — ya es posible sin código nuevo
3. Mapear qué tareas operativas semanales se pueden delegar al agente: harvesting, negativización, reportes

### Para el PPC Manager (roadmap)
- El Amazon Ads MCP Server es la infraestructura que valida toda la Sección 3 (Ejecución) del plan maestro
- El **Bulk Upload Builder** previsto como UI manual puede reemplazarse por un módulo que ejecuta directamente via MCP
- El **Automation Rules Builder** puede convertirse en un generador de prompts para el agente MCP en lugar de archivos bulk para Atom 11
- Prioridad: evaluar si los clientes pueden obtener API credentials — ese es el único prerequisito

### Acciones mediano plazo
- Construir flujo: PPC Manager detecta oportunidad → genera prompt → Claude via MCP ejecuta en Amazon
- Evaluar Amazon Q (el agente propio de Amazon) vs Claude+MCP para tareas de optimización

## Fuentes
- [Amazon Ads oficial — anuncio open beta](https://advertising.amazon.com/library/news/amazon-ads-mcp-server-open-beta)
- [MCP Playground — guía completa de workflows](https://mcpplaygroundonline.com/blog/amazon-ads-mcp-claude-automation-guide)
- [ClearAds — explicación técnica](https://clearadsagency.com/what-is-amazons-mcp-server-and-how-does-it-change-advertising-for-sellers/)
- [AdExchanger — análisis](https://www.adexchanger.com/marketers/amazon-ads-opens-a-beta-test-for-its-new-mcp-server/)
- [Digiday — contexto industria](https://digiday.com/media-buying/ad-tech-briefing-amazon-launches-mcp-server-for-agent-driven-advertising/)

## Tags
#amazon #mcp #ai #automatización #ppc #claude #ads-api #agentes #2026 #urgente
