"""Lógica pura sobre os treinos (sem dependência do Home Assistant).

Cada treino é um dict produzido por `sisrun_api.parser.parse_week_html`, com
chaves como: date (ISO), status, modality, workout_type, planned_km,
planned_km_is_est, intensity, hr_min, hr_max, structure, coach_note,
done_distance_km, done_time, done_hr.

Status possíveis: Proposto, Programado, Feito, Não Feito, Justificado,
Feito Avulso (atividade importada que NÃO foi prescrita).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

Workout = dict[str, Any]

PENDING_STATUSES = {"Proposto", "Programado"}
NOT_PRESCRIBED = {"Feito Avulso"}

REST_TEXT = "Sem treino"


def _num(value: Any) -> float:
    """Converte o valor do parser (float ou "") em float."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def prescribed(rows: list[Workout]) -> list[Workout]:
    """Treinos que o treinador prescreveu (exclui atividades avulsas)."""
    return [r for r in rows if r.get("status") not in NOT_PRESCRIBED]


def workouts_on(rows: list[Workout], day: date) -> list[Workout]:
    iso = day.isoformat()
    return [r for r in rows if r.get("date") == iso]


def pending_on(rows: list[Workout], day: date) -> list[Workout]:
    return [r for r in workouts_on(rows, day) if r.get("status") in PENDING_STATUSES]


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


def _in_week(rows: list[Workout], day: date) -> list[Workout]:
    start, end = week_bounds(day)
    return [r for r in rows if start.isoformat() <= r.get("date", "") <= end.isoformat()]


def planned_km_week(rows: list[Workout], day: date) -> float:
    """Km prescritos na semana de `day` (usa `planned_km`, o número corrigido)."""
    return round(sum(_num(r.get("planned_km")) for r in prescribed(_in_week(rows, day))), 1)


def done_km_week(rows: list[Workout], day: date) -> float:
    """Km realizados na semana de `day`, segundo o que o SisRUN associou."""
    return round(sum(_num(r.get("done_distance_km")) for r in _in_week(rows, day)), 1)


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
