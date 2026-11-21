/*
 * INIM alarm panel card.
 *
 * Drawn like the Home Assistant alarm panel dialog: the state in large type,
 * the time of the last change, and a vertical column of pill buttons, one
 * per scenario programmed on the panel, with its real name. The active
 * scenario is filled with the alarm colour. Everything comes from the
 * scenario select of the INIM SmartLiving integration
 * (select.<panel>_scenario): options, active scenario, alarm state, open zones.
 *
 * type: custom:inim-alarm-panel
 * entity: select.inim_smartliving_scenario
 * name: Allarme            # optional header (default: entity name)
 * confirm: true            # second tap to confirm (default true)
 * show_zones: true         # list open zones (default true)
 * show_time: true          # "18 minutes ago" under the state (default true)
 * compact: false           # one row like a tile; a tap opens the panel in a dialog
 * hide: [SCENARIO X]       # optional, scenario names to hide
 * names: {TOTALE: Fuori}   # optional, labels instead of panel names
 * icons: {NOTTE: mdi:weather-night}  # optional
 */

const TEXT = {
  it: {
    disarmed: "Disinserito",
    armed: "Inserito",
    triggered: "Allarme in corso",
    unknown: "Sconosciuto",
    unavailable: "Non disponibile",
    confirm: "Tocca di nuovo per confermare",
    sending: "Invio…",
    open: "Zone aperte",
    none: "Nessuna zona aperta",
    missing: "Scegli l'entità scenario dell'integrazione INIM",
  },
  en: {
    disarmed: "Disarmed",
    armed: "Armed",
    triggered: "Triggered",
    unknown: "Unknown",
    unavailable: "Unavailable",
    confirm: "Tap again to confirm",
    sending: "Sending…",
    open: "Open zones",
    none: "No open zones",
    missing: "Choose the scenario entity of the INIM integration",
  },
};

// Same variables (and defaults) the Home Assistant frontend uses for alarm states.
const COLOR = {
  armed: "var(--state-alarm_control_panel-armed_away-color, var(--green-color, #4caf50))",
  disarmed: "var(--state-alarm_control_panel-disarmed-color, var(--grey-color, #9e9e9e))",
  triggered: "var(--state-alarm_control_panel-triggered-color, var(--red-color, #f44336))",
  pending: "var(--state-alarm_control_panel-pending-color, var(--orange-color, #ff9800))",
  unknown: "var(--disabled-color, #bdbdbd)",
};

