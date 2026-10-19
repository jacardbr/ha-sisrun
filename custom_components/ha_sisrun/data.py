"""Lógica pura sobre os treinos (sem dependência do Home Assistant).

Cada treino é um dict produzido por `sisrun_api.parser.parse_week_html`, com
chaves como: date (ISO), status, modality, workout_type, planned_km,
planned_km_is_est, intensity, hr_min, hr_max, structure, coach_note,
done_distance_km, done_time, done_hr.

Status possíveis: Proposto, Programado, Feito, Não Feito, Justificado,
Feito Avulso (atividade importada que NÃO foi prescrita).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

Workout = dict[str, Any]

PENDING_STATUSES = {"Proposto", "Programado"}
NOT_PRESCRIBED = {"Feito Avulso"}

REST_TEXT = "Sem treino"

# Campos que definem "o que o treinador prescreveu". Status e dados de execução
# ficam de fora de propósito: marcar um treino como feito não é mudar a planilha.
SIGNATURE_FIELDS = (
    "modality",
    "workout_type",
    "route",
    "planned_km",
    "intensity",
    "hr_min",
    "hr_max",
    "time_min",
    "time_max",
    "structure",
    "coach_note",
)
FIELD_LABELS = {
    "modality": "modalidade",
    "workout_type": "tipo",
    "route": "percurso",
    "planned_km": "distância",
    "intensity": "intensidade",
    "hr_min": "FC mínima",
    "hr_max": "FC máxima",
    "time_min": "tempo mínimo",
    "time_max": "tempo máximo",
    "structure": "estrutura",
    "coach_note": "observação",
}


def _num(value: Any) -> float:
    """Converte o valor do parser (float ou "") em float."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def prescribed(rows: list[Workout]) -> list[Workout]:
    """Treinos que o treinador prescreveu (exclui atividades avulsas)."""
    return [r for r in rows if r.get("status") not in NOT_PRESCRIBED]


def workouts_on(rows: list[Workout], day: date) -> list[Workout]:
    iso = day.isoformat()
    return [r for r in rows if r.get("date") == iso]


def first_today(rows: list[Workout], day: date) -> Workout | None:
    """Treino de `day` para os sensores de detalhe: o primeiro pendente, senão o primeiro."""
    todays = prescribed(workouts_on(rows, day))
    pending = [r for r in todays if r.get("status") in PENDING_STATUSES]
    return (pending or todays or [None])[0]


def next_pending(rows: list[Workout], today: date) -> Workout | None:
    """Primeiro treino ainda não feito, de hoje em diante."""
    iso = today.isoformat()
    candidates = [
        r for r in rows if r.get("status") in PENDING_STATUSES and r.get("date", "") >= iso
    ]
    candidates.sort(key=lambda r: r["date"])
    return candidates[0] if candidates else None


def week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def weekday_date(today: date, index: int) -> date:
    """Data do dia `index` (0 = segunda … 6 = domingo) na semana de `today`."""
    return week_bounds(today)[0] + timedelta(days=index)


def day_attrs(rows: list[Workout], day: date) -> dict[str, Any]:
    """Atributos de um sensor de dia da semana: data, status e treinos prescritos."""
    todays = prescribed(workouts_on(rows, day))
    return {
        "date": day.isoformat(),
        "statuses": [r.get("status") for r in todays],
        "workouts": todays,
    }


def _in_week(rows: list[Workout], day: date) -> list[Workout]:
    start, end = week_bounds(day)
    return [r for r in rows if start.isoformat() <= r.get("date", "") <= end.isoformat()]


def planned_km_week(rows: list[Workout], day: date) -> float:
    """Km prescritos na semana de `day` (usa `planned_km`, o número corrigido)."""
    return round(sum(_num(r.get("planned_km")) for r in prescribed(_in_week(rows, day))), 1)


def done_km_week(rows: list[Workout], day: date, prescribed_only: bool = False) -> float:
    """Km realizados na semana de `day`, segundo o que o SisRUN associou."""
    week = _in_week(rows, day)
    if prescribed_only:
        week = prescribed(week)
    return round(sum(_num(r.get("done_distance_km")) for r in week), 1)


def week_adherence(rows: list[Workout], day: date) -> dict[str, Any] | None:
    """Aderência da semana de `day`: treinos feitos / treinos prescritos.

    "Justificado" fica fora da conta (o treinador aceitou a falta). Devolve None
    quando a semana não tem treino prescrito (nada a medir).
    """
    week = prescribed(_in_week(rows, day))
    counts = Counter(r.get("status") for r in week)
    done = counts["Feito"]
    missed = counts["Não Feito"]
    justified = counts["Justificado"]
    pending = sum(counts[s] for s in PENDING_STATUSES)
    total = done + missed + pending
    if not total:
        return None
    planned = planned_km_week(rows, day)
    done_km = done_km_week(rows, day, prescribed_only=True)
    return {
        "percent": round(100 * done / total),
        "done": done,
        "pending": pending,
        "missed": missed,
        "justified": justified,
        "total": total,
        "planned_km": planned,
        "done_km": done_km,
        "km_percent": round(100 * done_km / planned) if planned else None,
    }


