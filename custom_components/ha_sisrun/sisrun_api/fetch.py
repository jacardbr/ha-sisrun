"""Leitura do SisRUN já interpretada (código desta integração).

Ao contrário de `client.py` e `parser.py`, este arquivo é nosso: junta o cliente
e os leitores. Roda código bloqueante, então chame-o num executor.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import BASE, SisrunClient, SisrunError
from .parser import detail_panels_missing, parse_week_html
from .performance import (
    PERFORMANCE_PATH,
    parse_performance_html,
    performance_diagnostic,
    performance_total,
)

_LOGGER = logging.getLogger(__name__)


def fetch_parsed(
    email: str, password: str, back: int, ahead: int, with_tests: bool = False
) -> tuple[dict[str, list[dict[str, Any]]], set[str], list[dict[str, Any]] | None]:
    """Login + semana atual, `back` semanas para trás e `ahead` para frente.

    Devolve ({início_da_semana: treinos}, semanas_sem_painéis_de_detalhe, testes).
    `testes` é a lista da tela "Teste de Desempenho" (ou None se não foi pedida ou
    se a leitura falhou: isso nunca derruba a leitura da planilha).
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

    tests = _fetch_tests(client) if with_tests else None
    return parsed, missing_detail, tests


def _fetch_tests(client: SisrunClient) -> list[dict[str, Any]] | None:
    """Testes de desempenho, ou None se a leitura falhar."""
    try:
        # `fetch_weeks` já deixou a sessão logada; reaproveitamos para não logar de novo.
        html = client._session.get(BASE + PERFORMANCE_PATH)  # noqa: SLF001
        tests = parse_performance_html(html)
    except Exception as err:  # noqa: BLE001 - nada aqui pode derrubar a planilha
        _LOGGER.warning("SisRUN: não consegui ler os testes de desempenho: %s", err)
        return None
    if tests is None:
        _LOGGER.warning(
            "SisRUN: tabela de testes de desempenho não encontrada (%s)",
            performance_diagnostic(html),
        )
        return None
    total = performance_total(html)
    if total is not None and total > len(tests):
        _LOGGER.warning(
            "SisRUN: a tela informa %d testes, mas só li %d (tabela paginada); "
            "os testes já guardados continuam no histórico",
            total,
            len(tests),
        )
    return tests
