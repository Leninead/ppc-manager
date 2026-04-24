Claude + Nano Banana — Generación de imágenes Amazon listing con AI
Metadata

Categoría: AI × Amazon
Subcategoría: Creación de contenido visual · Listing Optimization · Automatización
Fecha de relevancia: Q1 2026
Fuente original: Google DeepMind · aimaker.substack.com · Medium (Ziadi Lotfi) · TechCrunch
Fecha de captura: 2026-03-21
Urgencia: 🔴 Alta


Resumen ejecutivo
"Nano Banana" es el apodo popular del modelo de generación de imágenes de Google basado en Gemini. En 2026 hay tres versiones activas: la original, Nano Banana Pro (Gemini 3 Pro Image) y Nano Banana 2 (Gemini 3.1 Flash Image, lanzado el 26 de febrero de 2026). El stack Claude + Nano Banana permite generar sets completos de imágenes Amazon — infografías, lifestyle shots, imágenes A+, A+ de marca — desde una sola foto del producto, en minutos, a un costo de $0.04–$0.15 por imagen. El "ingrediente secreto" del post viral es usar Claude para redactar el prompt y Nano Banana para generar la imagen — dos modelos especializados haciendo lo que cada uno hace mejor.

Análisis detallado
Las tres versiones activas en 2026
VersiónModelo oficialVelocidadResoluciónCosto APIAccesoNano Banana (original)Gemini 2.5 Flash ImageRápido2K~$0.04/imgGemini app gratisNano Banana ProGemini 3 Pro ImageLento (Thinking)2K~$0.13–$0.24/imgGemini Pro/UltraNano Banana 2Gemini 3.1 Flash ImageMuy rápido4K~$0.04–$0.15/imgDefault en Gemini app
Nano Banana 2 es el punto óptimo: calidad de Pro a velocidad de Flash, 4K, y es el modelo default desde el 26 de febrero de 2026.
Por qué funciona para Amazon
Tres capacidades clave que lo hacen diferente a otros generadores:

Text rendering que funciona — genera texto legible dentro de las imágenes. Crítico para infografías Amazon donde los bullets visuales deben ser legibles. Usa un sistema de verificación de tres pasos (Plan → Evaluate → Improve) para cada caracter.
Consistencia de producto — mantiene la fidelidad de hasta 14 objetos en un mismo workflow. Para un set de 7 imágenes de listing, el producto se ve igual en todas.
Upload de hasta 14 imágenes de referencia — se puede cargar el producto desde múltiples ángulos + logo + paleta de marca + ejemplos de competidores. El modelo hace síntesis de todo el contexto visual.

El workflow Claude + Nano Banana (el "proceso" del post)
Flujo manual básico (Gemini app, gratis):

Sacar 3-5 fotos del producto (ángulo general, contexto de escala, macro de detalles/texto)
Abrir Google Gemini app → cambiar modelo a "Thinking" (= Nano Banana Pro) o usar default (= Nano Banana 2)
Subir las fotos
Escribir el prompt de la imagen deseada
Siempre descargar antes de descartar — Gemini aplica procesamiento final al descargar

Flujo avanzado Claude + Nano Banana MCP (automatizable):

Claude analiza el listing (bullets, keywords, A+ existente) y determina qué imágenes necesita el set
Claude genera los prompts optimizados para cada imagen (lifestyle, infográfica, comparativa, hero)
Nano Banana ejecuta la generación via MCP Server o API de Gemini
Claude evalúa las imágenes generadas y decide si re-generar o aceptar
Output: set completo de imágenes listo para subir a Seller Central

El MCP de Nano Banana para Claude Code ya existe como skill público. Permite que Claude Code genere imágenes directamente desde el terminal sin salir del entorno de desarrollo.
Costos reales

Set de 7 imágenes de listing con API Nano Banana 2: $0.28–$1.05
Mismas imágenes con fotógrafo profesional: $200–$800
Con iteraciones (3–4 rounds de refinamiento): <$5 por set completo

El truco del texto en productos con label (skincare, suplementos)
Para productos con texto en el packaging (como Dermaglos):

