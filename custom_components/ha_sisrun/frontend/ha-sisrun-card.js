/* SisRUN card para o Home Assistant (não oficial). Sem dependências externas. */
const CARD_VERSION = "0.3.0";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const TABS = ["plan", "vo2", "races"];

const T = {
  "pt-BR": {
    plan: "Planilha", vo2: "Vo2 Max", races: "Provas",
    days: ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
    today: "Hoje", rest: "Sem treino", planned: "Planejado", done: "Realizado", adherence: "Aderência",
    intensity: "Intensidade", hr: "FC", coach: "Treinador", structure: "Estrutura", doneInfo: "Feito",
    status: { Proposto: "Proposto", Feito: "Feito", "Não Feito": "Não feito", Justificado: "Justificado", Programado: "Programado" },
    noPlan: "Planilha sem dados ainda.", noWorkouts: "Sem treinos nesta semana.", noWeekData: "Sem dados guardados desta semana. Para semanas passadas, use a ação ha_sisrun.load_history.", week: "Semana", prev: "Semana anterior", next: "Próxima semana", first: "Primeira semana registrada", last: "Última semana registrada", loading: "Carregando…", noTests: "Nenhum teste de desempenho lido ainda.",
    latest: "Último teste", history: "Histórico", date: "Data", protocol: "Protocolo", distance: "Distância",
    time: "Tempo", pace: "Pace", speed: "Velocidade", change: "vs. teste anterior", vsPrev: "vs. anterior", tests: "testes",
    all: "Todos", races1: "prova", racesN: "provas", noRaces: "Nenhuma prova lida ainda.", noRacesYear: "Sem provas neste ano.", racesError: "Não consegui carregar as provas.", main: "Principal", archived: "Arquivada", reg: "Inscrição", timePh: "Tempo de prova (h:mm:ss)", timeTip: "Tempo de prova (só no Home Assistant)", rename: "Renomear (só no Home Assistant)", renameSave: "Salvar", renameCancel: "Cancelar", renameHint: "Nome original no SisRUN: ", regOn: "Inscrito: toque para desmarcar", regOff: "Não inscrito: toque para marcar como inscrito", inRel: "em {t}", agoRel: "há {t}", todayRace: "hoje", units: { y: ["ano", "anos"], m: ["mês", "meses"], d: ["dia", "dias"] }, and: "e",
    missing: "Não encontrei as entidades do SisRUN. Informe-as em `entities:` na configuração do card.",
    unit: "mL/(kg·min)",
  },
  en: {
    plan: "Plan", vo2: "Vo2 Max", races: "Races",
    days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    today: "Today", rest: "Rest", planned: "Planned", done: "Done", adherence: "Adherence",
    intensity: "Intensity", hr: "HR", coach: "Coach", structure: "Structure", doneInfo: "Done",
    status: { Proposto: "Planned", Feito: "Done", "Não Feito": "Missed", Justificado: "Excused", Programado: "Scheduled" },
    noPlan: "No plan data yet.", noWorkouts: "No workouts this week.", noWeekData: "No stored data for this week. For past weeks, use the ha_sisrun.load_history action.", week: "Week", prev: "Previous week", next: "Next week", first: "First recorded week", last: "Last recorded week", loading: "Loading…", noTests: "No performance tests read yet.",
    latest: "Latest test", history: "History", date: "Date", protocol: "Protocol", distance: "Distance",
    time: "Time", pace: "Pace", speed: "Speed", change: "vs. previous test", vsPrev: "vs. previous", tests: "tests",
    all: "All", races1: "race", racesN: "races", noRaces: "No races read yet.", noRacesYear: "No races this year.", racesError: "Could not load the races.", main: "Main", archived: "Archived", reg: "Registration", timePh: "Finish time (h:mm:ss)", timeTip: "Finish time (Home Assistant only)", rename: "Rename (Home Assistant only)", renameSave: "Save", renameCancel: "Cancel", renameHint: "Original name in SisRUN: ", regOn: "Registered: tap to unmark", regOff: "Not registered: tap to mark as registered", inRel: "in {t}", agoRel: "{t} ago", todayRace: "today", units: { y: ["year", "years"], m: ["month", "months"], d: ["day", "days"] }, and: "and",
    missing: "Could not find the SisRUN entities. Set them under `entities:` in the card config.",
    unit: "mL/(kg·min)",
  },
};

const STATUS_COLOR = {
  Feito: "var(--success-color, #43a047)",
  "Não Feito": "var(--error-color, #db4437)",
  Justificado: "var(--warning-color, #ffa726)",
  Proposto: "var(--primary-color, #03a9f4)",
  Programado: "var(--primary-color, #03a9f4)",
};

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtNum = (v, d = 1) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? "–" : Number(v).toFixed(d).replace(".", ","));
let LOCALE;
const fmtDate = (iso, opts) => {
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(LOCALE, opts || { day: "2-digit", month: "2-digit", year: "numeric" });
};

