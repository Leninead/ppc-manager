"""Parámetros de negocio del módulo Mercado Libre.

Todos los umbrales de este archivo fueron acordados con el equipo de cuentas.
Viven acá y no dentro de la lógica para que se puedan ajustar sin tocar código
de negocio: cuando las chicas vean las primeras corridas es esperable que
quieran mover alguno.
"""
from __future__ import annotations

AREA = "marketplaces"
SCHEMA_VERSION = 1

MODULO_RENDIMIENTO = "meli-rendimiento"
MODULO_PUBLICACIONES = "meli-publicaciones"
MODULO_ADS = "meli-ads"

LOG_CAMBIOS = "cambios"
LOG_TRANSITO = "transito"

# ── Feature 1: tracker de cambios ────────────────────────────────────────────
# Un cambio se evalúa comparando la ventana previa contra la posterior.
VENTANA_DIAS = 14
UMBRAL_MEJORA = 0.10
UMBRAL_EMPEORO = -0.10
# Por debajo de este tráfico la variación de conversión es ruido: con 30 visitas
# y una conversión típica del 2% hablamos de menos de una venta por ventana.
MIN_VISITAS_EVALUACION = 30

TIPOS_CAMBIO = [
    "titulo",
    "precio",
    "imagenes",
    "ficha_tecnica",
    "descripcion",
    "variantes",
    "envio",
    "otro",
]

# Qué métrica mira primero cada tipo de cambio. Un cambio de título mueve
# visitas; uno de precio mueve conversión. Se calculan siempre las dos, esto
# solo define cuál se destaca en la lectura del resultado.
METRICA_PRINCIPAL = {
    "titulo": "visitas",
    "imagenes": "visitas",
    "envio": "visitas",
    "precio": "conversion",
    "ficha_tecnica": "conversion",
    "descripcion": "conversion",
    "variantes": "conversion",
    "otro": "conversion",
}

# ── Feature 2: sugerencia de stock ───────────────────────────────────────────
DIAS_COBERTURA_OBJETIVO = 30
DIAS_VELOCIDAD_VENTA = 15
# Sin mínimo de envío por decisión del equipo de cuentas.
MINIMO_ENVIO = 0
ESTADOS_EXCLUIDOS_STOCK = {"pausada", "inactiva", "finalizada", "cerrada"}

# ── Feature 3: alertas de ads ────────────────────────────────────────────────
ACOS_ALERTA_AMARILLA = 15.0
ROAS_ALERTA_ROJA = 3.0
# Debajo de este volumen de clics el ACOS y el ROAS no son estadísticamente
# significativos y generan alertas que no se pueden accionar.
MIN_CLICS_ALERTA = 20

# ── Presentación ─────────────────────────────────────────────────────────────
COLOR_MEJORO = "#1B6B2F"
COLOR_NEUTRO = "#6B7280"
COLOR_EMPEORO = "#B71C1C"
COLOR_SIN_DATOS = "#9CA3AF"
COLOR_ACENTO = "#E84000"
COLOR_SECUNDARIO = "#4F8CFF"
COLOR_AMARILLO = "#F59E0B"

RESULTADO_MEJORO = "mejoro"
RESULTADO_NEUTRO = "neutro"
RESULTADO_EMPEORO = "empeoro"
RESULTADO_SIN_DATOS = "sin_datos"
RESULTADO_PENDIENTE = "pendiente"

ETIQUETA_RESULTADO = {
    RESULTADO_MEJORO: "Mejoró",
    RESULTADO_NEUTRO: "Neutro",
    RESULTADO_EMPEORO: "Empeoró",
    RESULTADO_SIN_DATOS: "Sin datos suficientes",
    RESULTADO_PENDIENTE: "Pendiente de evaluación",
}

COLOR_RESULTADO = {
    RESULTADO_MEJORO: COLOR_MEJORO,
    RESULTADO_NEUTRO: COLOR_NEUTRO,
    RESULTADO_EMPEORO: COLOR_EMPEORO,
    RESULTADO_SIN_DATOS: COLOR_SIN_DATOS,
    RESULTADO_PENDIENTE: COLOR_SECUNDARIO,
}
