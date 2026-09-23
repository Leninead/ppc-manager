"""The questions the chat's start screen offers: what it already answers well, the open page's own first.

Each one is sent exactly as the AM would type it. A page the chat can read adds its questions here, tied to that
page; a question without pages goes to the pool every page draws from. Each conversation draws its own ideas from
the pool, so a new session shows others and the same session keeps the ones it drew.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

LIMIT = 5


@dataclass(frozen=True)
class StarterQuestion:
    text: dict[str, str]
    pages: tuple[str, ...] = ()


STARTER_QUESTIONS: tuple[StarterQuestion, ...] = (
    StarterQuestion({"es": "¿Qué negativizo primero de este análisis?",
                     "en": "What should I negate first from this analysis?"}, ("📊 Search Term Report",)),
    StarterQuestion({"es": "¿Qué términos de este análisis paso a exact?",
                     "en": "Which terms from this analysis should I move to exact?"}, ("📊 Search Term Report",)),
    StarterQuestion({"es": "¿Qué campañas pausarías hoy?",
                     "en": "Which campaigns would you pause today?"}, ("📁 Bulk Campañas",)),
    StarterQuestion({"es": "¿Qué campañas rinden bien pero se quedan sin presupuesto?",
                     "en": "Which campaigns perform well but run out of budget?"}, ("📁 Bulk Campañas",)),
    StarterQuestion({"es": "¿A qué ASINs les subo o les bajo la puja?",
                     "en": "Which ASINs should I raise or lower bids on?"}, ("🧠 Bid Optimizer",)),
    StarterQuestion({"es": "¿Qué términos que venden no corren en ninguna campaña activa?",
                     "en": "Which selling terms don't run in any active campaign?"}, ("🔻 Análisis de Funnel",)),
    StarterQuestion({"es": "¿Quién vende más en este niche?",
                     "en": "Who sells the most in this niche?"}, ("🧲 DataDive Analyzer",)),
    StarterQuestion({"es": "¿Qué keywords del niche no estoy pautando?",
                     "en": "Which niche keywords am I not advertising on?"}, ("🧲 DataDive Analyzer",)),
    StarterQuestion({"es": "¿Qué ASIN tiene peor salud y por qué?",
                     "en": "Which ASIN has the worst health, and why?"}, ("🔎 PPC Insights",)),
    StarterQuestion({"es": "¿Cómo vienen los ads de todas las cuentas esta semana?",
                     "en": "How are ads doing across all accounts this week?"}),
    StarterQuestion({"es": "¿Qué campañas se están quedando sin presupuesto?",
                     "en": "Which campaigns are running out of budget?"}),
    StarterQuestion({"es": "¿Qué search terms conviene negativizar?",
                     "en": "Which search terms should I negate?"}),
    StarterQuestion({"es": "¿Qué search terms venden y todavía no tengo en exact?",
                     "en": "Which search terms sell and aren't in exact yet?"}),
    StarterQuestion({"es": "¿Qué cliente aumentó más el gasto este último mes?",
                     "en": "Which client increased spend the most this past month?"}),
    StarterQuestion({"es": "¿Qué campañas habilitadas no tuvieron impresiones esta semana?",
                     "en": "Which enabled campaigns had no impressions this week?"}),
    StarterQuestion({"es": "¿Qué keywords me están quemando plata?",
                     "en": "Which keywords are burning money?"}),
    StarterQuestion({"es": "¿Cómo vienen las ventas de ads este mes contra el anterior?",
                     "en": "How are ad sales this month compared with last month?"}),
    StarterQuestion({"es": "¿Qué ASINs venden más por publicidad?",
                     "en": "Which ASINs sell the most through ads?"}),
    StarterQuestion({"es": "¿Qué cambió esta semana en el rendimiento de una cuenta?",
                     "en": "What changed in an account's performance this week?"}),
    StarterQuestion({"es": "¿Qué portfolio se lleva más gasto y cómo rinde?",
                     "en": "Which portfolio takes the most spend, and how does it perform?"}),
    StarterQuestion({"es": "¿Qué debería hacer mañana en una cuenta?",
                     "en": "What should I do tomorrow in an account?"}),
)


def for_page(page: str, lang: str, seed: str = "", limit: int = LIMIT) -> list[str]:
    """The open page's own questions first, then others drawn from the pool, in the AM's language.

    The same `seed` and page draw the same questions; the app passes one per conversation.
    """
    draw = random.Random(f"{seed}:{page}")
    own = [question for question in STARTER_QUESTIONS if page in question.pages]
    pool = [question for question in STARTER_QUESTIONS if not question.pages]
    picked = draw.sample(own, len(own)) + draw.sample(pool, len(pool))
    return [question.text.get(lang) or question.text["es"] for question in picked][:limit]
