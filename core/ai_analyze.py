import os
import anthropic
from dotenv import load_dotenv

load_dotenv()


def _claude_analyze(prompt: str, max_tokens: int = 800) -> str:
    """
    Helper global para llamar a Claude API desde cualquier tab.
    Retorna el texto del análisis o un mensaje de error amigable.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "⚠️ API key no configurada. Verificá el archivo .env"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except anthropic.AuthenticationError:
        return "⚠️ API key inválida. Verificá el archivo .env"
    except anthropic.RateLimitError:
        return "⚠️ Límite de requests alcanzado. Esperá unos segundos y reintentá."
    except Exception as e:
        return f"⚠️ Error al conectar con Claude API: {str(e)}"


def _build_sqp_prompt(market_df, gap_df, client_name: str, brand: str) -> str:
    """
    Arma el prompt para análisis de SQP con datos reales.
    """
    # Top 10 oportunidades por revenue potencial
    oportunidades = market_df[
        market_df["Estado"].str.contains("Oportunidad", na=False)
    ].nlargest(10, "Revenue Potencial") if "Revenue Potencial" in market_df.columns else market_df.head(10)

    # Top 10 gaps por volumen
    top_gaps = gap_df.nlargest(10, "Total Impressions") if "Total Impressions" in gap_df.columns else gap_df.head(10)

    # Métricas resumen
    total_queries = len(market_df)
    dominando = len(market_df[market_df["Estado"].str.contains("Dominando", na=False)]) if "Estado" in market_df.columns else 0
    oportunidad_count = len(market_df[market_df["Estado"].str.contains("Oportunidad", na=False)]) if "Estado" in market_df.columns else 0
    is_promedio = market_df["Impression Share %"].mean() if "Impression Share %" in market_df.columns else 0

    prompt = f"""Sos un experto senior en Amazon PPC analizando la cuenta de {client_name}.
Marca: {brand}
Marketplace: Amazon

RESUMEN DE CUENTA:
- Total queries analizados: {total_queries}
- Queries dominando (IS >30%): {dominando}
- Queries oportunidad (IS <10%): {oportunidad_count}
- IS promedio de cuenta: {is_promedio:.1f}%

TOP OPORTUNIDADES (queries donde podés ganar terreno):
{oportunidades[["Search Query","Total Impressions","Impression Share %","Purchase Share %","Revenue Potencial"]].to_string(index=False) if not oportunidades.empty else "Sin datos"}

TOP GAPS (queries con mayor volumen donde no aparecés o rendís bajo):
{top_gaps[["Search Query","Total Impressions","Brand IS%","Market CVR%","Tipo de Gap"]].to_string(index=False) if not top_gaps.empty else "Sin datos"}

Generá un análisis ejecutivo en español con exactamente estas secciones:

📍 SITUACIÓN ACTUAL
[2-3 líneas describiendo el estado real de la cuenta basado en los datos]

🔴 ACCIÓN PRIORITARIA — ESTA SEMANA
[La acción más importante con query específico, qué hacer exactamente, bid sugerido si aplica, y por qué tiene el mayor ROI]

🟡 ACCIÓN 2 — ESTA SEMANA
[Segunda acción con query específico y pasos concretos]

🔵 OPORTUNIDAD MEDIANO PLAZO
[1 oportunidad para las próximas 2-4 semanas]

⚠️ ALERTA O RIESGO
[Un riesgo o problema detectado en los datos, o "Sin alertas críticas" si no hay]

Reglas:
- Máximo 280 palabras en total
- Directo y accionable — nada de generalidades
- Mencioná queries específicos con sus métricas reales
- No uses frases como "basándome en los datos" o "según el análisis"
"""
    return prompt


def _build_str_prompt(neg_df, harv_df, client_name: str, cvr: float,
                      target_acos: float) -> str:
    """
    Arma el prompt para análisis de STR (negativos + harvest).
    """
    prompt = f"""Sos un experto senior en Amazon PPC analizando el Search Term Report de {client_name}.

MÉTRICAS DE CUENTA:
- CVR promedio: {cvr:.1f}%
- Target ACoS: {target_acos:.0f}%

CANDIDATOS A NEGATIVIZAR ({len(neg_df)} términos):
{neg_df[["Search Term","Clicks","Spend","Orders","Regla","Prioridad"]].head(10).to_string(index=False) if not neg_df.empty else "Sin candidatos"}

CANDIDATOS A HARVEST ({len(harv_df)} términos):
{harv_df[["Search Term","Clicks","Orders","ACoS","CVR%","Bid Sugerido","Regla"]].head(10).to_string(index=False) if not harv_df.empty else "Sin candidatos"}

Generá un análisis ejecutivo en español con exactamente estas secciones:

📍 SITUACIÓN ACTUAL
[Estado del STR en 2 líneas]

🔴 NEGATIVIZAR AHORA
[Top 3 términos a negativizar con razón específica]

🟢 HARVESTEAR ESTA SEMANA
[Top 3 términos a harvestear con bid sugerido y tipo de campaña]

⚠️ ALERTA
[Patrón problemático detectado o "Sin alertas críticas"]

Máximo 200 palabras. Sin generalidades. Citá términos específicos.
"""
    return prompt