const STYLE = `
:host { display: block; }
ha-card { overflow: hidden; }
.head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 0; }
.title { font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
.tabs { display: flex; gap: 0; padding: 8px 0 0; border-bottom: 1px solid var(--divider-color); }
.tab { flex: 1 1 0; text-align: center; appearance: none; background: none; border: 0; border-bottom: 3px solid transparent; padding: 10px 14px; cursor: pointer;
  font: inherit; font-weight: 500; color: var(--secondary-text-color); border-radius: 6px 6px 0 0; }
.tab:hover { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
.tab[aria-selected="true"] { color: var(--primary-color); border-bottom-color: var(--primary-color); }
.tab:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
.body { padding: 16px; }
.muted { color: var(--secondary-text-color); }
.empty { padding: 24px 8px; text-align: center; color: var(--secondary-text-color); }
.kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; text-align: center; }
.kpi .v { font-size: 1.5em; font-weight: 500; color: var(--primary-text-color); line-height: 1.2; }
.kpi .l { font-size: .8em; color: var(--secondary-text-color); }
.bar { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; margin: 2px 0 14px; }
.bar > i { display: block; height: 100%; background: var(--primary-color); border-radius: 3px; }
.nav { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; }
.nl { flex: 1; text-align: center; display: flex; flex-direction: column; line-height: 1.25; color: var(--primary-text-color); }
.nl .muted { font-size: .85em; }
.nb { appearance: none; background: none; border: 1px solid var(--divider-color); border-radius: 8px; min-width: 38px; height: 36px; cursor: pointer;
  font: inherit; font-size: 1.3em; line-height: 1; color: var(--primary-text-color); }
.nb:disabled { opacity: .35; cursor: default; }
.nb:hover:not(:disabled) { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
.nb:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.nb.nt { font-size: .85em; padding: 0 12px; color: var(--primary-color); border-color: var(--primary-color); }
.days { display: grid; gap: 8px; }
.day { border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px; background: var(--card-background-color); }
.day.today { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color) inset; }
.day.rest { opacity: .7; }
.dh { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dn { font-weight: 500; color: var(--primary-text-color); }
.dd { font-size: .85em; color: var(--secondary-text-color); }
.chip { font-size: .72em; font-weight: 500; padding: 2px 8px; border-radius: 10px; color: var(--text-primary-color, #fff); margin-left: auto; white-space: nowrap; }
.chip.now { background: var(--primary-color); margin-left: 0; }
.w { margin-top: 6px; }
.wt { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.ws { color: var(--primary-text-color); }
.wk { font-weight: 500; color: var(--primary-text-color); white-space: nowrap; }
.wm { font-size: .85em; color: var(--secondary-text-color); margin-top: 2px; }
details { margin-top: 4px; }
summary { cursor: pointer; font-size: .85em; color: var(--primary-color); }
.det { font-size: .85em; color: var(--secondary-text-color); margin-top: 4px; white-space: pre-line; }
.hero { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.hero .big { font-size: 2.4em; font-weight: 500; line-height: 1; color: var(--primary-text-color); }
.hero .u { color: var(--secondary-text-color); }
.delta { font-size: .85em; font-weight: 500; }
.sub { font-size: .85em; color: var(--secondary-text-color); margin: 4px 0 12px; }
.chart { position: relative; width: 100%; margin: 40px 0 8px; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart text { fill: var(--secondary-text-color); font-size: 11px; }
.grid { stroke: var(--divider-color); stroke-width: 1; }
.line { fill: none; stroke: var(--primary-color); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.pt { fill: var(--primary-color); stroke: var(--card-background-color); stroke-width: 2; }
.pt.act { r: 6; }
.cross { stroke: var(--secondary-text-color); stroke-width: 1; stroke-dasharray: 3 3; }
.tip { position: absolute; pointer-events: none; transform: translate(-50%, -100%); margin-top: -10px; z-index: 2;
  background: var(--card-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);
  border-radius: 8px; padding: 6px 10px; font-size: .8em; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,.25); }
.tip b { font-weight: 500; }
table { width: 100%; border-collapse: collapse; font-size: .85em; }
th, td { text-align: left; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--divider-color); white-space: nowrap; }
th { color: var(--secondary-text-color); font-weight: 500; }
td.n, th.n { text-align: right; padding-right: 0; padding-left: 8px; }
tr.sel td { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
table.vt { table-layout: fixed; }
.cmp.up { color: var(--success-color, #43a047); font-weight: 500; }
.cmp.down { color: var(--error-color, #db4437); font-weight: 500; }
table.vt th, table.vt td { width: 16.66%; text-align: center; padding: 6px 4px; }
.tscroll { overflow-x: auto; }
.years { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.yr { appearance: none; background: none; border: 1px solid var(--divider-color); border-radius: 16px; padding: 4px 14px; cursor: pointer;
  font: inherit; font-size: .9em; color: var(--primary-text-color); }
.yr:hover { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
.yr[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
.yr:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.rsum { font-size: .85em; color: var(--secondary-text-color); margin: 0 0 12px; }
.ryear { font-weight: 500; color: var(--primary-text-color); margin: 14px 0 6px; }
.race { display: flex; gap: 12px; align-items: center; border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 12px; margin-bottom: 8px; background: var(--card-background-color); }
.race.p-gold { border: 1px solid #d4af37; }
.race.p-silver { border: 1px solid #b0b4ba; }
.race.p-bronze { border: 1px solid #cd7f32; }
.race.past { opacity: .72; }
.race.next { opacity: 1; }
.rleft { flex: 0 0 60px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.cal { box-sizing: border-box; width: 60px; height: 62px; display: flex; flex-direction: column; justify-content: space-between; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; text-align: center; background: var(--card-background-color); }
.cal .cm { background: var(--primary-color); color: var(--text-primary-color, #fff); font-size: .65em; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; padding: 2px 0; }
.cal.c-past .cm { background: var(--disabled-text-color, #9e9e9e); }
.cal.c-future .cm { background: var(--success-color, #43a047); }
.cal.c-today .cm { background: var(--primary-color, #03a9f4); }
.cal.c-future { border-color: var(--success-color, #43a047); }
.cal.c-today { border-color: var(--primary-color, #03a9f4); }
.cal b { display: block; font-size: 1.4em; font-weight: 500; line-height: 1.15; padding-top: 2px; color: var(--primary-text-color); }
.cal .cy { font-size: .7em; text-transform: uppercase; color: var(--secondary-text-color); padding-bottom: 3px; }
.rmain { flex: 1; min-width: 0; align-self: stretch; min-height: 62px; display: flex; flex-direction: column; justify-content: space-between; gap: 4px; }
.rpen { appearance: none; background: none; border: 0; padding: 0 0 0 6px; font-size: .9em; color: var(--secondary-text-color); cursor: pointer; opacity: .6; }
.rpen:hover, .rpen:focus-visible { opacity: 1; color: var(--primary-color); }
.redit { display: flex; gap: 4px; align-items: center; }
.rinput { flex: 1; min-width: 0; font: inherit; color: var(--primary-text-color); background: var(--card-background-color); border: 1px solid var(--primary-color); border-radius: 6px; padding: 3px 6px; }
.rbtn { appearance: none; font: inherit; width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); cursor: pointer; }
.rtime { font: inherit; font-size: .85em; width: 100%; box-sizing: border-box; color: var(--primary-text-color); background: transparent; border: 0; border-bottom: 1px dashed var(--divider-color); border-radius: 0; padding: 1px 0; }
.rtime.zero { color: var(--secondary-text-color); opacity: .6; }
.rtime::placeholder { color: var(--secondary-text-color); opacity: .6; }
.rtime:focus { outline: none; border-bottom: 1px solid var(--primary-color); }
.rtime[readonly] { border-bottom-color: transparent; }
.rname { color: var(--primary-text-color); overflow-wrap: anywhere; }
.rmeta { font-size: .85em; color: var(--secondary-text-color); margin-top: 2px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.reg { appearance: none; font: inherit; box-sizing: border-box; flex: 0 0 auto; width: 80px; height: 44px; display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; text-align: center; padding: 0; overflow: hidden; border-radius: 8px; cursor: pointer; background: var(--card-background-color); color: var(--error-color, #db4437); border: 1px solid var(--error-color, #db4437); }
.reg .rh { background: var(--error-color, #db4437); color: #fff; font-size: .6em; font-weight: 500; text-transform: uppercase; letter-spacing: 0; padding: 2px 0; line-height: 1.4; }
.reg .rv { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 1.2em; font-weight: 700; line-height: 1; }
.reg[aria-pressed="true"] { color: var(--success-color, #43a047); border-color: var(--success-color, #43a047); }
.reg[aria-pressed="true"] .rh { background: var(--success-color, #43a047); }
.reg:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.rside .chip.km-off { background: var(--error-color, #db4437); }
.rside .chip.km-on { background: var(--success-color, #43a047); }
.rside .chip { box-sizing: border-box; width: 100%; text-align: center; border-radius: 8px; }
.rside { flex: 0 0 80px; display: flex; flex-direction: column; gap: 4px; align-items: stretch; }
.rrel { font-size: .8em; color: var(--secondary-text-color); white-space: nowrap; }
.chips { display: flex; flex-direction: column; justify-content: flex-start; align-items: flex-end; gap: 4px; align-self: stretch; min-height: 62px; }
.star { color: var(--warning-color, #ffa726); }
`;

class SisrunCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = null;
    this._sel = null;
    this._offset = 0;
    this._cache = new Map();
    this._racesCache = null;
    this._year = null;
    this._editKey = null;
    this._typing = false;
    this._sig = "";
  }

  static getStubConfig() { return { type: "custom:ha-sisrun-card" }; }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "default_tab", selector: { select: { mode: "dropdown", options: [
          { value: "plan", label: "Planilha" }, { value: "vo2", label: "Vo2 Max" }, { value: "races", label: "Provas" } ] } } },
      ],
      computeLabel: (s) => ({ title: "Título", default_tab: "Aba inicial" }[s.name] || s.name),
    };
  }

  setConfig(config) {
    this._config = { entities: {}, ...config };
    this._tab = TABS.includes(config.default_tab) ? config.default_tab : "plan";
    this._sig = "";
    this._render();
  }

  getCardSize() { return 8; }

  set hass(hass) {
    this._hass = hass;
    LOCALE = hass.locale?.language || hass.language || undefined;
    this._render();
  }

  get _t() {
    const lang = this._hass?.language || "en";
    return lang.toLowerCase().startsWith("pt") ? T["pt-BR"] : T.en;
  }

  /** Acha as entidades: configuração manual primeiro, depois o registro (plataforma + translation_key). */
  _find() {
    const manual = this._config.entities || {};
    const found = {};
    const reg = this._hass.entities || {};
    const byKey = {};
    for (const [id, e] of Object.entries(reg)) {
      if (e.platform === "ha_sisrun" && e.translation_key && !byKey[e.translation_key]) byKey[e.translation_key] = id;
    }
    const want = {
      ...Object.fromEntries(DAYS.map((d) => [d, `weekday_${d}`])),
      performance: "performance_test", planned_km: "week_planned_km", done_km: "week_done_km", adherence: "week_adherence",
    };
    for (const [k, tk] of Object.entries(want)) found[k] = manual[k] || byKey[tk] || null;
    return found;
  }

  _state(id) { return id ? this._hass.states[id] : undefined; }

  _render() {
    if (!this._hass || !this._config) return;
    const ent = this._find();
    const states = Object.values(ent).map((id) => this._state(id));
    const sig = JSON.stringify([this._tab, this._hass.language, states.map((s) => s && [s.state, s.last_updated, s.attributes?.history?.length]), this._sel, this._offset, this._year, this._racesCache?.at || 0, this._cache.size, [...this._cache.values()].map((c) => c.at || 0), new Date().toDateString()]);
    if ((this._editKey || this._typing) && this._sig) return; // não perde o que está sendo digitado
    if (sig === this._sig) return;
    this._sig = sig;
    const t = this._t;
    const title = this._config.title ?? "SisRUN";
    const tabs = TABS.map((k) => `<button class="tab" role="tab" data-tab="${k}" aria-selected="${k === this._tab}">${esc(t[k])}</button>`).join("");
    let body;
    if (!Object.values(ent).some(Boolean)) body = `<div class="empty">${esc(t.missing)}</div>`;
    else if (this._tab === "plan") body = this._plan(ent, t);
    else if (this._tab === "vo2") body = this._vo2(ent, t);
    else body = this._races(t);
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>
      ${title ? `<div class="head"><div class="title">${esc(title)}</div></div>` : ""}
      <div class="tabs" role="tablist">${tabs}</div><div class="body">${body}</div></ha-card>`;
    this.shadowRoot.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { this._tab = b.dataset.tab; this._editKey = null; this._sig = ""; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
      const v = Number(b.dataset.nav);
      this._offset = v === 0 ? 0 : this._offset + v;
      this._render();
    }));
    this.shadowRoot.querySelectorAll("[data-rename]").forEach((b) => b.addEventListener("click", () => { this._editKey = b.dataset.rename; this._sig = ""; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-cancel]").forEach((b) => b.addEventListener("click", () => this._endEdit()));
    this.shadowRoot.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", () => this._saveName(b.dataset.save)));
    this.shadowRoot.querySelectorAll(".rtime").forEach((i) => {
      i.addEventListener("focus", () => { this._typing = true; i.select(); });
      i.addEventListener("keydown", (e) => { if (e.key === "Enter") i.blur(); else if (e.key === "Escape") { i.value = i.dataset.orig || "00:00:00"; i.blur(); } });
      i.addEventListener("blur", () => { this._typing = false; this._saveTime(i.dataset.key, i.value, i.dataset.orig); });
    });
    const inp = this.shadowRoot.querySelector(".rinput");
    if (inp) {
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this._saveName(inp.dataset.key);
        else if (e.key === "Escape") this._endEdit();
      });
      inp.focus(); inp.select();
    }
    this.shadowRoot.querySelectorAll("[data-reg]").forEach((b) => b.addEventListener("click", () => this._toggleReg(b.dataset.reg)));
    this.shadowRoot.querySelectorAll("[data-year]").forEach((b) => b.addEventListener("click", () => { this._year = b.dataset.year; this._editKey = null; this._sig = ""; this._render(); }));
    this.shadowRoot.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => {
      const data = this._weekData(this._offset, this._find());
      const target = data && (b.dataset.goto === "first" ? data.first_week : data.last_week);
      if (!target) return;
      const ms = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d); };
      this._offset = Math.round((ms(target) - ms(this._mondayIso(0))) / 604800000);
      this._render();
    }));
    if (this._tab === "vo2") this._bindChart();
  }

  // ---------- aba Planilha ----------
  _iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }

  _mondayIso(offset) {
    const n = new Date();
    const m = new Date(n.getFullYear(), n.getMonth(), n.getDate() - ((n.getDay() + 6) % 7) + offset * 7);
    return this._iso(m);
  }

  /** Semana ISO e ano ISO (a quinta-feira da semana define o ano). */
  _isoWeek(mondayIso) {
    const [y, m, d] = mondayIso.split("-").map(Number);
    const thu = new Date(Date.UTC(y, m - 1, d + 3));
    const jan1 = Date.UTC(thu.getUTCFullYear(), 0, 1);
    return { week: Math.floor((thu.getTime() - jan1) / 604800000) + 1, year: thu.getUTCFullYear() };
  }

  /** Semana `offset` (0 = atual). Pede ao backend; devolve do cache enquanto vale. */
  _weekData(offset, ent) {
    const key = this._mondayIso(offset);
    const stamp = DAYS.map((d) => this._state(ent[d])?.last_updated || "").join("|");
    const hit = this._cache.get(key);
    if (hit && hit.stamp === stamp && Date.now() - hit.at < 300000) return hit.data;
    if (!hit?.pending) {
      this._cache.set(key, { ...(hit || {}), pending: true });
      this._hass.callWS({ type: "ha_sisrun/week", start: key }).then(
        (data) => { this._cache.set(key, { data, stamp, at: Date.now() }); this._sig = ""; this._render(); },
        () => { this._cache.set(key, { data: hit?.data || null, error: true, stamp, at: Date.now() }); this._sig = ""; this._render(); },
      );
    }
    return hit?.data;
  }

  /** Semana atual montada a partir dos sensores (se o backend não responder). */
  _weekFromSensors(ent) {
    const num = (id) => { const s = this._state(id); return s && !isNaN(Number(s.state)) ? Number(s.state) : null; };
    const days = DAYS.map((d) => { const a = this._state(ent[d])?.attributes || {}; return { date: a.date || "", workouts: Array.isArray(a.workouts) ? a.workouts : [] }; });
    const pct = num(ent.adherence);
    return { has_data: days.some((x) => x.date), days, planned_km: num(ent.planned_km), done_km: num(ent.done_km),
      adherence: pct === null ? null : { percent: pct }, week_start: days[0].date, week_end: days[6].date };
  }

  _plan(ent, t) {
    const todayIso = this._iso(new Date());
    const off = this._offset;
    let data = this._weekData(off, ent);
    const cached = this._cache.get(this._mondayIso(off));
    if (!data && off === 0 && cached?.error) data = this._weekFromSensors(ent);
    const loading = !data && !cached?.error;
    const kpi = (v, l) => `<div class="kpi"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`;
    const pct = data?.adherence ? data.adherence.percent : null;
    let h = `<div class="kpis">${kpi(`${fmtNum(data?.planned_km)} km`, t.planned)}${kpi(`${fmtNum(data?.done_km)} km`, t.done)}${kpi(pct === null || pct === undefined ? "–" : `${pct}%`, t.adherence)}</div>`;
    h += `<div class="bar" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, pct ?? 0))}%"></i></div>`;
    const range = data?.week_start
      ? `${fmtDate(data.week_start, { day: "2-digit", month: "2-digit" })} – ${fmtDate(data.week_end, { day: "2-digit", month: "2-digit" })}`
      : "";
    const iw = this._isoWeek(this._mondayIso(off));
    const label = `${t.week} ${iw.week} - ${iw.year}`;
    const curMonday = this._mondayIso(off);
    const canFirst = !!data?.first_week && data.first_week < curMonday;
    const canLast = !!data?.last_week && data.last_week > curMonday;
    h += `<div class="nav"><button class="nb" data-goto="first" aria-label="${esc(t.first)}"${canFirst ? "" : " disabled"}>«</button><button class="nb" data-nav="-1" aria-label="${esc(t.prev)}">‹</button>
      <div class="nl"><b>${esc(label)}</b><span class="muted">${esc(range)}</span></div>
      ${off !== 0 ? `<button class="nb nt" data-nav="0">${esc(t.today)}</button>` : ""}
      <button class="nb" data-nav="1" aria-label="${esc(t.next)}">›</button><button class="nb" data-goto="last" aria-label="${esc(t.last)}"${canLast ? "" : " disabled"}>»</button></div>`;
    if (loading) return h + `<div class="empty">${esc(t.loading)}</div>`;
    if (!data) return h + `<div class="empty">${esc(t.noPlan)}</div>`;
    h += `<div class="days">`;
    let shown = 0;
    data.days.forEach((day, i) => {
      const ws = day.workouts || [];
      if (!ws.length) return; // dia sem treino não aparece
      shown++;
      const iso = day.date;
      const isToday = iso === todayIso;
      const chips = [...new Set(ws.map((w) => w.status))].filter(Boolean)
        .map((s) => `<span class="chip" style="background:${STATUS_COLOR[s] || "var(--secondary-text-color)"}">${esc(t.status[s] || s)}</span>`).join("");
      h += `<div class="day${isToday ? " today" : ""}"><div class="dh"><span class="dn">${esc(t.days[i])}</span>
        <span class="dd">${iso ? esc(fmtDate(iso, { day: "2-digit", month: "2-digit" })) : ""}</span>${isToday ? `<span class="chip now">${esc(t.today)}</span>` : ""}${chips}</div>`;
      for (const w of ws) {
        const km = w.planned_km !== "" && w.planned_km != null ? `${w.planned_km_is_est ? "~" : ""}${fmtNum(w.planned_km)} km` : "";
        const title = [w.modality, w.workout_type].filter(Boolean).join(" · ");
        const meta = [w.intensity && `${t.intensity}: ${w.intensity}`, (w.hr_min || w.hr_max) && `${t.hr} ${w.hr_min || "?"}–${w.hr_max || "?"}`].filter(Boolean).join("  ·  ");
        const done = w.done_distance_km !== "" && w.done_distance_km != null
          ? `${t.doneInfo}: ${fmtNum(w.done_distance_km)} km${w.done_time ? ` · ${w.done_time}` : ""}${w.done_hr ? ` · ${w.done_hr} bpm` : ""}` : "";
        const struct = w.structure ? String(w.structure).split(" | ").join("\n") : "";
        const det = [struct && `${t.structure}:\n${struct}`, w.coach_note && `${t.coach}: ${w.coach_note}`].filter(Boolean).join("\n\n");
        h += `<div class="w"><div class="ws">${esc(title)}${km ? ` - ${esc(km)}` : ""}</div>${meta ? `<div class="wm">${esc(meta)}</div>` : ""}${done ? `<div class="wm">${esc(done)}</div>` : ""}
          ${det ? `<details><summary>${esc(t.structure)}</summary><div class="det">${esc(det)}</div></details>` : ""}</div>`;
      }
      h += `</div>`;
    });
    if (!shown) h += `<div class="empty">${esc(data.has_data === false ? t.noWeekData : t.noWorkouts)}</div>`;
    return h + `</div>`;
  }

  // ---------- aba Provas ----------
  _racesData() {
    const c = this._racesCache;
    if (c && !c.pending && Date.now() - c.at < 300000) return c;
    if (!c?.pending) {
      this._racesCache = { ...(c || {}), pending: true };
      this._hass.callWS({ type: "ha_sisrun/races" }).then(
        (d) => { this._racesCache = { data: d, at: Date.now() }; this._sig = ""; this._render(); },
        () => { this._racesCache = { error: true, at: Date.now() }; this._sig = ""; this._render(); },
      );
    }
    return this._racesCache;
  }

  /** Inscrição é um dado só do Home Assistant: marca na hora e confirma no servidor. */
  _toggleReg(key) {
    const race = this._racesCache?.data?.races?.find((r) => r.key === key);
    if (!race) return;
    const value = !race.registered;
    race.registered = value;
    this._sig = ""; this._render();
    this._hass.callWS({ type: "ha_sisrun/set_registration", key, registered: value }).catch(() => {
      race.registered = !value; // não gravou: desfaz
      this._sig = ""; this._render();
    });
  }

  /** Tempo de prova: dado só do Home Assistant, salvo ao sair do campo. */
  _saveTime(key, raw, orig) {
    let value = String(raw || "").replace(/\s+/g, " ").trim().slice(0, 20);
    if (value === "00:00:00") value = ""; // zerado = sem tempo cadastrado
    if (value === (orig || "")) return;
    const race = this._racesCache?.data?.races?.find((r) => r.key === key);
    if (!race) return;
    const before = race.finish_time;
    if (value) race.finish_time = value; else delete race.finish_time;
    this._sig = ""; this._render();
    this._hass.callWS({ type: "ha_sisrun/set_race_time", key, time: value }).catch(() => {
      if (before) race.finish_time = before; else delete race.finish_time;
      this._sig = ""; this._render();
    });
  }

  _endEdit() { this._editKey = null; this._sig = ""; this._render(); }

  /** Renomear é local: guarda o nome no Home Assistant, o SisRUN não é tocado. */
  _saveName(key) {
    const inp = this.shadowRoot.querySelector(".rinput");
    const race = this._racesCache?.data?.races?.find((r) => r.key === key);
    const name = (inp ? inp.value : "").replace(/\s+/g, " ").trim();
    this._editKey = null;
    if (!race) { this._endEdit(); return; }
    const before = race.local_name;
    if (name && name !== race.name) race.local_name = name; else delete race.local_name;
    this._sig = ""; this._render();
    this._hass.callWS({ type: "ha_sisrun/set_race_name", key, name: race.local_name || "" }).catch(() => {
      if (before) race.local_name = before; else delete race.local_name;
      this._sig = ""; this._render();
    });
  }

  _races(t) {
    const c = this._racesData();
    if (!c || c.pending) return `<div class="empty">${esc(t.loading)}</div>`;
    if (c.error) return `<div class="empty">${esc(t.racesError)}</div>`;
    const all = (c.data?.races || []).filter((r) => r && r.date);
    if (!all.length) return `<div class="empty">${esc(t.noRaces)}</div>`;
    const todayIso = this._iso(new Date());
    const canEdit = !!this._hass?.user?.is_admin;
    const years = [...new Set(all.map((r) => r.date.slice(0, 4)))].sort().reverse();
    if (this._year === null || (this._year !== "all" && !years.includes(this._year))) {
      const cur = String(new Date().getFullYear());
      this._year = years.includes(cur) ? cur : years[0];
    }
    const chip = (v, label) => `<button class="yr" data-year="${esc(v)}" aria-pressed="${this._year === v}">${esc(label)}</button>`;
    let h = `<div class="years">${chip("all", t.all)}${years.map((y) => chip(y, y)).join("")}</div>`;
    const shown = (this._year === "all" ? all : all.filter((r) => r.date.startsWith(this._year)))
      .slice().sort((a, b) => b.date.localeCompare(a.date) || a.name.localeCompare(b.name)); // mais nova primeiro
    if (!shown.length) return h + `<div class="empty">${esc(t.noRacesYear)}</div>`;
    const km = shown.reduce((sum, r) => sum + (Number(r.distance_km) || 0), 0);
    h += `<div class="rsum">${shown.length} ${esc(shown.length === 1 ? t.races1 : t.racesN)} · ${fmtNum(km, km % 1 ? 1 : 0)} km</div>`;
    const nextRace = all.filter((r) => r.date >= todayIso).sort((a, b) => a.date.localeCompare(b.date))[0];
    // Diferença de calendário entre hoje e a data, em anos, meses e dias ("1 ano, 2 meses e 5 dias").
    const rel = (iso) => {
      if (iso === todayIso) return t.todayRace;
      const future = iso > todayIso;
      const [a, b] = (future ? [todayIso, iso] : [iso, todayIso]).map((v) => v.split("-").map(Number));
      let y = b[0] - a[0], m = b[1] - a[1], d = b[2] - a[2];
      if (d < 0) { m -= 1; d += new Date(b[0], b[1] - 1, 0).getDate(); }
      if (m < 0) { y -= 1; m += 12; }
      const part = (n, u) => (n ? `${n} ${t.units[u][n === 1 ? 0 : 1]}` : null);
      const parts = [part(y, "y"), part(m, "m"), part(d, "d")].filter(Boolean);
      const text = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} ${t.and} ${parts[parts.length - 1]}` : parts[0];
      return (future ? t.inRel : t.agoRel).replace("{t}", text);
    };
    const SIT = { "Atingido": "var(--success-color, #43a047)", "Não Atingido": "var(--error-color, #db4437)", "Em Espera": "var(--warning-color, #ffa726)",
      "Em Andamento": "var(--primary-color, #03a9f4)" };
    let lastYear = null;
    for (const r of shown) {
      const year = r.date.slice(0, 4);
      if (this._year === "all" && year !== lastYear) { h += `<div class="ryear">${year}</div>`; lastYear = year; }
      const past = r.date < todayIso;
      const isNext = nextRace && r.id === nextRace.id && r.date === nextRace.date;
      const pn = String(r.priority || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const prio = pn.startsWith("princ") ? "gold" : pn.startsWith("secund") ? "silver" : pn.startsWith("terc") ? "bronze" : "";
      const meta = r.status && r.status !== "Exibir" ? r.status : "";
      const regBtn = r.key ? `<button class="reg" data-reg="${esc(r.key)}" aria-pressed="${!!r.registered}" title="${esc(t.reg)}: ${esc(r.registered ? t.regOn : t.regOff)}" aria-label="${esc(t.reg)}: ${esc(r.registered ? t.regOn : t.regOff)}"><span class="rh">${esc(t.reg)}</span><span class="rv">${r.registered ? "✓" : "✗"}</span></button>` : "";
      const chipColor = SIT[r.situation] || "var(--secondary-text-color)";
      const kmChip = r.distance_km != null ? `<span class="chip km ${r.registered ? "km-on" : "km-off"}" style="margin-left:0">${fmtNum(r.distance_km, r.distance_km % 1 ? 1 : 0)} km</span>` : "";
      const sitChip = r.situation ? `<span class="chip" style="margin-left:0;background:${chipColor}">${esc(r.situation)}</span>` : "";
      const [yy, mm, dd] = r.date.split("-").map(Number);
      const mon = new Date(yy, mm - 1, dd).toLocaleDateString(LOCALE, { month: "short" }).replace(".", "");
      h += `<div class="race${past ? " past" : ""}${isNext ? " next" : ""}${prio ? " p-" + prio : ""}"><div class="rleft"><div class="cal ${r.date < todayIso ? "c-past" : r.date === todayIso ? "c-today" : "c-future"}"><div class="cm">${yy}</div><b>${String(dd).padStart(2, "0")}</b><div class="cy">${esc(mon)}</div></div></div>
        <div class="rmain">${this._editKey === r.key
          ? `<div class="redit"><input class="rinput" data-key="${esc(r.key)}" maxlength="120" value="${esc(r.local_name || r.name)}"><button class="rbtn" data-save="${esc(r.key)}" title="${esc(t.renameSave)}" aria-label="${esc(t.renameSave)}">✓</button><button class="rbtn" data-cancel="1" title="${esc(t.renameCancel)}" aria-label="${esc(t.renameCancel)}">✕</button></div>`
          : `<div class="rname"${r.local_name ? ` title="${esc(t.renameHint + r.name)}"` : ""}>${esc(r.local_name || r.name)}${r.key && canEdit ? `<button class="rpen" data-rename="${esc(r.key)}" title="${esc(t.rename)}" aria-label="${esc(t.rename)}">✎</button>` : ""}</div>`}${r.key ? `<input class="rtime${r.finish_time ? "" : " zero"}" data-key="${esc(r.key)}" data-orig="${esc(r.finish_time || "")}" value="${esc(r.finish_time || "00:00:00")}" maxlength="20" title="${esc(t.timeTip)}" aria-label="${esc(t.timeTip)}"${canEdit ? "" : " readonly"}>` : ""}
        <div class="rmeta"><span class="rrel">${esc(rel(r.date))}</span>${meta ? `<span>${esc(meta)}</span>` : ""}</div></div>
        <div class="rside">${regBtn}${kmChip}</div></div>`;
    }
    return h;
  }

  // ---------- aba VO2 Max ----------
  _tests(ent) {
    const st = this._state(ent.performance);
    const hist = Array.isArray(st?.attributes?.history) ? st.attributes.history : [];
    return { st, tests: hist.filter((x) => x && x.date && x.vo2max != null).sort((a, b) => a.date.localeCompare(b.date)) };
  }

  _vo2(ent, t) {
    const { st, tests } = this._tests(ent);
    if (!st || !tests.length) return `<div class="empty">${esc(t.noTests)}</div>`;
    const last = tests[tests.length - 1], prev = tests[tests.length - 2];
    let delta = "";
    if (prev) {
      const d = last.vo2max - prev.vo2max;
      const up = d >= 0;
      delta = `<span class="delta" style="color:${up ? "var(--success-color,#43a047)" : "var(--error-color,#db4437)"}">${up ? "▲" : "▼"} ${up ? "+" : "−"}${fmtNum(Math.abs(d), 2)} <span class="muted">${esc(t.change)}</span></span>`;
    }
    const sel = this._sel != null && tests[this._sel] ? this._sel : null;
    let h = `<div class="hero"><span class="big">${fmtNum(last.vo2max, 2)}</span><span class="u">${esc(t.unit)}</span>${delta}</div>
      <div class="sub">${esc(t.latest)}: ${esc(fmtDate(last.date))} · ${esc(last.protocol || "")}${last.time ? ` · ${esc(last.time)}` : ""} · ${tests.length} ${esc(t.tests)}</div>`;
    h += `<div class="chart" id="chart">${this._svg(tests, sel, t)}<div class="tip" id="tip" hidden></div></div>`;
    h += `<div class="tscroll"><table class="vt"><thead><tr><th>${esc(t.date)}</th><th class="n">${esc(t.distance)}</th><th class="n">${esc(t.time)}</th><th class="n">${esc(t.pace)}</th><th class="n">Vo2 Max</th><th class="n">${esc(t.vsPrev)}</th></tr></thead><tbody>`;
    [...tests].reverse().forEach((x, ri) => {
      const idx = tests.length - 1 - ri;
      const before = tests[idx - 1];
      let cmp = '<span class="muted">–</span>';
      if (before && x.vo2max != null && before.vo2max != null) {
        const d = x.vo2max - before.vo2max;
        if (Math.abs(d) >= 0.005) cmp = d > 0
          ? `<span class="cmp up" title="+${fmtNum(d, 2)}">▲ +${fmtNum(d, 2)}</span>`
          : `<span class="cmp down" title="−${fmtNum(-d, 2)}">▼ −${fmtNum(-d, 2)}</span>`;
      }
      h += `<tr class="${idx === sel ? "sel" : ""}"><td>${esc(fmtDate(x.date))}</td><td class="n">${fmtNum(x.distance_km, 3)} km</td><td class="n">${esc(x.time || "–")}</td><td class="n">${esc(x.pace || "–")}</td><td class="n">${fmtNum(x.vo2max, 2)}</td><td class="n">${cmp}</td></tr>`;
    });
    return h + `</tbody></table></div>`;
  }

  _geom(tests) {
    const W = 600, H = 220, L = 38, R = 14, Tp = 14, B = 28;
    const vals = tests.map((x) => x.vo2max);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = Math.max((hi - lo) * 0.2, 1);
    lo = Math.floor(lo - pad); hi = Math.ceil(hi + pad);
    const ts = tests.map((x) => new Date(x.date + "T00:00:00").getTime());
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const X = (i) => (t1 === t0 ? (L + W - R) / 2 : L + ((ts[i] - t0) / (t1 - t0)) * (W - L - R));
    const Y = (v) => Tp + (1 - (v - lo) / (hi - lo)) * (H - Tp - B);
    return { W, H, L, R, Tp, B, lo, hi, ts, t0, t1, X, Y };
  }

  _svg(tests, sel, t) {
    const g = this._geom(tests);
    const step = Math.max(1, Math.round((g.hi - g.lo) / 4));
    let s = `<svg viewBox="0 0 ${g.W} ${g.H}" role="img" aria-label="VO2 Max">`;
    for (let v = g.lo; v <= g.hi; v += step) s += `<line class="grid" x1="${g.L}" x2="${g.W - g.R}" y1="${g.Y(v)}" y2="${g.Y(v)}"/><text x="${g.L - 6}" y="${g.Y(v) + 4}" text-anchor="end">${v}</text>`;
    const n = Math.min(tests.length, 5);
    const seen = new Set();
    for (let k = 0; k < n; k++) {
      const i = n === 1 ? 0 : Math.round((k * (tests.length - 1)) / (n - 1));
      if (seen.has(i)) continue; seen.add(i);
      const anchor = i === 0 ? "start" : i === tests.length - 1 ? "end" : "middle";
      s += `<text x="${g.X(i)}" y="${g.H - 8}" text-anchor="${anchor}">${esc(fmtDate(tests[i].date, { month: "2-digit", year: "2-digit" }))}</text>`;
    }
    if (tests.length > 1) s += `<polyline class="line" points="${tests.map((x, i) => `${g.X(i)},${g.Y(x.vo2max)}`).join(" ")}"/>`;
    s += `<line class="cross" id="cross" y1="${g.Tp}" y2="${g.H - g.B}" visibility="hidden"/>`;
    tests.forEach((x, i) => { s += `<circle class="pt${i === sel ? " act" : ""}" data-i="${i}" cx="${g.X(i)}" cy="${g.Y(x.vo2max)}" r="4.5"/>`; });
    s += `<rect id="hit" x="${g.L}" y="0" width="${g.W - g.L - g.R}" height="${g.H - g.B}" fill="transparent"/>`;
    return s + `</svg>`;
  }

  _bindChart() {
    const root = this.shadowRoot, chart = root.getElementById("chart");
    if (!chart) return;
    const { tests } = this._tests(this._find());
    const svg = chart.querySelector("svg"), tip = root.getElementById("tip"), cross = root.getElementById("cross");
    const g = this._geom(tests);
    const nearest = (ev) => {
      const r = svg.getBoundingClientRect();
      const x = ((ev.clientX - r.left) / r.width) * g.W;
      let best = 0, bd = Infinity;
      tests.forEach((_, i) => { const d = Math.abs(g.X(i) - x); if (d < bd) { bd = d; best = i; } });
      return best;
    };
    const show = (i) => {
      const x = tests[i], r = svg.getBoundingClientRect(), cr = chart.getBoundingClientRect();
      const px = (g.X(i) / g.W) * r.width + (r.left - cr.left), py = (g.Y(x.vo2max) / g.H) * r.height + (r.top - cr.top);
      cross.setAttribute("x1", g.X(i)); cross.setAttribute("x2", g.X(i)); cross.setAttribute("visibility", "visible");
      tip.innerHTML = `<b>${fmtNum(x.vo2max, 2)}</b> ${esc(this._t.unit)}<br>${esc(fmtDate(x.date))} · ${esc(x.protocol || "")}${x.time ? ` · ${esc(x.time)}` : ""}`;
      tip.style.left = `${Math.min(Math.max(px, 80), cr.width - 80)}px`; tip.style.top = `${py}px`; tip.hidden = false;
      root.querySelectorAll(".pt").forEach((c) => c.classList.toggle("act", Number(c.dataset.i) === i));
    };
    const hide = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); root.querySelectorAll(".pt").forEach((c, i) => c.classList.toggle("act", i === this._sel)); };
    svg.addEventListener("pointermove", (ev) => show(nearest(ev)));
    svg.addEventListener("pointerleave", hide);
    svg.addEventListener("click", (ev) => { const i = nearest(ev); this._sel = this._sel === i ? null : i; this._render(); });
  }
}

if (!customElements.get("ha-sisrun-card")) customElements.define("ha-sisrun-card", SisrunCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ha-sisrun-card")) {
  window.customCards.push({
    type: "ha-sisrun-card", name: "SisRUN", preview: false,
    description: "Planilha semanal, teste de desempenho (VO2 Max) e histórico do SisRUN.",
  });
}
console.info(`%c SISRUN-CARD %c ${CARD_VERSION} `, "background:#03a9f4;color:#fff", "");
