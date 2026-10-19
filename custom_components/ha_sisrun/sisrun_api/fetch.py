"""Leitura de várias semanas do SisRUN já interpretadas (código desta integração).

Ao contrário de `client.py` e `parser.py`, este arquivo é nosso: junta os dois.
Roda código bloqueante, então chame-o num executor.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SisrunClient, SisrunError
from .parser import detail_panels_missing, parse_week_html

_LOGGER = logging.getLogger(__name__)


def fetch_parsed(
    email: str, password: str, back: int, ahead: int
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    """Login + semana atual, `back` semanas para trás e `ahead` para frente.

    Devolve ({início_da_semana: treinos}, semanas_sem_painéis_de_detalhe).
    Semana que não pôde ser interpretada fica de fora (e é avisada no log); só
    levanta erro se NENHUMA semana pôde ser interpretada.
    """
    client = SisrunClient(email, password)
    weeks = client.fetch_weeks(back=back, ahead=ahead)

    parsed: dict[str, list[dict[str, Any]]] = {}
    missing_detail: set[str] = set()
    failures: list[str] = []
    for start in sorted(weeks):
        html = weeks[start]
        try:
            rows = parse_week_html(html)
        except Exception as err:  # noqa: BLE001 - o layout do site pode mudar de qualquer jeito
            failures.append(f"semana {start}: {err}")
            continue
        parsed[start] = rows
        if detail_panels_missing(html):
            missing_detail.add(start)
            _LOGGER.warning(
                "SisRUN: semana %s veio sem os detalhes dos treinos (estrutura/observações)",
                start,
            )

    if failures and not parsed:
        raise SisrunError("Não consegui interpretar as páginas do SisRUN: " + "; ".join(failures))
    for failure in failures:
        _LOGGER.warning("SisRUN: %s", failure)
    return parsed, missing_detail
