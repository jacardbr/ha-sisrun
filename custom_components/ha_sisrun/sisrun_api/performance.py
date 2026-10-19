"""Leitor da tela "Teste de Desempenho" do SisRUN (código desta integração).

Só biblioteca padrão. A tabela é encontrada pelo TEXTO dos cabeçalhos (Data,
Protocolo, Distância, Tempo, Pace, Velocidade, VO2 Máx), nunca por ids gerados
pelo servidor, que mudam a cada deploy do SisRUN.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

PERFORMANCE_PATH = "/sisrun/pages/desempenho/listaDesempenho.xhtml"

# trecho do cabeçalho (minúsculo) -> campo; vale o primeiro que casar
_HEADER_FIELDS = (
    ("vo2", "vo2max"),
    ("protoc", "protocol"),
    ("prococ", "protocol"),
    ("pace", "pace"),
    ("veloc", "speed"),
    ("dist", "distance"),
    ("tempo", "time"),
    ("data", "date"),
)

_ALWAYS_SKIP = ("ui-helper-hidden-accessible",)
_CELL_SKIP = ("ui-column-title",)  # título repetido dentro das células no layout responsivo


class _Table:
    def __init__(self) -> None:
        self.head: list[str] = []
        self.rows: list[list[str]] = []
        self.row_ids: list[str | None] = []  # data-rk de cada linha (chave do registro no SisRUN)


class _TableParser(HTMLParser):
    """Coleta todas as <table> com cabeçalho (th) e linhas (td) como texto."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_Table] = []
        self._open: list[_Table] = []
        self._row: list[str] | None = None
        self._row_id: str | None = None
        self._row_has_th = False
        self._cell: list[str] | None = None
        self._cell_is_th = False
        self._skip = 0
        self._skip_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag == self._skip_tag:
                self._skip += 1
            return
        classes = dict(attrs).get("class") or ""
        if tag in ("script", "style") or (
            tag == "span"
            and (
                any(c in classes for c in _ALWAYS_SKIP)
                or (self._cell is not None and not self._cell_is_th
                    and any(c in classes for c in _CELL_SKIP))
            )
        ):
            self._skip, self._skip_tag = 1, tag
            return
        if tag == "table":
            self._open.append(_Table())
        elif tag == "tr" and self._open:
            self._row, self._row_has_th = [], False
            self._row_id = dict(attrs).get("data-rk")
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._cell_is_th = [], tag == "th"
            self._row_has_th = self._row_has_th or tag == "th"

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag == self._skip_tag:
                self._skip -= 1
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._open:
            table = self._open[-1]
            if self._row_has_th:
                if len(self._row) > len(table.head):
                    table.head = self._row
            elif self._row:
                table.rows.append(self._row)
                table.row_ids.append(self._row_id)
            self._row = None
        elif tag == "table" and self._open:
            self.tables.append(self._open.pop())

    def handle_data(self, data: str) -> None:
        if not self._skip and self._cell is not None:
            self._cell.append(data)


def _tables(raw: str) -> list[_Table]:
    parser = _TableParser()
    parser.feed(raw)
    parser.close()
    return parser.tables


def _map_columns(head: list[str]) -> dict[str, int]:
    """campo -> posição da coluna, a partir do texto dos cabeçalhos."""
    columns: dict[str, int] = {}
    for index, title in enumerate(head):
        text = title.lower()
        for needle, field in _HEADER_FIELDS:
            if needle in text:
                columns.setdefault(field, index)
                break
    return columns


def _pt_number(text: str) -> float | None:
    """Número no formato brasileiro: 14,17 / 3.000 / 49,61. None se não houver número."""
    match = re.search(r"\d[\d.,]*", text or "")
    if not match:
        return None
    s = match.group(0).rstrip(".,")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _parse_distance_km(text: str) -> float | None:
    value = _pt_number(text)
    if value is None:
        return None
    if re.search(r"\d\s*m\b", text, re.I) and not re.search(r"km", text, re.I):
        return round(value / 1000, 3)
    return round(value, 3)


def _parse_clock(text: str) -> tuple[str, int] | None:
    """'00:12:42' ou '12:42' -> ('00:12:42', 762)."""
    m = re.search(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", text)
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return f"{h:02d}:{mi:02d}:{s:02d}", h * 3600 + mi * 60 + s


def _parse_pace(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _parse_row(cells: list[str], columns: dict[str, int]) -> dict[str, Any] | None:
    def cell(field: str) -> str:
        index = columns.get(field)
        return cells[index] if index is not None else ""

    day = _parse_date(cell("date"))
    if not day:
        return None
    clock = _parse_clock(cell("time"))
    vo2 = _pt_number(cell("vo2max"))
    speed = _pt_number(cell("speed"))
    return {
        "date": day,
        "protocol": cell("protocol"),
        "distance_km": _parse_distance_km(cell("distance")),
        "time": clock[0] if clock else None,
        "time_s": clock[1] if clock else None,
        "pace": _parse_pace(cell("pace")),
        "speed_kmh": round(speed, 2) if speed is not None else None,
        "vo2max": round(vo2, 2) if vo2 is not None else None,
    }


def parse_performance_html(raw: str) -> list[dict[str, Any]] | None:
    """Testes da tela, do mais novo para o mais antigo.

    Devolve None quando a tabela de testes não foi encontrada (página de login,
    layout novo...) e [] quando ela existe mas está vazia.
    """
    tables = _tables(raw)
    for table in tables:
        columns = _map_columns(table.head)
        if "date" not in columns or "protocol" not in columns:
            continue
        # layouts com cabeçalho e corpo em tabelas separadas: pega o corpo da vizinha
        source = table if table.rows else next(
            (u for u in tables
             if u is not table and u.rows and len(u.rows[0]) == len(table.head)),
            table,
        )
        tests: list[dict[str, Any]] = []
        for cells, row_id in zip(source.rows, source.row_ids):
            if len(cells) != len(table.head):  # descarta a linha "nenhum registro"
                continue
            parsed = _parse_row(cells, columns)
            if parsed:
                if row_id:
                    parsed["id"] = row_id
                tests.append(parsed)
        tests.sort(key=lambda t: (t["date"], t["time_s"] or 0), reverse=True)
        return tests
    return None


def performance_total(raw: str) -> int | None:
    """Total de registros que o paginador da tela informa ("7 registros"), se houver.

    A tela mostra 15 testes por página; se o total for maior que o número de
    linhas lidas, a leitura veio incompleta.
    """
    m = re.search(r'ui-paginator-current">\s*(\d+)\s*registro', raw)
    return int(m.group(1)) if m else None


def performance_diagnostic(raw: str) -> str:
    """Resumo curto do que a página tem, para o log quando a tabela não é encontrada."""
    tables = _tables(raw)
    heads = [" | ".join(t.head)[:120] for t in tables if t.head][:3]
    login = "Acesso ao Sistema" in raw
    return (
        f"{len(tables)} tabela(s); cabeçalhos: {heads or 'nenhum'}"
        + ("; parece a tela de login (sessão expirada?)" if login else "")
    )
