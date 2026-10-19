"""Parse a SisRUN planilha week (raw HTML or JSF partial-response) into workout dicts.

Stdlib-only. The page is parsed with a minimal DOM builder (just enough to find
nodes by their stable, human-authored CSS classes and read their visible text),
because every generated id on the page (j_idtNNN) changes when SisRUN redeploys.

Each workout row carries:
  date, weekday, status, modality, workout_type, route,
  distance_km        : the coach's own `Distância` field (blank on interval days!)
  planned_km         : the honest prescribed distance (see below)
  planned_km_is_est  : "yes" when a timed step was converted at an assumed pace
  intensity, hr_min, hr_max, time_min, time_max,
  structure          : the coach's structured session, flattened with ` | `
  coach_note,
  done_date, done_distance_km, done_time, done_hr, done_kcal  : SisRUN's own
                       auto-association of a Garmin/Strava activity to the row
  week_start

Statuses: Proposto (prescribed, not yet done) / Feito / Não Feito / Feito Avulso
(NOT prescribed: an activity SisRUN auto-imported and could not match).

Why planned_km exists: SisRUN's `Distância` field is EMPTY for every interval,
hill and time-based session (exactly the biggest sessions in the plan), and on
interval days it counts the reps only. Summing that column undercounts the real
prescription by ~35% (SisRUN's own "Evolução Semanal" panel has the same bug).
planned_km derives the honest number from the structured session, expanding
`Repetir Nx` blocks, and takes the LARGER of the field and the structure sum.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from html.parser import HTMLParser

WEEKDAYS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
# Longest-first so "Feito Avulso" is not shadowed by "Feito".
PLAN_STATUSES = ["Feito Avulso", "Não Feito", "Justificado", "Programado",
                 "Proposto", "Feito"]
STATUS_RE = re.compile(r"^(%s)\t" % "|".join(re.escape(s) for s in PLAN_STATUSES), re.M)
WEEK_HEADER_RE = re.compile(r"(\d{2}/\d{2}/\d{4}) até (\d{2}/\d{2}/\d{4})")

_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
              "meta", "param", "source", "track", "wbr"}
_BLOCK_TAGS = {"div", "p", "table", "tr", "li", "ul", "ol", "br", "label", "h1",
               "h2", "h3", "h4", "h5", "h6", "fieldset", "legend", "section"}
_SKIP_TAGS = {"script", "style"}


class _Node:
    __slots__ = ("tag", "cls", "children", "parent", "text")

    def __init__(self, tag="", cls="", parent=None):
        self.tag, self.cls, self.parent = tag, cls, parent
        self.children, self.text = [], None


class _TreeBuilder(HTMLParser):
    """Minimal DOM builder: enough to find a node by class and read its text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        node = _Node(tag, dict(attrs).get("class", "") or "", self.cur)
        self.cur.children.append(node)
        if tag not in _VOID_TAGS:
            self.cur = node

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip or tag in _VOID_TAGS:
            return
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent or self.root

    def handle_data(self, data):
        if self._skip or not data.strip():
            return
        node = _Node("#text", "", self.cur)
        node.text = data
        self.cur.children.append(node)


def _inner_text(node, buf=None):
    """innerText-ish: newlines around block elements, tabs after table cells."""
    if buf is None:
        buf = []
    if node.tag == "#text":
        buf.append(node.text)
        return buf
    if node.tag in _BLOCK_TAGS:
        buf.append("\n")
    for child in node.children:
        _inner_text(child, buf)
    if node.tag in ("td", "th"):
        buf.append("\t")
    if node.tag in _BLOCK_TAGS:
        buf.append("\n")
    return buf


def _clean_text(s):
    s = re.sub(r"[ \xa0]+", " ", s)
    out, blanks = [], 0
    for line in (ln.strip() for ln in s.split("\n")):
        if not line:
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        out.append(line)
    return "\n".join(out).strip()


def _unwrap_jsf(raw):
    """Input is either a full page or a JSF partial-response carrying CDATA."""
    if "<partial-response" in raw[:400]:
        return "\n".join(re.findall(r"<!\[CDATA\[(.*?)\]\]>", raw, re.S))
    return raw


def _find_by_class(node, cls, acc=None):
    if acc is None:
        acc = []
    if cls in (node.cls or ""):
        acc.append(node)
    for child in node.children:
        _find_by_class(child, cls, acc)
    return acc


def _ancestor_with_class(node, cls):
    node = node.parent
    while node is not None:
        if cls in (node.cls or ""):
            return node
        node = node.parent
    return None


