"""Cliente e parser do SisRUN.

`client.py` e `parser.py` são cópias sem alterações do projeto
https://github.com/cdutr/sisrun-mcp (licença MIT, veja LICENSE-sisrun-mcp na
raiz do pacote). O commit copiado está em UPSTREAM_COMMIT.txt.

`fetch.py` é código desta integração: junta cliente e parser.

Para atualizar quando o SisRUN mudar o site: copie as versões novas de
`client.py` e `parser.py` por cima, sem editar.
"""

from .client import SisrunClient, SisrunError
from .fetch import fetch_parsed
from .parser import detail_panels_missing, parse_week_html
from .performance import parse_performance_html

__all__ = [
    "SisrunClient",
    "SisrunError",
    "detail_panels_missing",
    "fetch_parsed",
    "parse_performance_html",
    "parse_week_html",
]
