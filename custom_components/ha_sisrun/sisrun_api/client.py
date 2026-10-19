"""HTTP client for SisRUN (appsisrun.com.br): login, week fetch, week navigation.

SisRUN is JSF + PrimeFaces 8.0, so every request carries a javax.faces.ViewState
token and the widget IDs (j_idt381 etc.) are server-generated: they change
whenever the vendor redeploys. Nothing here hardcodes them. The submit button and
the week-navigation buttons are located at runtime by their stable, human-authored
attributes (title="Muda para semana anterior", the frmLogin form id), and the
ViewState is re-read from every response. The current week needs no AJAX at all;
it is fully rendered on a plain GET of the planilha page.

The load-bearing subtlety: the day detail panels (Estruturado, Feedback do Aluno,
splits) are PrimeFaces accordions, and the server only renders their contents when
the request carries their expanded state (`...tableSegunda:0:j_idtNNN_active=...`)
AND `javax.faces.partial.execute=@all`. Post without them and you get summary rows
with no prescriptions at all, silently. Worse, that state must be accumulated
across hops: the show-detail checkbox lives outside the re-rendered panel, so
harvesting fresh from each AJAX response drops it. Session.absorb_state() exists
for exactly this.
"""

from __future__ import annotations

import datetime
import html as html_mod
import http.cookiejar
import os
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://appsisrun.com.br"
LOGIN_URL = BASE + "/sisrun/login.xhtml"
PLAN_URL = BASE + "/sisrun/pages/planilha/formPlanilhaAluno.xhtml"

CRED_FILE = os.path.expanduser("~/.sisrun/credentials")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# Be a polite client on someone else's server: one week per request, spaced out.
REQUEST_DELAY_S = 0.6

WEEK_RE = re.compile(r"(\d{2}/\d{2}/\d{4}) até (\d{2}/\d{2}/\d{4})")

DATA_URI_RE = re.compile(r"data:[a-zA-Z0-9.+/-]+;base64,[A-Za-z0-9+/=]+")


class SisrunError(RuntimeError):
    """Anything that stops us talking to SisRUN: network, auth, layout change."""


def load_credentials() -> tuple[str, str]:
    """SISRUN_EMAIL / SISRUN_PASSWORD env vars, or ~/.sisrun/credentials."""
    email = os.environ.get("SISRUN_EMAIL")
    password = os.environ.get("SISRUN_PASSWORD")
    if email and password:
        return email, password

    if not os.path.exists(CRED_FILE):
        raise SisrunError(
            f"No SisRUN credentials found. Create {CRED_FILE} with:\n"
            f"    email=you@example.com\n"
            f"    password=yourpassword\n"
            f"then: chmod 600 {CRED_FILE}\n"
            f"(or set SISRUN_EMAIL / SISRUN_PASSWORD in the environment)"
        )

    mode = stat.S_IMODE(os.stat(CRED_FILE).st_mode)
    if mode & 0o077:
        # Warn on stderr-ish channels is the caller's job; keep the library quiet.
        pass

    creds = {}
    with open(CRED_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip().lower()] = v.strip()

    email = creds.get("email")
    password = creds.get("password") or creds.get("senha")
    if not email or not password:
        raise SisrunError(f"{CRED_FILE} must define both `email=` and `password=`.")
    return email, password


class Session:
    """Cookie-carrying JSF session that tracks the current ViewState."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.view_state = None
        # Accumulated frmPrincipal input state. A real browser keeps the whole form
        # in the DOM and resends it; an AJAX response only re-renders part of the
        # page, so harvesting fresh from each response silently drops the inputs
        # that live outside the updated panel (notably the show-detail checkbox).
        self.form_state = {}

    def absorb_state(self, body, form="frmPrincipal"):
        """Merge this response's inputs into the running form state."""
        found = harvest_state(body, form)
        if not found:
            return
        # Accordion state is re-rendered per week, so replace it wholesale rather
        # than letting last week's day-tables linger. Everything else persists.
        if any(k.endswith("_active") for k in found):
            for k in [k for k in self.form_state if k.endswith("_active")]:
                del self.form_state[k]
        self.form_state.update(found)

    def _open(self, req):
        try:
            with self.opener.open(req, timeout=45) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise SisrunError(f"SisRUN HTTP {e.code} for {req.full_url}: {e.reason}")
        except urllib.error.URLError as e:
            raise SisrunError(f"Could not reach SisRUN ({e.reason}). Network down?")

    def get(self, url):
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        body = self._open(req)
        self._remember_view_state(body)
        return body

    def post(self, url, fields):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Referer", url)
        req.add_header("Faces-Request", "partial/ajax")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        body = self._open(req)
        self._remember_view_state(body)
        return body

    def _remember_view_state(self, body):
        vs = extract_view_state(body)
        if vs:
            self.view_state = vs


