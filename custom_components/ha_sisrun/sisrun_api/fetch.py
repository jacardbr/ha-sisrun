"""Leitura do SisRUN já interpretada (código desta integração).

Ao contrário de `client.py` e `parser.py`, este arquivo é nosso: junta o cliente
e os leitores. Roda código bloqueante, então chame-o num executor.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import BASE, SisrunClient, SisrunError, navigate, week_label, week_start_iso
from .parser import detail_panels_missing, parse_week_html
from .races import (
    PAGE_SIZE,
    RACES_PATH,
    pagination_fields,
    parse_races_html,
    races_total,
    unwrap_partial,
)
from .performance import (
    PERFORMANCE_PATH,
    parse_performance_html,
    performance_diagnostic,
    performance_total,
)

_LOGGER = logging.getLogger(__name__)


def fetch_parsed(
    email: str, password: str, back: int, ahead: int, with_extras: bool = False
) -> tuple[
    dict[str, list[dict[str, Any]]],
    set[str],
    list[dict[str, Any]] | None,
    list[dict[str, Any]] | None,
]:
    """Login + semana atual, `back` semanas para trás e `ahead` para frente.

    Devolve ({início_da_semana: treinos}, semanas_sem_painéis_de_detalhe, testes, provas).
    `testes` e `provas` são as listas das telas "Teste de Desempenho" e "Objetivos/Metas"
    (None se `with_extras` é falso ou se a leitura falhou: isso nunca derruba a leitura
    da planilha).
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

    tests = _fetch_tests(client) if with_extras else None
    races = _fetch_races(client) if with_extras else None
    return parsed, missing_detail, tests, races


# Para "todo o histórico": para depois de tantas semanas seguidas sem treino, ou no teto.
ALL_HISTORY_EMPTY_WEEKS = 16
ALL_HISTORY_MAX_WEEKS = 520


def fetch_all_parsed(
    email: str, password: str
) -> tuple[dict[str, list[dict[str, Any]]], set[str], None, None]:
    """Volta semana a semana desde a atual até acabar o histórico.

    Acaba quando `ALL_HISTORY_EMPTY_WEEKS` semanas seguidas vêm sem treino (a cauda
    vazia não é guardada), quando o SisRUN não deixa recuar mais, ou no teto de
    `ALL_HISTORY_MAX_WEEKS` semanas. Devolve o mesmo formato de `fetch_parsed`.
    """
    client = SisrunClient(email, password)
    current = client.current_week_html()
    parsed: dict[str, list[dict[str, Any]]] = {}
    missing_detail: set[str] = set()
    empty_streak = 0
    body = current
    for step in range(ALL_HISTORY_MAX_WEEKS + 1):
        start = week_start_iso(body)
        if start in parsed:
            break  # não recuou: chegou ao começo do que o SisRUN mostra
        try:
            rows = parse_week_html(body)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("SisRUN: semana %s: %s", start, err)
            rows = []
        parsed[start] = rows
        if rows and detail_panels_missing(body):
            missing_detail.add(start)
        empty_streak = 0 if rows else empty_streak + 1
        if empty_streak >= ALL_HISTORY_EMPTY_WEEKS or step == ALL_HISTORY_MAX_WEEKS:
            break
        body = navigate(client._session, body, -1)  # noqa: SLF001
        if not body or not week_label(body):
            break
        if step and step % 25 == 0:
            _LOGGER.info("SisRUN: importando histórico... %d semanas lidas", step)

    # tira a cauda vazia (mas nunca a semana atual)
    for start in sorted(parsed):
        if parsed[start]:
            break
        if start != week_start_iso(current):
            del parsed[start]
    if not any(parsed.values()):
        raise SisrunError("Nenhum treino encontrado no histórico do SisRUN.")
    return parsed, missing_detail, None, None


def _race_key(race: dict[str, Any]) -> str:
    return f"id:{race['id']}" if race.get("id") else f"{race.get('date')}|{race.get('full_name')}"


def _fetch_races(client: SisrunClient) -> list[dict[str, Any]] | None:
    """Provas da tela "Objetivos/Metas" (todas as páginas), ou None se a leitura falhar."""
    session = client._session  # noqa: SLF001 - já logada pela leitura da planilha
    url = BASE + RACES_PATH
    try:
        page = session.get(url)
        races = parse_races_html(page)
    except Exception as err:  # noqa: BLE001 - nada aqui pode derrubar a planilha
        _LOGGER.warning("SisRUN: não consegui ler as provas: %s", err)
        return None
    if races is None:
        _LOGGER.warning("SisRUN: tabela de provas (metas) não encontrada")
        return None
    total = races_total(page)
    if not total or len(races) >= total:
        return races

    def post(first: int, rows: int) -> list[dict[str, Any]]:
        body = session.post(url, pagination_fields(page, session.view_state, first, rows))
        return parse_races_html(unwrap_partial(body)) or []

    # 1) tenta pedir tudo de uma vez (o paginador manda `rows` e o servidor obedece)
    try:
        everything = post(0, total)
        if len(everything) >= total:
            return everything
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("SisRUN: pedido único de provas falhou: %s", err)
    # 2) página por página
    merged = {_race_key(r): r for r in races}
    for first in range(PAGE_SIZE, total, PAGE_SIZE):
        try:
            for race in post(first, PAGE_SIZE):
                merged.setdefault(_race_key(race), race)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("SisRUN: não consegui ler a página %d das provas: %s", first // PAGE_SIZE + 1, err)
            break
    if len(merged) < total:
        _LOGGER.warning("SisRUN: li %d de %d provas", len(merged), total)
    return sorted(merged.values(), key=lambda r: r["date"], reverse=True)


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
