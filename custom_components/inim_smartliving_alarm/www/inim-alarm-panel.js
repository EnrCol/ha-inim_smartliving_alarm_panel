/*
 * INIM alarm panel card.
 *
 * An alarm panel in the style of the Home Assistant one, with one button per
 * scenario programmed on the panel and its real name. It reads everything
 * from the scenario select of the INIM SmartLiving integration
 * (select.<panel>_scenario): options, active scenario, alarm state, open zones.
 *
 * type: custom:inim-alarm-panel
 * entity: select.inim_smartliving_scenario
 * name: Allarme            # optional title
 * confirm: true            # second tap to confirm (default true)
 * show_zones: true         # list open zones (default true)
 * hide: [SCENARIO X]       # optional, scenario names to hide
 * names: {TOTALE: Fuori}   # optional, labels to show instead of panel names
 * icons: {NOTTE: mdi:weather-night}  # optional
 */

const TEXT = {
  it: {
    disarmed: "Disinserito",
    armed: "Inserito",
    triggered: "ALLARME",
    unknown: "Sconosciuto",
    unavailable: "Non disponibile",
    confirm: "Tocca di nuovo",
    sending: "Invio…",
    open: "Zone aperte",
    none: "Nessuna zona aperta",
    missing: "Scegli l'entità scenario dell'integrazione INIM",
    description: "Pannello allarme con gli scenari della centrale INIM",
  },
  en: {
    disarmed: "Disarmed",
    armed: "Armed",
    triggered: "ALARM",
    unknown: "Unknown",
    unavailable: "Unavailable",
    confirm: "Tap again",
    sending: "Sending…",
    open: "Open zones",
    none: "No open zones",
    missing: "Choose the scenario entity of the INIM integration",
    description: "Alarm panel with the scenarios of the INIM panel",
  },
};

const STATE_ICON = {
  disarmed: "mdi:shield-off-outline",
  armed: "mdi:shield-lock",
  triggered: "mdi:bell-ring",
  unknown: "mdi:shield-outline",
};