def describe(row: Workout) -> str:
    """Resumo curto de um treino, ex.: 'Corrida · Intervalado · 8.5 km'."""
    parts: list[str] = []
    modality = (row.get("modality") or "").strip()
    wtype = (row.get("workout_type") or "").strip()
    if modality:
        parts.append(modality)
    if wtype and wtype.lower() != modality.lower():
        parts.append(wtype)
    km = _num(row.get("planned_km"))
    if km:
        approx = "~" if row.get("planned_km_is_est") else ""
        parts.append(f"{approx}{km:.1f} km")
    return " · ".join(parts) or "Treino"


def day_summary(rows: list[Workout], day: date) -> str:
    """Texto do estado do sensor 'treino de hoje' (máx. 255 caracteres)."""
    todays = prescribed(workouts_on(rows, day))
    if not todays:
        return REST_TEXT
    return " + ".join(describe(r) for r in todays)[:255]


def event_summary(row: Workout) -> str:
    status = row.get("status")
    prefix = {"Feito": "✓ ", "Não Feito": "✗ "}.get(status, "")
    return f"{prefix}{describe(row)}"


def event_description(row: Workout) -> str:
    """Detalhes do treino para o corpo do evento no calendário."""
    lines: list[str] = [f"Status: {row.get('status', '?')}"]
    if row.get("route"):
        lines.append(f"Percurso: {row['route']}")
    if row.get("intensity"):
        lines.append(f"Intensidade: {row['intensity']}")
    if row.get("hr_min") or row.get("hr_max"):
        lines.append(f"FC: {row.get('hr_min') or '?'}–{row.get('hr_max') or '?'} bpm")
    if row.get("structure"):
        lines.append("Estrutura:")
        lines.extend(f"  {step}" for step in row["structure"].split(" | "))
    if row.get("coach_note"):
        lines.append(f"Treinador: {row['coach_note']}")
    if row.get("done_distance_km") not in ("", None):
        done = f"{_num(row['done_distance_km']):.1f} km"
        if row.get("done_time"):
            done += f" em {row['done_time']}"
        if row.get("done_hr"):
            done += f", FC média {row['done_hr']}"
        lines.append(f"Realizado: {done}")
    return "\n".join(lines)


# ---------- mudanças na planilha ----------


def _signature(row: Workout) -> tuple[str, ...]:
    return tuple(str(row.get(k) if row.get(k) is not None else "") for k in SIGNATURE_FIELDS)


def _changed_fields(before: Workout, after: Workout) -> list[str]:
    return [
        FIELD_LABELS[k]
        for k in SIGNATURE_FIELDS
        if str(before.get(k) if before.get(k) is not None else "")
        != str(after.get(k) if after.get(k) is not None else "")
    ]


def change_message(change: dict[str, Any]) -> str:
    """Frase pronta para notificação."""
    day = date.fromisoformat(change["date"]).strftime("%d/%m")
    before, after = change["before"], change["after"]
    if change["type"] == "added":
        return f"Novo treino em {day}: {describe(after)}"
    if change["type"] == "removed":
        return f"Treino de {day} removido: {describe(before)}"
    fields = ", ".join(change["fields"])
    return f"Treino de {day} alterado ({fields}): {describe(before)} → {describe(after)}"


def _make_change(kind: str, day: str, before: Workout | None, after: Workout | None) -> dict:
    change: dict[str, Any] = {
        "type": kind,
        "date": day,
        "before": before,
        "after": after,
        "fields": _changed_fields(before, after) if before and after else [],
    }
    change["message"] = change_message(change)
    return change


def diff_week(old_rows: list[Workout], new_rows: list[Workout]) -> list[dict[str, Any]]:
    """Diferenças de prescrição entre duas leituras da mesma semana.

    Compara só treinos prescritos e só os campos de `SIGNATURE_FIELDS`. Por dia,
    descarta o que é idêntico dos dois lados; do que sobra, emparelha em ordem
    como "alterado" e o excedente vira "novo" ou "removido".
    """
    old = prescribed(old_rows)
    new = prescribed(new_rows)
    changes: list[dict[str, Any]] = []
    for day in sorted({r["date"] for r in old} | {r["date"] for r in new}):
        pool = [r for r in old if r["date"] == day]
        leftover_new: list[Workout] = []
        for row in (r for r in new if r["date"] == day):
            sig = _signature(row)
            for i, candidate in enumerate(pool):
                if _signature(candidate) == sig:
                    del pool[i]
                    break
            else:
                leftover_new.append(row)
        for i in range(max(len(pool), len(leftover_new))):
            before = pool[i] if i < len(pool) else None
            after = leftover_new[i] if i < len(leftover_new) else None
            kind = "changed" if before and after else "added" if after else "removed"
            changes.append(_make_change(kind, day, before, after))
    return changes