def _plan_day_blocks(raw):
    """One (weekday, daynum, text) per day. `.planilhaDiaSemana` is a stable,
    human-authored class; the responsive layout renders each day 3x, so dedupe."""
    tree = _TreeBuilder()
    tree.feed(_unwrap_jsf(raw))
    seen, blocks = set(), []
    for label in _find_by_class(tree.root, "planilhaDiaSemana"):
        row = _ancestor_with_class(label, "ui-grid-row") or label.parent
        if row is None:
            continue
        text = _clean_text("".join(_inner_text(row)))
        m = re.search(r"(%s)[^\n]*\n+\s*(\d{1,2})\b" % "|".join(WEEKDAYS_PT), text)
        if not m:
            continue
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        blocks.append((m.group(1), int(m.group(2)), text))
    return blocks


def _plan_num(s):
    """SisRUN uses pt-BR numbers: 7,802 Km means 7.802 km."""
    if not s:
        return ""
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return ""


# Distance derivation from the coach's structured session.
_STEP_KM_RE = re.compile(r"por\s+([\d.,]+)\s*km\b", re.I)
_STEP_M_RE = re.compile(r"por\s+([\d.,]+)\s*m(?![a-z])", re.I)
# "completar entre 115m e 134m": the plan's own distance estimate for a timed step.
_STEP_COMPLETAR_M_RE = re.compile(r"completar entre\s+([\d.,]+)\s*m\s+e\s+([\d.,]+)\s*m\b", re.I)
_STEP_MIN_RE = re.compile(r"por\s+([\d.,]+)\s*min\b", re.I)
_STEP_HOUR_RE = re.compile(r"por\s+([\d.,]+)\s*h\b", re.I)
_STEP_BAND_RE = re.compile(r"\((\d{1,2}):(\d{2})\s*a\s*(\d{1,2}):(\d{2})\s*min/km\)")
_REPEAT_RE = re.compile(r"(?:^|\.\s*)Repetir\s+(\d+)\s*x", re.I)
# Fallback pace when a timed step states no intensity band: the midpoint of a
# typical "Moderada" band (05:47–07:27 min/km).
_DEFAULT_PACE_MIN_KM = 6.62


def _step_distance_km(step):
    """(km, is_estimate) for one structured step."""
    if re.search(r"\bDescansar\b", step, re.I):
        return 0.0, False
    m = _STEP_KM_RE.search(step)
    if m:
        return _plan_num(m.group(1)) or 0.0, False
    m = _STEP_M_RE.search(step)
    if m:
        return (_plan_num(m.group(1)) or 0.0) / 1000.0, False
    # Timed step, but the plan tells us the distance window it should cover.
    m = _STEP_COMPLETAR_M_RE.search(step)
    if m:
        lo, hi = _plan_num(m.group(1)) or 0.0, _plan_num(m.group(2)) or 0.0
        return (lo + hi) / 2000.0, False
    minutes = None
    m = _STEP_MIN_RE.search(step)
    if m:
        minutes = _plan_num(m.group(1))
    else:
        m = _STEP_HOUR_RE.search(step)
        if m:
            minutes = (_plan_num(m.group(1)) or 0.0) * 60
    if minutes:
        band = _STEP_BAND_RE.search(step)
        if band:
            lo = int(band.group(1)) + int(band.group(2)) / 60.0
            hi = int(band.group(3)) + int(band.group(4)) / 60.0
            pace = (lo + hi) / 2
        else:
            pace = _DEFAULT_PACE_MIN_KM
        return minutes / pace, True
    return 0.0, False


def structure_distance_km(structure):
    """Total prescribed distance for a structured session.

    Returns (km, is_estimate). Handles `Repetir Nx` blocks, whose repeated steps
    are the following ` | `-separated entries that start with a dash.
    """
    if not structure:
        return 0.0, False
    steps = [s.strip() for s in structure.split(" | ") if s.strip()]
    total, estimated, i = 0.0, False, 0
    while i < len(steps):
        rep = _REPEAT_RE.search(steps[i])
        if rep:
            times = int(rep.group(1))
            block, j = [], i + 1
            while j < len(steps) and steps[j].lstrip().startswith("-"):
                block.append(steps[j])
                j += 1
            for step in block:
                km, est = _step_distance_km(step)
                total += times * km
                estimated |= est
            i = j
            continue
        km, est = _step_distance_km(steps[i])
        total += km
        estimated |= est
        i += 1
    return round(total, 3), estimated


def _plan_field(text, label):
    m = re.search(re.escape(label) + r"\s*:?\s*([^\n]*)", text)
    return m.group(1).strip() if m else ""