const STATE_COLOR = {
  disarmed: "var(--state-alarm_control_panel-disarmed-color, var(--success-color, #43a047))",
  armed: "var(--state-alarm_control_panel-armed_away-color, var(--warning-color, #ff9800))",
  triggered: "var(--state-alarm_control_panel-triggered-color, var(--error-color, #db4437))",
  unknown: "var(--disabled-text-color, #9e9e9e)",
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class InimAlarmPanel extends HTMLElement {
  setConfig(config) {
    this._config = { confirm: true, show_zones: true, hide: [], names: {}, icons: {}, ...config };
    this._armed = null;
    this._pending = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    const old = this._hass?.states?.[this._config?.entity];
    this._hass = hass;
    const now = hass.states[this._config?.entity];
    if (this._pending && now && now.state !== this._pending.from) this._pending = null;
    if (old !== now || !this.shadowRoot?.childElementCount) this._render();
  }

  getCardSize() {
    return 5;
  }

  _t(key) {
    const lang = (this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key];
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const stateObj = this._hass?.states?.[this._config.entity];
    if (!stateObj) {
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">${esc(this._t("missing"))}</div></ha-card>${STYLE}`;
      return;
    }
    const attrs = stateObj.attributes || {};
    const unavailable = stateObj.state === "unavailable";
    const alarm = unavailable ? "unknown" : attrs.alarm_state || "unknown";
    const color = STATE_COLOR[alarm] || STATE_COLOR.unknown;
    const active = attrs.active_scenario_index;
    const hide = new Set(this._config.hide || []);
    const scenarios = (attrs.scenarios || []).filter((s) => !hide.has(s.name));
    const label = (s) => this._config.names?.[s.name] || s.name;
    const activeScenario = (attrs.scenarios || []).find((s) => s.index === active);
    const stateText = unavailable ? this._t("unavailable") : this._t(alarm);
    const title = this._config.name ?? stateObj.attributes.friendly_name ?? "";

    const buttons = scenarios
      .map((s) => {
        const icon =
          this._config.icons?.[s.name] || (s.kind === "disarm" ? "mdi:shield-off-outline" : "mdi:shield-lock-outline");
        const isActive = s.index === active;
        const isArmed = this._armed === s.index;
        const isPending = this._pending?.index === s.index;
        const text = isPending ? this._t("sending") : isArmed ? this._t("confirm") : label(s);
        return `<button class="scenario ${isActive ? "active" : ""} ${isArmed ? "confirm" : ""}"
                  data-index="${s.index}" ${unavailable || isPending ? "disabled" : ""}>
                  <ha-icon icon="${esc(icon)}"></ha-icon><span>${esc(text)}</span></button>`;
      })
      .join("");

    const zones = attrs.open_zones || [];
    const zonesHtml = this._config.show_zones
      ? `<div class="zones ${zones.length ? "warn" : ""}">
           <ha-icon icon="${zones.length ? "mdi:door-open" : "mdi:door-closed"}"></ha-icon>
           <span>${zones.length ? `${esc(this._t("open"))}: ${zones.map(esc).join(", ")}` : esc(this._t("none"))}</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <ha-card>
        ${title ? `<div class="title">${esc(title)}</div>` : ""}
        <div class="status ${alarm}" style="--alarm-color:${color}">
          <div class="badge"><ha-icon icon="${STATE_ICON[alarm] || STATE_ICON.unknown}"></ha-icon></div>
          <div class="state">${esc(stateText)}</div>
          <div class="scenario-name">${esc(activeScenario ? label(activeScenario) : "")}</div>
        </div>
        <div class="buttons">${buttons}</div>
        ${zonesHtml}
      </ha-card>${STYLE}`;

    this.shadowRoot.querySelectorAll("button.scenario").forEach((button) =>
      button.addEventListener("click", () => this._press(Number(button.dataset.index)))
    );
  }

  _press(index) {
    const stateObj = this._hass.states[this._config.entity];
    const scenario = (stateObj?.attributes?.scenarios || []).find((s) => s.index === index);
    if (!scenario) return;
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
        { name: "confirm", default: true, selector: { boolean: {} } },
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
  ha-card { padding: 16px; }
  .missing { padding: 8px; color: var(--secondary-text-color); }
  .title { font-size: 1.2em; font-weight: 500; margin-bottom: 8px; }
  .status { display: flex; flex-direction: column; align-items: center; gap: 4px; margin: 4px 0 16px; }
  .badge { width: 88px; height: 88px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
           background: color-mix(in srgb, var(--alarm-color) 20%, transparent); color: var(--alarm-color); }
  .badge ha-icon { --mdc-icon-size: 48px; }
  .status.triggered .badge { animation: pulse 1s ease-in-out infinite; }
  @keyframes pulse { 50% { transform: scale(1.08); background: color-mix(in srgb, var(--alarm-color) 40%, transparent); } }
  .state { font-size: 1.5em; font-weight: 500; color: var(--alarm-color); }
  .scenario-name { color: var(--secondary-text-color); min-height: 1.2em; }
  .buttons { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
  button.scenario { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 8px;
                    border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color);
                    background: var(--card-background-color); color: var(--primary-text-color);
                    font: inherit; cursor: pointer; transition: background .2s, border-color .2s; }
  button.scenario:hover { background: var(--secondary-background-color); }
  button.scenario.active { border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 15%, transparent); }
  button.scenario.confirm { border-color: var(--warning-color, #ff9800); background: color-mix(in srgb, var(--warning-color, #ff9800) 20%, transparent); }
  button.scenario:disabled { opacity: .6; cursor: default; }
  button.scenario span { text-align: center; word-break: break-word; }
  .zones { display: flex; gap: 8px; align-items: flex-start; margin-top: 16px; color: var(--secondary-text-color); }
  .zones.warn { color: var(--warning-color, #ff9800); }
</style>`;

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