# ---------- histórico por semana ----------


def merge_weeks(
    stored: dict[str, list[Workout]],
    parsed: dict[str, list[Workout]],
    missing_detail: set[str],
    current_monday: str,
    diff: bool = True,
) -> tuple[dict[str, list[Workout]], list[dict[str, Any]], list[str]]:
    """Junta semanas recém-lidas ao que já estava guardado.

    Devolve (semanas, mudanças, semanas_mantidas). Só gera mudanças para semanas
    de hoje em diante que já eram conhecidas: a primeira leitura de uma semana e
    o histórico passado não disparam aviso. Uma semana que veio sem os painéis
    de detalhe (site mudou) não sobrescreve a anterior, para não parecer que o
    treinador apagou a estrutura dos treinos.
    """
    weeks = dict(stored)
    changes: list[dict[str, Any]] = []
    kept: list[str] = []
    for start, new_rows in parsed.items():
        old_rows = weeks.get(start)
        if start in missing_detail and old_rows:
            kept.append(start)
            continue
        if diff and old_rows is not None and start >= current_monday:
            changes.extend(diff_week(old_rows, new_rows))
        weeks[start] = new_rows
    return weeks, changes, kept


def prune_weeks(weeks: dict[str, list[Workout]], keep: int) -> dict[str, list[Workout]]:
    """Mantém só as `keep` semanas mais recentes."""
    newest = sorted(weeks)[-keep:]
    return {start: weeks[start] for start in newest}


def flatten_weeks(weeks: dict[str, list[Workout]]) -> list[Workout]:
    return [row for start in sorted(weeks) for row in weeks[start]]


# ---------- testes de desempenho ----------

Test = dict[str, Any]

# Quantos testes entram no atributo `history` do sensor (o resto fica guardado).
MAX_HISTORY_IN_ATTRS = 50


def test_key(test: Test) -> str:
    """Identificador do teste: o `id` do SisRUN (data-rk) ou, sem ele, data+protocolo+tempo."""
    if test.get("id"):
        return f"id:{test['id']}"
    return f"{test.get('date')}|{test.get('protocol')}|{test.get('time')}"


def _newest_first(tests: list[Test]) -> list[Test]:
    return sorted(tests, key=lambda t: (t.get("date", ""), t.get("time_s") or 0), reverse=True)


def merge_tests(stored: list[Test], new: list[Test]) -> tuple[list[Test], list[Test]]:
    """Junta os testes lidos aos já guardados.

    Devolve (todos, do mais novo ao mais antigo; novos, do mais antigo ao mais novo).
    Um teste já conhecido é atualizado (o treinador pode corrigir um resultado);
    um teste que sumiu da tela continua no histórico.
    """
    merged = {test_key(t): t for t in stored}
    added: dict[str, Test] = {}
    for test in new:
        key = test_key(test)
        if key not in merged:
            added[key] = test
        merged[key] = test
    return _newest_first(list(merged.values())), list(reversed(_newest_first(list(added.values()))))


def latest_test(tests: list[Test]) -> Test | None:
    return _newest_first(tests)[0] if tests else None


def test_attrs(tests: list[Test]) -> dict[str, Any]:
    """Atributos do sensor: o último teste por extenso e o histórico completo."""
    latest = latest_test(tests)
    if not latest:
        return {}
    attrs: dict[str, Any] = {
        key: latest.get(key)
        for key in ("date", "protocol", "distance_km", "time", "pace", "speed_kmh", "vo2max")
    }
    attrs["tests_count"] = len(tests)
    attrs["history"] = _newest_first(tests)[:MAX_HISTORY_IN_ATTRS]
    return attrs


def test_message(test: Test) -> str:
    """Frase pronta para notificação de um teste novo."""
    day = date.fromisoformat(test["date"]).strftime("%d/%m/%Y")
    parts = [test.get("protocol") or "Teste"]
    if test.get("time"):
        parts.append(test["time"])
    if test.get("vo2max") is not None:
        parts.append("VO2 máx " + f"{test['vo2max']:.2f}".replace(".", ","))
    return f"Novo teste de desempenho em {day}: " + " · ".join(parts)