const HEADER_ICON = {
  disarmed: "mdi:shield-off",
  armed: "mdi:shield-lock",
  triggered: "mdi:bell-ring",
  unknown: "mdi:shield",
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function relativeTime(iso, lang) {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  if (!Number.isFinite(seconds)) return "";
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  const steps = [
    [60, "second"],
    [3600, "minute", 60],
    [86400, "hour", 3600],
    [604800, "day", 86400],
    [Infinity, "week", 604800],
  ];
  const abs = Math.abs(seconds);
  for (const [limit, unit, div = 1] of steps) {
    if (abs < limit) return rtf.format(Math.round(seconds / div), unit);
  }
  return "";
}

class InimAlarmPanel extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity is required");
    this._config = { confirm: true, show_zones: true, show_time: true, hide: [], names: {}, icons: {}, ...config };
    this._armed = null;
    this._pending = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  connectedCallback() {
    // Keep "x minutes ago" fresh.
    this._tick = setInterval(() => this._render(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._closeDialog();
  }

  set hass(hass) {
    const old = this._hass?.states?.[this._config?.entity];
    this._hass = hass;
    const now = hass.states[this._config?.entity];
    if (this._pending && now && now.state !== this._pending.from) this._pending = null;
    if (old !== now || !this.shadowRoot?.childElementCount) this._render();
  }

  getCardSize() {
    return this._config?.compact ? 1 : 6;
  }

  getGridOptions() {
    return this._config?.compact
      ? { columns: 6, min_columns: 3, rows: 1 }
      : { columns: 6, min_columns: 4, rows: "auto" };
  }

  _lang() {
    return (this._hass?.language || "en").slice(0, 2);
  }

  _t(key) {
    return (TEXT[this._lang()] || TEXT.en)[key];
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const stateObj = this._hass?.states?.[this._config.entity];
    if (!stateObj) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="missing">${esc(this._t("missing"))}</div></ha-card>`;
      return;
    }
    const attrs = stateObj.attributes || {};
    const unavailable = stateObj.state === "unavailable";
    const alarm = unavailable ? "unknown" : attrs.alarm_state || "unknown";
    const active = attrs.active_scenario_index;
    const hide = new Set(this._config.hide || []);
    const all = attrs.scenarios || [];
    const scenarios = all.filter((s) => !hide.has(s.name));
    const label = (s) => this._config.names?.[s.name] || s.name;
    const activeScenario = all.find((s) => s.index === active);
    const title = this._config.name ?? attrs.friendly_name ?? "";

    // Like "Attivo in casa" in the HA dialog: the active scenario is the headline
    // when armed, the alarm state and the time of the change go underneath.
    const stateText = unavailable ? this._t("unavailable") : this._t(alarm);
    const armedName = !unavailable && alarm === "armed" && activeScenario ? label(activeScenario) : null;
    const headline = armedName || stateText;
    const time = this._config.show_time ? relativeTime(stateObj.last_changed, this._lang()) : "";
    const sub = this._pending
      ? this._t("sending")
      : this._armed !== null
      ? this._t("confirm")
      : [armedName ? stateText : "", time].filter(Boolean).join(" · ");

    const pills = scenarios
      .map((s) => {
        const icon =
          this._config.icons?.[s.name] || (s.kind === "disarm" ? "mdi:shield-off" : "mdi:shield-lock");
        const isActive = s.index === active;
        const color = alarm === "triggered" ? COLOR.triggered : s.kind === "disarm" ? COLOR.disarmed : COLOR.armed;
        const classes = [
          "pill",
          isActive ? "active" : "",
          this._armed === s.index ? "confirm" : "",
          this._pending?.index === s.index ? "pending" : "",
        ].join(" ");
        return `<button class="${classes}" style="--pill-color:${color}" data-index="${s.index}"
                  ${unavailable || this._pending ? "disabled" : ""} aria-pressed="${isActive}">
                  <ha-icon icon="${esc(icon)}"></ha-icon><span>${esc(label(s))}</span></button>`;
      })
      .join("");

    const zones = attrs.open_zones || [];
    const zonesHtml = this._config.show_zones
      ? `<div class="zones ${zones.length ? "warn" : ""}">
           <ha-icon icon="${zones.length ? "mdi:door-open" : "mdi:door-closed"}"></ha-icon>
           <span>${zones.length ? `${esc(this._t("open"))}: ${zones.map(esc).join(", ")}` : esc(this._t("none"))}</span>
         </div>`
      : "";

    const color = COLOR[alarm] || COLOR.unknown;
    const iconHtml = `<div class="header-icon"><ha-icon icon="${HEADER_ICON[alarm] || HEADER_ICON.unknown}"></ha-icon></div>`;
    const body = `
        <div class="state">${esc(headline)}</div>
        <div class="sub">${esc(sub)}</div>
        <div class="column">${pills}</div>
        ${zonesHtml}`;

    if (this._config.compact) {
      // One row like a tile; a tap opens the panel in a dialog.
      const line = armedName ? `${armedName} · ${stateText}` : stateText;
      this.shadowRoot.innerHTML = `${STYLE}
        <ha-card class="compact ${alarm}" style="--alarm-color:${color}" role="button" tabindex="0">
          ${iconHtml}
          <div class="info"><div class="header-name">${esc(title)}</div><div class="compact-state">${esc(line)}</div></div>
          <ha-icon class="chevron" icon="mdi:chevron-right"></ha-icon>
        </ha-card>`;
      const card = this.shadowRoot.querySelector("ha-card");
      card.addEventListener("click", () => this._openDialog());
      card.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && this._openDialog());
      if (this._dialog) this._renderDialog(alarm, color, iconHtml, title, body);
      return;
    }

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card class="${alarm}" style="--alarm-color:${color}">
        <div class="header">${iconHtml}<div class="header-name">${esc(title)}</div></div>
        ${body}
      </ha-card>`;
    this._bindPills(this.shadowRoot);
    this.shadowRoot.querySelector(".header")?.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: this._config.entity }, bubbles: true, composed: true }));
    });
  }

  _bindPills(root) {
    root.querySelectorAll("button.pill").forEach((button) =>
      button.addEventListener("click", () => this._press(Number(button.dataset.index)))
    );
  }

  _openDialog() {
    if (this._dialog) return;
    // Attached to <body>, outside the dashboard layout, so it covers the page.
    this._dialog = document.createElement("div");
    this._dialog.attachShadow({ mode: "open" });
    document.body.appendChild(this._dialog);
    this._onKey = (e) => e.key === "Escape" && this._closeDialog();
    document.addEventListener("keydown", this._onKey);
    this._render();
  }

  _closeDialog() {
    if (!this._dialog) return;
    this._dialog.remove();
    this._dialog = null;
    this._armed = null;
    document.removeEventListener("keydown", this._onKey);
    this._onDialogClosed?.();
  }

  _renderDialog(alarm, color, iconHtml, title, body) {
    const root = this._dialog.shadowRoot;
    const opened = root.childElementCount > 0;
    root.innerHTML = `${STYLE}${DIALOG_STYLE}
      <div class="backdrop"></div>
      <div class="sheet ${alarm} ${opened ? "" : "opening"}" style="--alarm-color:${color}" role="dialog" aria-modal="true">
        <div class="handle"></div>
        <div class="header">${iconHtml}<div class="header-name">${esc(title)}</div>
          <button class="close" aria-label="close"><ha-icon icon="mdi:close"></ha-icon></button></div>
        ${body}
      </div>`;
    root.querySelector(".backdrop").addEventListener("click", () => this._closeDialog());
    root.querySelector(".close").addEventListener("click", () => this._closeDialog());
    this._bindPills(root);
  }

  _press(index) {
    const stateObj = this._hass.states[this._config.entity];
    const scenario = (stateObj?.attributes?.scenarios || []).find((s) => s.index === index);
    if (!scenario || scenario.index === stateObj.attributes.active_scenario_index) return;
    if (this._config.confirm && this._armed !== index) {
      this._armed = index;
      clearTimeout(this._armTimer);
      this._armTimer = setTimeout(() => {
        this._armed = null;
        this._render();
      }, 4000);
      this._render();
      return;
    }
    clearTimeout(this._armTimer);
    this._armed = null;
    this._pending = { index, from: stateObj.state };
    clearTimeout(this._pendingTimer);
    this._pendingTimer = setTimeout(() => {
      this._pending = null;
      this._render();
    }, 8000);
    this._render();
    this._hass
      .callService("select", "select_option", { entity_id: this._config.entity, option: scenario.name })
      .catch(() => {
        this._pending = null;
        this._render();
      });
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "select", integration: "inim_smartliving_alarm" } } },
        { name: "name", selector: { text: {} } },
        { name: "compact", default: false, selector: { boolean: {} } },
        { name: "confirm", default: true, selector: { boolean: {} } },
        { name: "show_time", default: true, selector: { boolean: {} } },
        { name: "show_zones", default: true, selector: { boolean: {} } },
      ],
    };
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("select.") && Array.isArray(hass.states[id].attributes?.scenarios)
    );
    return { entity: entity || "" };
  }
}