def _parse_plan_workouts(day_text):
    """A day can hold several workouts; each starts with a status cell."""
    hits = list(STATUS_RE.finditer(day_text))
    rows = []
    for i, hit in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(day_text)
        chunk = day_text[hit.start():end]
        cells = chunk.split("\n", 1)[0].split("\t")

        def cell(n):
            return cells[n].strip() if len(cells) > n else ""

        dm = re.match(r"([\d.,]+)\s*Km", cell(4), re.I)

        structure = ""
        ms = re.search(
            r"Estruturado:\s*\n(.*?)(?=\n(?:Tempo Mínimo|Intensidade|FC Mínima|"
            r"Feedback do Aluno|Feedback do Treinador|Mensagens|Descrição)\b|\Z)",
            chunk, re.S)
        if ms:
            structure = " | ".join(
                ln.strip() for ln in ms.group(1).split("\n") if ln.strip())

        coach_note = ""
        md = re.search(r"Descrição:\s*\n([^\n]*)", chunk)
        if md and "adicionado automaticamente" not in md.group(1):
            coach_note = md.group(1).strip()

        # What SisRUN itself matched to this prescription: the coach-side view
        # of "was it fulfilled" (SisRUN auto-imports Garmin/Strava activities).
        done = {}
        parts = chunk.split("Feedback do Aluno", 1)
        if len(parts) > 1:
            seg = parts[1]
            m = re.search(r"Data Realização:\s*(\d{2}/\d{2}/\d{4})", seg)
            if m:
                done["date"] = datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
            m = re.search(r"Distância:\s*([\d.,]+)\s*Km", seg)
            if m:
                done["km"] = _plan_num(m.group(1))
            m = re.search(r"Tempo:\s*(\d{2}:\d{2}:\d{2})", seg)
            if m:
                done["time"] = m.group(1)
            m = re.search(r"FC Média:\s*(\d+)", seg)
            if m:
                done["hr"] = m.group(1)
            m = re.search(r"Calorias:\s*(\d+)", seg)
            if m:
                done["kcal"] = m.group(1)

        # The Distância column is blank for interval/hill/timed sessions, so fall
        # back to summing the structured session. planned_km is the honest number.
        # When BOTH exist, take the larger: on interval days the coach's field
        # counts the reps only, which would make a to-spec session read as long.
        field_km = _plan_num(dm.group(1)) if dm else ""
        struct_km, struct_est = structure_distance_km(structure)
        if field_km and struct_km and struct_km > field_km:
            planned_km, planned_est = struct_km, struct_est
        elif field_km:
            planned_km, planned_est = field_km, False
        else:
            planned_km, planned_est = (struct_km or ""), struct_est

        rows.append({
            "status": hit.group(1),
            "modality": cell(1),
            "workout_type": cell(2),
            "route": cell(3),
            "distance_km": _plan_num(dm.group(1)) if dm else "",
            "planned_km": planned_km,
            "planned_km_is_est": "yes" if planned_est else "",
            "intensity": _plan_field(chunk, "Intensidade"),
            "hr_min": _plan_field(chunk, "FC Mínima").replace(" bpm", ""),
            "hr_max": _plan_field(chunk, "FC Máxima").replace(" bpm", ""),
            "time_min": _plan_field(chunk, "Tempo Mínimo"),
            "time_max": _plan_field(chunk, "Tempo Máximo"),
            "structure": structure,
            "coach_note": coach_note,
            "done_date": done.get("date", ""),
            "done_distance_km": done.get("km", ""),
            "done_time": done.get("time", ""),
            "done_hr": done.get("hr", ""),
            "done_kcal": done.get("kcal", ""),
        })
    return rows


def parse_week_html(raw):
    """All workout rows for one week of planilha HTML, sorted by (date, seq).

    Raises ValueError when no week header is present. A week the coach has not
    published yet parses to an empty list; that is data, not an error.
    """
    body = _unwrap_jsf(raw)
    header = WEEK_HEADER_RE.search(body)
    if not header:
        raise ValueError("no week header ('dd/mm/yyyy até dd/mm/yyyy') in the HTML")
    start = datetime.strptime(header.group(1), "%d/%m/%Y").date()

    rows = []
    for weekday, daynum, text in _plan_day_blocks(raw):
        day = start + timedelta(days=WEEKDAYS_PT.index(weekday))
        if day.day != daynum:
            # Week header and day cells disagree; skip rather than mis-date.
            continue
        for seq, row in enumerate(_parse_plan_workouts(text)):
            row["date"] = day.isoformat()
            row["weekday"] = weekday
            row["week_start"] = start.isoformat()
            row["_seq"] = seq
            rows.append(row)
    rows.sort(key=lambda r: (r["date"], r.pop("_seq")))
    return rows


def detail_panels_missing(raw):
    """True when workouts are present but no detail panels rendered, i.e. the
    accordion-state-not-sent regression. Callers should surface this loudly."""
    body = _unwrap_jsf(raw)
    workouts = body.count("Feedback deste treino")
    details = body.count("Estruturado") + body.count("Feedback do Aluno")
    return bool(workouts and not details)