def extract_view_state(body):
    """ViewState appears as a hidden input on full pages, in CDATA on AJAX responses."""
    m = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', body)
    if m:
        return html_mod.unescape(m.group(1))
    m = re.search(
        r'<update id="[^"]*ViewState[^"]*"><!\[CDATA\[(.*?)\]\]></update>', body, re.S
    )
    return html_mod.unescape(m.group(1).strip()) if m else None


def find_button(body, form, title=None, fallback_any=False):
    """Locate a PrimeFaces button id by its stable title, not its generated id.

    Returns (button_id, render_targets). Attribute order varies between PrimeFaces
    renderings, so try both orders before giving up.
    """
    if title:
        patterns = [
            r'<button[^>]*id="(%s:[^"]+)"[^>]*title="%s"' % (form, re.escape(title)),
            r'<button[^>]*title="%s"[^>]*id="(%s:[^"]+)"' % (re.escape(title), form),
        ]
    elif fallback_any:
        patterns = [r'<button[^>]*id="(%s:[^"]+)"' % form]
    else:
        return None, None

    for pat in patterns:
        m = re.search(pat, body)
        if m:
            bid = m.group(1)
            # Pull the AJAX render targets out of this button's own onclick.
            tag = re.search(
                r'<button[^>]*id="%s".*?</button>' % re.escape(bid), body, re.S
            )
            render = None
            if tag:
                oc = re.search(r'onclick="([^"]*)"', tag.group(0))
                if oc:
                    u = re.search(r'u:"([^"]*)"', html_mod.unescape(oc.group(1)))
                    if u:
                        render = u.group(1)
            return bid, render
    return None, None


INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)


def harvest_state(body, form):
    """Collect every form input the browser would resend for `form`.

    This is not optional politeness; it is load-bearing. The day detail panels
    (Estruturado, Feedback do Aluno, splits) are PrimeFaces accordions, and the
    server only renders their contents when the request carries their expanded
    state (`...tableSegunda:0:j_idtNNN_active=0,1,2,3,4,5`). Post without it and
    you get back the summary rows only, silently. Harvesting from the previous
    response also means the generated j_idt ids never have to be hardcoded, and
    weeks with different day-tables just work.
    """
    state = {}
    for m in INPUT_RE.finditer(body):
        tag = m.group(0)
        name = re.search(r'name="(%s:[^"]+)"' % re.escape(form), tag)
        if not name:
            continue
        name = name.group(1)
        typ = re.search(r'type="([^"]*)"', tag)
        typ = typ.group(1).lower() if typ else "text"
        val = re.search(r'value="([^"]*)"', tag)
        val = html_mod.unescape(val.group(1)) if val else ""
        if typ in ("checkbox", "radio"):
            if "checked" in tag.lower():
                state[name] = val or "on"
        else:
            state[name] = val
    return state


def login(session, email, password):
    page = session.get(LOGIN_URL)
    if session.view_state is None:
        raise SisrunError("SisRUN login page had no ViewState; the site layout may have changed.")

    btn, _ = find_button(page, "frmLogin", fallback_any=True)
    if not btn:
        raise SisrunError("Could not find the SisRUN login button; the site layout may have changed.")

    resp = session.post(LOGIN_URL, {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": btn,
        "javax.faces.partial.execute": "frmLogin",
        "javax.faces.partial.render": "frmLogin",
        btn: btn,
        "frmLogin": "frmLogin",
        "frmLogin:email": email,
        "frmLogin:senha": password,
        "javax.faces.ViewState": session.view_state,
    })

    if '"logado":true' not in html_mod.unescape(resp):
        if "senha" in resp.lower() or "inválid" in resp.lower():
            raise SisrunError("SisRUN rejected the credentials. Check them.")
        raise SisrunError("SisRUN login did not succeed (no `logado:true` in the response).")