const STYLE = `<style>
  ha-card { padding: 16px 16px 20px; display: flex; flex-direction: column; align-items: center; }
  .missing { padding: 8px; color: var(--secondary-text-color); }
  .header { align-self: stretch; display: flex; align-items: center; gap: 12px; cursor: pointer; }
  .header-icon { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                 color: var(--alarm-color); background: color-mix(in srgb, var(--alarm-color) 20%, transparent); }
  .header-icon ha-icon { --mdc-icon-size: 22px; }
  .header-name { font-size: 16px; font-weight: 500; color: var(--primary-text-color);
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .state { margin-top: 16px; font-size: 30px; line-height: 38px; overflow-wrap: anywhere; font-weight: 400; text-align: center;
           color: var(--primary-text-color); }
  ha-card.triggered .state { color: var(--alarm-color); }
  .sub { margin-top: 4px; min-height: 20px; font-size: 14px; color: var(--secondary-text-color); text-align: center; }
  .column { margin-top: 20px; width: 100%; max-width: 220px; display: flex; flex-direction: column; gap: 4px; padding: 4px;
            box-sizing: border-box; border-radius: 32px;
            background: var(--ha-control-select-background, var(--secondary-background-color, rgba(0,0,0,.06))); }
  .pill { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
          min-height: 62px; padding: 8px 12px; border: none; border-radius: 28px; background: transparent;
          color: var(--primary-text-color); font: inherit; font-size: 15px; font-weight: 500; cursor: pointer;
          transition: background-color .18s ease, color .18s ease; -webkit-tap-highlight-color: transparent; }
  .pill ha-icon { --mdc-icon-size: 24px; }
  .pill span { text-align: center; word-break: break-word; }
  .pill:hover:not(:disabled):not(.active) { background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }
  .pill.active { background: var(--pill-color); color: var(--text-primary-color, #fff); cursor: default; }
  .pill.confirm { background: color-mix(in srgb, var(--pill-color) 28%, transparent);
                  box-shadow: inset 0 0 0 2px var(--pill-color); }
  .pill.pending { animation: pulse 1s ease-in-out infinite; background: color-mix(in srgb, var(--pill-color) 35%, transparent); }
  .pill:disabled:not(.active):not(.pending) { opacity: .5; cursor: default; }
  ha-card.triggered .pill.active { animation: pulse 1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .55; } }
  .zones { align-self: stretch; display: flex; gap: 8px; align-items: flex-start; margin-top: 20px;
           font-size: 14px; color: var(--secondary-text-color); }
  .zones ha-icon { --mdc-icon-size: 20px; flex: none; }
  .zones.warn { color: var(--warning-color, #ff9800); }
  ha-card.compact { flex-direction: row; align-items: center; gap: 12px; padding: 10px 12px; cursor: pointer; }
  ha-card.compact .info { flex: 1; min-width: 0; }
  .compact-state { font-size: 14px; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  ha-card.compact.armed .compact-state, ha-card.compact.triggered .compact-state { color: var(--alarm-color); }
  .chevron { color: var(--secondary-text-color); --mdc-icon-size: 20px; }
</style>`;