Subir una foto macro del logo/texto del packaging específico
En un prompt separado dentro del mismo chat: "The label text is low resolution. I have uploaded a reference image. Please fix the label on the bottle."
El modelo "Thinking" puede leer la foto de referencia y parchear el texto correctamente en la imagen generada.


Aplicación práctica — Capybaras Agency
Uso inmediato — Dermaglos USA (prioridad máxima)
Dermaglos tiene el caso de uso perfecto: producto de skincare con packaging con texto, audiencia hispanohablante, y listing que acaba de ser optimizado en Fase 1.
Workflow propuesto:

Sacar 4 fotos del cream y 4 del lotion (wide, context, macro label, macro texture)
Usar Claude (este chat) para generar los prompts de 7 imágenes por ASIN:

Hero shot con fondo blanco
Lifestyle (noche, baño, piel seca)
Infográfica de ingredientes (Vitamin A + Allantoin)
Comparativa vs CeraVe (visual de diferenciación)
Instrucciones de uso paso a paso
Antes/después (si hay assets existentes)
Imagen de audiencia (mujer hispanohablante USA, nocturno)


Nano Banana 2 genera cada imagen con los prompts de Claude
Resultado: set completo A+ listo para subir

Costo estimado: <$5 por ASIN · Tiempo estimado: 30–45 minutos por ASIN
Para Love To Dream MX y Mott & Bow MX
Útil para A+ content de variantes — si un ASIN tiene múltiples colores/tallas, Nano Banana 2 mantiene consistencia del producto en todos los ángulos. Una sesión fotográfica del producto base → set para todas las variantes.
Para el PPC Manager (roadmap futuro)
Módulo propuesto: "🎨 Listing Image Builder"

Input: fotos del producto + keywords del SQP + bullets del listing
Claude genera los prompts de imagen basados en los search terms que más convierten
Nano Banana API genera las imágenes
Output: set descargable de imágenes optimizadas para conversion
El diferencial: las imágenes responden visualmente a las queries del comprador, no solo muestran el producto

Prerequisito técnico: integración con Gemini API (Google AI Studio, pay-as-you-go, sin subscripción mínima).

Setup técnico — Cómo conectar
Opción 1 — Manual (gratis, sin código)

Google Gemini app (iOS/Android) o gemini.google.com
Modelo: cambiar a "Thinking" para Pro, o usar el default (ya es NB2)
Límite free: 20 imágenes/día (NB2) en el plan gratuito

Opción 2 — API (pay-as-you-go, para agencia)

Google AI Studio: aistudio.google.com → crear API key
Modelo: gemini-3.1-flash-image-preview (NB2) o gemini-3-pro-image (Pro)
Costo: ~$0.04–$0.15/imagen, sin mínimo mensual

Opción 3 — MCP Server en Claude Code (workflow integrado)

Instalar el skill de Nano Banana para Claude Code (GitHub: kkoppenhaver/cc-nano-banana)
Claude Code genera imágenes directamente desde el terminal
Las imágenes se guardan en ./nanobanana-output/
Requiere Gemini API key configurada


Implicaciones estratégicas

Las imágenes de listing son el nuevo ad creativo — con Rufus AI generando prompts desde el contenido visual del listing, la calidad de las imágenes afecta directamente qué conversaciones de Rufus activa el producto.
La barrera de entrada visual desaparece — una agencia boutique puede producir contenido visual de calidad Kerastase ($2.4B) sin estudio fotográfico. El diferencial se desplaza a estrategia y prompt design.
El stack Claude + Nano Banana es complementario, no competitivo — Claude razona sobre qué imagen necesita el listing para convertir; Nano Banana la genera. Dos modelos, dos trabajos distintos.


Fuentes

Google DeepMind — Nano Banana Pro oficial
Google Blog — Nano Banana 2 launch
TechCrunch — Nano Banana 2 análisis
aimaker.substack — Claude + Nano Banana workflow
Medium / Ziadi Lotfi — Amazon listing guide
Google Cloud — Nano Banana Pro enterprise
GitHub — cc-nano-banana Claude Code skill


Tags
#ai #nanobanana #gemini #claude #listing #amazon #imagenes #aplus #creativo #workflow #dermaglos #2026