# ---------- week fetching ----------

def week_label(body):
    m = WEEK_RE.search(body)
    return m.group(0) if m else None


def week_start_iso(body):
    """Monday of the displayed week, as YYYY-MM-DD."""
    m = WEEK_RE.search(body)
    if not m:
        return None
    d = datetime.datetime.strptime(m.group(1), "%d/%m/%Y").date()
    return d.isoformat()


def navigate(session, body, direction):
    """Step one week backwards/forwards. Returns the new (partial) HTML."""
    title = ("Muda para semana anterior" if direction < 0
             else "Muda para próxima semana")
    bid, render = find_button(body, "frmPrincipal", title=title)
    if not bid:
        return None
    fields = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": bid,
        # @all, not the form id, matching what the real client sends. With a
        # narrower execute the server skips the accordion state and returns
        # summary rows without any workout detail.
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": render or "frmPrincipal:painelSemana frmPrincipal:divSemana",
        bid: bid,
        "frmPrincipal": "frmPrincipal",
    }
    session.absorb_state(body)
    fields.update(session.form_state)
    fields["javax.faces.ViewState"] = session.view_state
    resp = session.post(PLAN_URL, fields)
    time.sleep(REQUEST_DELAY_S)
    return resp


def strip_inline_images(body):
    """Drop base64 data: URIs (~70% of every page, never parsed)."""
    return DATA_URI_RE.sub("data:[stripped]", body)


class SisrunClient:
    """One logged-in session; fetches weeks on demand.

    Week HTML is cached per week-start for the lifetime of the client, so an MCP
    server answering several tool calls does not re-walk the site each time.
    """

    def __init__(self, email=None, password=None):
        if email is None or password is None:
            email, password = load_credentials()
        self._email, self._password = email, password
        self._session = None
        self._cache = {}  # week_start_iso -> html

    def _ensure_login(self):
        if self._session is None:
            s = Session()
            login(s, self._email, self._password)
            self._session = s

    def _reset(self):
        self._session = None

    def current_week_html(self):
        self._ensure_login()
        body = self._session.get(PLAN_URL)
        if not week_label(body):
            # Most likely an expired server session. Log in again, once.
            self._reset()
            self._ensure_login()
            body = self._session.get(PLAN_URL)
            if not week_label(body):
                raise SisrunError("Fetched the planilha but found no week header. Layout changed?")
        self._cache[week_start_iso(body)] = body
        return body

    def fetch_weeks(self, back=0, ahead=0):
        """Fetch current week ± N, newest login-fresh. Returns {week_start: html}."""
        out = {}
        current = self.current_week_html()
        out[week_start_iso(current)] = current

        body = current
        for _ in range(back):
            body = navigate(self._session, body, -1)
            if not body or not week_label(body):
                break
            out[week_start_iso(body)] = body
            self._cache[week_start_iso(body)] = body

        if ahead > 0:
            body = self._session.get(PLAN_URL)
            for _ in range(ahead):
                body = navigate(self._session, body, +1)
                if not body or not week_label(body):
                    break
                out[week_start_iso(body)] = body
                self._cache[week_start_iso(body)] = body
        return out

    def week_html(self, week_start):
        """HTML for the week containing/starting `week_start` (datetime.date)."""
        monday = week_start - datetime.timedelta(days=week_start.weekday())
        iso = monday.isoformat()
        if iso in self._cache:
            return self._cache[iso]
        current = self.current_week_html()
        cur_monday = datetime.date.fromisoformat(week_start_iso(current))
        delta_weeks = (monday - cur_monday).days // 7
        if delta_weeks == 0:
            return current
        body = current
        for _ in range(abs(delta_weeks)):
            body = navigate(self._session, body, 1 if delta_weeks > 0 else -1)
            if not body or not week_label(body):
                raise SisrunError(f"Week of {iso} is not reachable on SisRUN.")
            self._cache[week_start_iso(body)] = body
        if week_start_iso(body) != iso:
            raise SisrunError(
                f"Navigation landed on {week_start_iso(body)}, expected {iso}.")
        return body