const DIALOG_STYLE = `<style>
  .backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(0, 0, 0, .45); }
  .sheet { position: fixed; z-index: 1001; left: 50%; top: 50%; transform: translate(-50%, -50%);
           width: min(420px, calc(100vw - 32px)); max-height: 90vh; overflow-y: auto; box-sizing: border-box;
           display: flex; flex-direction: column; align-items: center; padding: 12px 20px 28px;
           border-radius: 28px; color: var(--primary-text-color);
           background: var(--ha-dialog-surface-background, var(--card-background-color, var(--primary-background-color, #fff)));
           box-shadow: 0 8px 32px rgba(0, 0, 0, .3); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .sheet.opening { animation: fade .18s ease-out; }
  .sheet.triggered .state { color: var(--alarm-color); }
  .sheet.triggered .pill.active { animation: pulse 1s ease-in-out infinite; }
  .handle { display: none; width: 40px; height: 4px; border-radius: 2px; margin-bottom: 12px;
            background: var(--divider-color, rgba(0, 0, 0, .2)); }
  .sheet .header { cursor: default; }
  .sheet .header-name { flex: 1; }
  .close { border: none; background: transparent; color: var(--primary-text-color); cursor: pointer;
           width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
  .close:hover { background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }
  @keyframes fade { from { opacity: 0; transform: translate(-50%, -48%); } }
  @media (max-width: 600px) {
    .sheet { left: 0; right: 0; top: auto; bottom: 0; transform: none; width: 100%; max-height: 92vh;
             border-radius: 28px 28px 0 0; padding-bottom: calc(28px + env(safe-area-inset-bottom)); }
    .sheet.opening { animation: slide .22s ease-out; }
    .handle { display: block; }
    @keyframes slide { from { transform: translateY(100%); } }
  }
</style>`;

// Open the panel dialog from any card, e.g. a Mushroom or tile card:
//   tap_action:
//     action: fire-dom-event
//     inim_alarm_panel:
//       entity: select.inim_smartliving_scenario
//       name: Allarme          # optional, same options as the card
function openInimAlarmDialog(config) {
  const getHass = () => document.querySelector("home-assistant")?.hass;
  const hass = getHass();
  if (!hass || !config?.entity) return;
  const panel = document.createElement("inim-alarm-panel");
  panel.setConfig({ ...config, compact: true });
  panel.hass = hass;
  // The element is not in a dashboard, so nobody feeds it new states: poll the
  // frontend's hass object while the dialog is open.
  const timer = setInterval(() => {
    const now = getHass();
    if (now) panel.hass = now;
  }, 1000);
  panel._onDialogClosed = () => clearInterval(timer);
  panel._openDialog();
}

if (!window.__inimAlarmPanelListener) {
  window.__inimAlarmPanelListener = true;
  window.addEventListener("ll-custom", (ev) => {
    const config = ev.detail?.inim_alarm_panel;
    if (config) openInimAlarmDialog(config);
  });
}

if (!customElements.get("inim-alarm-panel")) {
  customElements.define("inim-alarm-panel", InimAlarmPanel);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "inim-alarm-panel",
    name: "INIM alarm panel",
    description: "Alarm panel with the scenarios of the INIM SmartLiving panel",
    preview: true,
  });
}
