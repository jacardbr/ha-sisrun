"""Leitor da tela "Objetivos/Metas" (provas) do SisRUN (código desta integração).

Só biblioteca padrão. A tabela é achada pelo TEXTO dos cabeçalhos (Data,
Objetivo/Meta, Tempo, Prioridade, Situação, Status), nunca por ids gerados.
A tela mostra 15 linhas por vez; `pagination_fields` monta o pedido AJAX do
PrimeFaces para as demais.
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any

from .performance import _parse_date, _pt_number, _tables

RACES_PATH = "/sisrun/pages/meta/listaMeta.xhtml"
PAGE_SIZE = 15

_HEADER_FIELDS = (
    ("objetivo", "name"),
    ("meta", "name"),
    ("tempo", "when"),
    ("priorid", "priority"),
    ("situa", "situation"),
    ("status", "status"),
    ("data", "date"),
)

_TRAILING_KM = re.compile(r"\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*km\s*$", re.I)


def _map_columns(head: list[str]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, title in enumerate(head):
        text = title.lower()
        for needle, field in _HEADER_FIELDS:
            if needle in text:
                columns.setdefault(field, index)
                break
    return columns


def _split_name(full: str) -> tuple[str, float | None]:
    """'Maratona do Rio - 42 Km' -> ('Maratona do Rio', 42.0)."""
    match = _TRAILING_KM.search(full)
    if not match:
        return full, None
    return full[: match.start()].strip(), _pt_number(match.group(1))


def parse_races_html(raw: str) -> list[dict[str, Any]] | None:
    """Provas da tela, da mais nova para a mais antiga (ordem da própria tela).

    None quando a tabela não foi encontrada (login, layout novo...); [] se estiver vazia.
    """
    for table in _tables(raw):
        columns = _map_columns(table.head)
        if "date" not in columns or "name" not in columns:
            continue
        races: list[dict[str, Any]] = []
        for cells, row_id in zip(table.rows, table.row_ids):
            def cell(field: str) -> str:
                index = columns.get(field)
                return cells[index] if index is not None and index < len(cells) else ""

            day = _parse_date(cell("date"))
            if not day:
                continue
            full = cell("name")
            name, km = _split_name(full)
            race: dict[str, Any] = {
                "date": day,
                "name": name,
                "full_name": full,
                "distance_km": km,
                "priority": cell("priority"),
                "situation": cell("situation"),
                "status": cell("status"),
            }
            if row_id:
                race["id"] = row_id
            races.append(race)
        return races
    return None


def unwrap_partial(response: str) -> str:
    """Conteúdo HTML de uma resposta parcial do JSF (<update><![CDATA[...]]></update>)."""
    parts = re.findall(r"<update[^>]*><!\[CDATA\[(.*?)\]\]></update>", response, re.S)
    return "\n".join(parts) if parts else response


def races_total(raw: str) -> int | None:
    """'27 registros' do paginador."""
    m = re.search(r'ui-paginator-current">\s*(\d+)\s*registro', raw)
    return int(m.group(1)) if m else None


def races_table_id(raw: str) -> str:
    m = re.search(r'<div id="([^"]+)" class="ui-datatable[ "]', raw)
    return m.group(1) if m else "frmConsulta:tableMeta"


def _form_id(table_id: str) -> str:
    return table_id.split(":")[0]


def _selected_filters(raw: str, form: str) -> dict[str, str]:
    """Valor mostrado em cada filtro (select) do formulário; o navegador reenvia todos."""
    out: dict[str, str] = {}
    for m in re.finditer(r'<select id="(%s:[^"]+)"[^>]*>(.*?)</select>' % re.escape(form), raw, re.S):
        options = re.findall(r'<option value="([^"]*)"([^>]*)>', m.group(2))
        chosen = [v for v, attrs in options if "selected" in attrs]
        out[m.group(1)] = html_mod.unescape(chosen[-1] if chosen else (options[0][0] if options else ""))
    return out


def pagination_fields(raw: str, view_state: str, first: int, rows: int) -> dict[str, str]:
    """Campos do pedido AJAX que o paginador do PrimeFaces envia ao trocar de página."""
    table = races_table_id(raw)
    form = _form_id(table)
    fields = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": table,
        "javax.faces.partial.execute": table,
        "javax.faces.partial.render": table,
        table: table,
        f"{table}_pagination": "true",
        f"{table}_first": str(first),
        f"{table}_rows": str(rows),
        f"{table}_skipChildren": "true",
        f"{table}_encodeFeature": "true",
        form: form,
        f"{table}_selection": "",
    }
    fields.update(_selected_filters(raw, form))
    fields["javax.faces.ViewState"] = view_state
    return fields
