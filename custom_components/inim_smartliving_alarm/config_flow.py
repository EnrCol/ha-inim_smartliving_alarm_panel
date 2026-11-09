"""Config flow for Inim Alarm integration."""

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PIN, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_EVENT_LOG_SIZE,
    CONF_LIMIT_AREAS,
    CONF_LIMIT_SCENARIOS,
    CONF_LIMIT_ZONES,
    CONF_PANEL_MODEL,
    CONF_PANEL_NAME,
    CONF_POLLING_INTERVAL,
    CONF_SLOW_POLLING_INTERVAL,
    CONF_READER_NAMES,
    CONF_REFRESH_INITIAL_CONFIG,
    CONF_SCENARIO_ARM_AWAY,
    CONF_SCENARIO_ARM_HOME,
    CONF_SCENARIO_ARM_NIGHT,
    CONF_SCENARIO_ARM_VACATION,
    CONF_SCENARIO_DISARM,
    DATA_INITIAL_PANEL_CONFIG,
    DATA_INITIAL_PANEL_CONFIG_REVISION,
    DEFAULT_EVENT_LOG_SIZE,
    DEFAULT_LIMIT_AREAS,
    DEFAULT_LIMIT_SCENARIOS,
    DEFAULT_LIMIT_ZONES,
    DEFAULT_PANEL_MODEL,
    DEFAULT_PANEL_NAME,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_SLOW_POLLING_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    INITIAL_PANEL_CONFIG_REVISION,
    SYSTEM_MAX_AREAS,
    SYSTEM_MAX_EVENT_LOG_SIZE,
    SYSTEM_MAX_SCENARIOS,
    SYSTEM_MAX_ZONES,
)
from .effective_entities import build_automatic_options, effective_indexes
from .inim_api import InimAlarmAPI
from .panel_profiles import (
    PANEL_MODEL_10100,
    PANEL_MODEL_AUTO,
    PANEL_MODEL_OPTIONS,
    PANEL_MODEL_SETUP_OPTIONS,
    detect_panel_model,
    read_panel_system_info,
    apply_panel_profile_api_patches,
    configure_api_for_panel,
    get_panel_profile,
)

_LOGGER = logging.getLogger(__name__)

# Ensure config-flow validation uses the same profile-aware API methods as runtime.
apply_panel_profile_api_patches()

SCENARIO_MAPPING_KEYS = [
    CONF_SCENARIO_ARM_HOME,
    CONF_SCENARIO_ARM_AWAY,
    CONF_SCENARIO_ARM_NIGHT,
    CONF_SCENARIO_ARM_VACATION,
    CONF_SCENARIO_DISARM,
]


async def _validate_connection_and_fetch_initial_config(
    hass: HomeAssistant,
    host: str,
    port: int,
    pin: str,
    panel_model: str | None = DEFAULT_PANEL_MODEL,
) -> dict[str, Any]:
    """Validate connection details by fetching initial panel configuration."""

    api = InimAlarmAPI(host=host, port=port, pin_code_str=pin)
    detected_model: str | None = None
    if panel_model == PANEL_MODEL_AUTO:
        system_info = await hass.async_add_executor_job(read_panel_system_info, api)
        if system_info is None:
            raise ConnectionError("Failed to read the panel system info.")
        detected_model = detect_panel_model(system_info.get("type"))
        if detected_model is None:
            _LOGGER.warning(
                "Unknown INIM panel type %r: using the %s profile",
                system_info.get("type"),
                DEFAULT_PANEL_MODEL,
            )
        panel_model = detected_model or DEFAULT_PANEL_MODEL
        _LOGGER.info(
            "INIM panel type %r detected: using profile %s",
            system_info.get("type"),
            panel_model,
        )
    configure_api_for_panel(api, panel_model)

    _LOGGER.debug(
        "Attempting to fetch initial panel configuration from %s:%s for validation using panel model %s",
        host,
        port,
        panel_model,
    )

    initial_config = await hass.async_add_executor_job(
        api.get_initial_panel_configuration
    )

    if initial_config is None:
        _LOGGER.error(
            "Connection/API error for %s:%s (API returned None)",
            host,
            port,
        )
        raise ConnectionError(
            "Failed to connect to the Inim panel or API error during fetch."
        )

    # Check for explicit errors reported by the API method
    if initial_config.get("errors"):
        _LOGGER.error(
            "Errors reported by API for %s:%s: %s",
            host,
            port,
            initial_config["errors"],
        )
        # If critical data is missing due to these errors, we'll catch it below.

    essential_keys = [
        "system_info",
        "areas",
        "zones",
        "zones_config",
        "scenarios",
        "scenario_activations",
    ]
    missing_or_failed_parts = [
        key for key in essential_keys if initial_config.get(key) is None
    ]

    if missing_or_failed_parts:
        error_message = f"Failed to retrieve essential data for: {', '.join(missing_or_failed_parts)}."
        _LOGGER.error("%s From %s:%s", error_message, host, port)
        if any("auth" in error.lower() for error in initial_config.get("errors", [])):
            raise ValueError("auth_failed")
        raise ValueError(error_message)

    if not initial_config.get("system_info") or not initial_config["system_info"].get(
        "ascii"
    ):
        _LOGGER.error("System information is missing from initial configuration")
        raise ValueError("invalid_panel_response")

    _LOGGER.info(
        "Initial panel configuration successfully validated/fetched for %s:%s",
        host,
        port,
    )
    initial_config["resolved_panel_model"] = panel_model
    return initial_config


def _build_scenario_choices(initial_config: dict[str, Any]) -> dict[str, str]:
    """Build scenario dropdown choices from the current initial panel configuration."""
    scenario_names_data = initial_config.get("scenarios", {})
    scenario_names_list = scenario_names_data.get("names", [])
    scenario_choices = {"none": "None (Do Not Assign)"}
    # Preserve the real zero-based INIM index, including gaps, but only show
    # programmed scenarios. Never offer a placeholder (e.g. SCENARIO 030).
    for i in effective_indexes(scenario_names_list, "scenario"):
        scenario_choices[str(i)] = f"{i}: {scenario_names_list[i].strip()}"
    return scenario_choices


def _scenario_default(settings: dict[str, Any], key: str, scenario_choices: dict[str, str]) -> str:
    """Return a valid default value for one scenario mapping selector."""
    value = settings.get(key, "none")
    if value is None:
        return "none"
    value_str = str(value)
    return value_str if value_str in scenario_choices else "none"


def _schema_limit_default(
    settings: dict[str, Any], key: str, profile: dict[str, Any], profile_key: str
) -> int:
    """Return an integer default for an import limit field."""
    value = settings.get(key)
    if value is None:
        return int(profile[profile_key])
    return int(value)


class InimAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Inim Alarm."""

    VERSION = 1
    _flow_data: dict = {}  # To store data between steps

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (host, port, pin, panel model, panel name)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store user input for this step temporarily
            self._flow_data["user_input_step1"] = user_input

            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()

            try:
                _LOGGER.info(
                    "Validating Inim Alarm connection for: %s", user_input[CONF_HOST]
                )
                initial_panel_config = (
                    await _validate_connection_and_fetch_initial_config(
                        self.hass,
                        user_input[CONF_HOST],
                        user_input[CONF_PORT],
                        user_input[CONF_PIN],
                        user_input.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
                    )
                )
                # "auto" is stored as the concrete profile it resolved to.
                user_input[CONF_PANEL_MODEL] = initial_panel_config.pop(
                    "resolved_panel_model",
                    user_input.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
                )
                self._flow_data[DATA_INITIAL_PANEL_CONFIG] = initial_panel_config
                _LOGGER.info(
                    "Inim Alarm connection validated for %s", user_input[CONF_HOST]
                )

                # Connection and initial data fetch successful, proceed to next step
                return await self.async_step_initial_options()

            except ConnectionError:
                _LOGGER.warning("Connection failed for %s", user_input[CONF_HOST])
                errors["base"] = "cannot_connect"
            except ValueError as vex:
                _LOGGER.warning(
                    "Validation error for %s: %s", user_input[CONF_HOST], vex
                )
                # Use specific error key if it's 'auth_failed' or 'invalid_panel_response'
                errors["base"] = (
                    str(vex)
                    if str(vex) in ["auth_failed", "invalid_panel_response"]
                    else "validation_error_detail"
                )
                if (
                    errors["base"] == "validation_error_detail"
                ):  # For generic ValueErrors with details
                    errors["detail"] = str(
                        vex
                    )  # Not standard, but an idea if form supported it
            except Exception as exc:
                _LOGGER.exception(
                    "Unexpected exception during Inim Alarm setup for %s: %s",
                    user_input[CONF_HOST],
                    exc,
                )
                errors["base"] = "unknown"

        user_data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=self._flow_data.get("user_input_step1", {}).get(
                        CONF_HOST, ""
                    ),
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=self._flow_data.get("user_input_step1", {}).get(
                        CONF_PORT, DEFAULT_PORT
                    ),
                ): cv.port,
                vol.Required(
                    CONF_PIN,
                    default=self._flow_data.get("user_input_step1", {}).get(
                        CONF_PIN, ""
                    ),
                ): str,
                vol.Optional(
                    CONF_PANEL_MODEL,
                    default=self._flow_data.get("user_input_step1", {}).get(
                        CONF_PANEL_MODEL, PANEL_MODEL_AUTO
                    ),
                ): vol.In(PANEL_MODEL_SETUP_OPTIONS),
                vol.Optional(
                    CONF_PANEL_NAME,
                    default=self._flow_data.get("user_input_step1", {}).get(
                        CONF_PANEL_NAME, DEFAULT_PANEL_NAME
                    ),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=user_data_schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Change host, port, PIN or panel model and read the panel again.

        For installations made with an older version: the panel configuration
        (names, model, terminal tables, outputs) is read again with the current
        code, without removing the integration. An empty PIN keeps the stored one.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input.get(CONF_PIN) or entry.data[CONF_PIN]
            # The panel accepts one connection at a time: release the running one.
            was_loaded = entry.state is config_entries.ConfigEntryState.LOADED
            if was_loaded:
                await self.hass.config_entries.async_unload(entry.entry_id)
                await asyncio.sleep(2.5)  # the SmartLAN delays a connection after a close
            try:
                initial_config = await _validate_connection_and_fetch_initial_config(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    pin,
                    user_input.get(CONF_PANEL_MODEL, PANEL_MODEL_AUTO),
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError as vex:
                errors["base"] = (
                    str(vex)
                    if str(vex) in ["auth_failed", "invalid_panel_response"]
                    else "unknown"
                )
            except Exception:  # never leave the integration unloaded
                _LOGGER.exception("Unexpected error while reconfiguring %s", entry.title)
                errors["base"] = "unknown"
            if errors and was_loaded:
                await self.hass.config_entries.async_setup(entry.entry_id)
            if not errors:
                panel_model = initial_config.pop("resolved_panel_model")
                options = dict(entry.options)
                options.pop(CONF_PANEL_MODEL, None)
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}",
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_PIN: pin,
                        CONF_PANEL_MODEL: panel_model,
                        DATA_INITIAL_PANEL_CONFIG: initial_config,
                        DATA_INITIAL_PANEL_CONFIG_REVISION: INITIAL_PANEL_CONFIG_REVISION,
                    },
                    options=options,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): cv.port,
                vol.Optional(CONF_PIN, default=""): str,
                vol.Optional(CONF_PANEL_MODEL, default=PANEL_MODEL_AUTO): vol.In(
                    PANEL_MODEL_SETUP_OPTIONS
                ),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_initial_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the second step for initial options (polling, limits, scenario mappings)."""
        errors: dict[str, str] = {}
        step1_data = self._flow_data["user_input_step1"]
        initial_config_data = self._flow_data[DATA_INITIAL_PANEL_CONFIG]
        panel_profile = get_panel_profile(step1_data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL))

        scenario_choices = _build_scenario_choices(initial_config_data)
        # On first installation, propose verified limits and unambiguous mappings
        # from the panel. Explicit user choices always override these defaults.
        detected_options, _ = build_automatic_options(initial_config_data, {})
        detected_limits = (
            detected_options
            if step1_data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL) == PANEL_MODEL_10100
            else {}
        )

        if user_input is not None:
            # Combine data from step 1 and this step
            final_data_for_entry = {
                CONF_HOST: step1_data[CONF_HOST],
                CONF_PORT: step1_data[CONF_PORT],
                CONF_PIN: step1_data[CONF_PIN],
                CONF_PANEL_MODEL: step1_data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
                CONF_PANEL_NAME: step1_data.get(CONF_PANEL_NAME, DEFAULT_PANEL_NAME),
                DATA_INITIAL_PANEL_CONFIG: initial_config_data,
                DATA_INITIAL_PANEL_CONFIG_REVISION: INITIAL_PANEL_CONFIG_REVISION,
            }

            final_options_for_entry = {
                CONF_PANEL_MODEL: step1_data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
                CONF_POLLING_INTERVAL: user_input[CONF_POLLING_INTERVAL],
                CONF_SLOW_POLLING_INTERVAL: user_input.get(
                    CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL
                ),
                CONF_LIMIT_AREAS: user_input[CONF_LIMIT_AREAS],
                CONF_LIMIT_ZONES: user_input[CONF_LIMIT_ZONES],
                CONF_LIMIT_SCENARIOS: user_input[CONF_LIMIT_SCENARIOS],
                CONF_EVENT_LOG_SIZE: min(
                    user_input[CONF_EVENT_LOG_SIZE], SYSTEM_MAX_EVENT_LOG_SIZE
                ),
                CONF_READER_NAMES: user_input.get(CONF_READER_NAMES, ""),
            }
            for key in SCENARIO_MAPPING_KEYS:
                val = user_input.get(key)
                final_options_for_entry[key] = (
                    int(val) if val and val != "none" else None
                )

            title = final_data_for_entry.get(CONF_PANEL_NAME, DEFAULT_PANEL_NAME)
            return self.async_create_entry(
                title=title, data=final_data_for_entry, options=final_options_for_entry
            )

        # Schema for this step, using profile defaults for panel capability limits.
        initial_options_schema_dict = {
            vol.Optional(
                CONF_POLLING_INTERVAL,
                default=step1_data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(
                CONF_SLOW_POLLING_INTERVAL,
                default=step1_data.get(CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(
                CONF_LIMIT_AREAS,
                default=step1_data.get(
                    CONF_LIMIT_AREAS, detected_limits.get(CONF_LIMIT_AREAS, int(panel_profile["max_areas"]))
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_AREAS)),
            vol.Optional(
                CONF_LIMIT_ZONES,
                default=step1_data.get(
                    CONF_LIMIT_ZONES, detected_limits.get(CONF_LIMIT_ZONES, int(panel_profile["max_zones"]))
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_ZONES)),
            vol.Optional(
                CONF_LIMIT_SCENARIOS,
                default=step1_data.get(
                    CONF_LIMIT_SCENARIOS, detected_limits.get(CONF_LIMIT_SCENARIOS, int(panel_profile["max_scenarios"]))
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_SCENARIOS)),
            vol.Optional(CONF_EVENT_LOG_SIZE, default=DEFAULT_EVENT_LOG_SIZE): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_EVENT_LOG_SIZE)
            ),
            vol.Optional(CONF_READER_NAMES, default=""): str,
        }
        if len(scenario_choices) > 1:
            initial_options_schema_dict.update(
                {
                    vol.Optional(
                        CONF_SCENARIO_ARM_HOME,
                        default=_scenario_default(detected_options, CONF_SCENARIO_ARM_HOME, scenario_choices),
                    ): vol.In(
                        scenario_choices
                    ),
                    vol.Optional(
                        CONF_SCENARIO_ARM_AWAY,
                        default=_scenario_default(detected_options, CONF_SCENARIO_ARM_AWAY, scenario_choices),
                    ): vol.In(
                        scenario_choices
                    ),
                    vol.Optional(
                        CONF_SCENARIO_ARM_NIGHT,
                        default=_scenario_default(detected_options, CONF_SCENARIO_ARM_NIGHT, scenario_choices),
                    ): vol.In(
                        scenario_choices
                    ),
                    vol.Optional(
                        CONF_SCENARIO_ARM_VACATION,
                        default=_scenario_default(detected_options, CONF_SCENARIO_ARM_VACATION, scenario_choices),
                    ): vol.In(
                        scenario_choices
                    ),
                    vol.Optional(
                        CONF_SCENARIO_DISARM,
                        default=_scenario_default(detected_options, CONF_SCENARIO_DISARM, scenario_choices),
                    ): vol.In(
                        scenario_choices
                    ),
                }
            )

        return self.async_show_form(
            step_id="initial_options",
            data_schema=vol.Schema(initial_options_schema_dict),
            errors=errors,
            description_placeholders={
                "panel_name": step1_data.get(CONF_PANEL_NAME, "Inim Panel")
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return InimAlarmOptionsFlowHandler(config_entry)


class InimAlarmOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for Inim Alarm."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.initial_panel_config = config_entry.data.get(
            DATA_INITIAL_PANEL_CONFIG, {}
        )
        self.current_pin = config_entry.data.get(CONF_PIN, "")
        self.current_panel_model = config_entry.options.get(
            CONF_PANEL_MODEL,
            config_entry.data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
        )
        self.current_settings = {**config_entry.data, **config_entry.options}
        self._pending_options: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage connection/profile options before showing profile-derived scenario mappings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = self.config_entry.data.copy()
            new_pin = user_input.get(CONF_PIN) or self.current_pin
            new_panel_model = user_input.get(CONF_PANEL_MODEL, self.current_panel_model)
            refresh_requested = bool(user_input.get(CONF_REFRESH_INITIAL_CONFIG, False))
            model_changed = new_panel_model != self.current_panel_model
            pin_changed = new_pin != self.current_pin
            stored_revision = self.config_entry.data.get(DATA_INITIAL_PANEL_CONFIG_REVISION)
            revision_stale = stored_revision != INITIAL_PANEL_CONFIG_REVISION

            if pin_changed or model_changed or refresh_requested or revision_stale:
                _LOGGER.info(
                    "Refreshing Inim initial panel config for %s: pin_changed=%s model_changed=%s refresh_requested=%s revision_stale=%s",
                    self.config_entry.title,
                    pin_changed,
                    model_changed,
                    refresh_requested,
                    revision_stale,
                )
                try:
                    refreshed_config = await _validate_connection_and_fetch_initial_config(
                        self.hass,
                        self.config_entry.data[CONF_HOST],
                        self.config_entry.data[CONF_PORT],
                        new_pin,
                        new_panel_model,
                    )
                    refreshed_config.pop("resolved_panel_model", None)
                    new_data[CONF_PIN] = new_pin
                    new_data[CONF_PANEL_MODEL] = new_panel_model
                    new_data[DATA_INITIAL_PANEL_CONFIG] = refreshed_config
                    new_data[DATA_INITIAL_PANEL_CONFIG_REVISION] = INITIAL_PANEL_CONFIG_REVISION
                    self.initial_panel_config = refreshed_config
                except ConnectionError:
                    _LOGGER.warning(
                        "Connection failed while refreshing initial config for %s",
                        self.config_entry.title,
                    )
                    errors[CONF_PIN] = "cannot_connect_new_pin"
                except ValueError as vex:
                    _LOGGER.warning(
                        "Validation error while refreshing initial config for %s: %s",
                        self.config_entry.title,
                        vex,
                    )
                    if str(vex) == "auth_failed":
                        errors[CONF_PIN] = "auth_failed_new_pin"
                    else:
                        errors[CONF_PIN] = "pin_validation_error"
                except Exception as exc:
                    _LOGGER.exception(
                        "Unexpected error refreshing initial config for %s: %s",
                        self.config_entry.title,
                        exc,
                    )
                    errors[CONF_PIN] = "unknown_pin_error"

            if not errors.get(CONF_PIN):
                if new_data != self.config_entry.data:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )
                    _LOGGER.info(
                        "Updated config entry data for %s",
                        self.config_entry.title,
                    )

                self.current_pin = new_pin
                self.current_panel_model = new_panel_model

                event_log_size_input = user_input.get(
                    CONF_EVENT_LOG_SIZE, DEFAULT_EVENT_LOG_SIZE
                )
                self._pending_options = {
                    CONF_PANEL_MODEL: new_panel_model,
                    CONF_POLLING_INTERVAL: user_input.get(CONF_POLLING_INTERVAL),
                    CONF_SLOW_POLLING_INTERVAL: user_input.get(
                        CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL
                    ),
                    CONF_LIMIT_AREAS: user_input.get(CONF_LIMIT_AREAS),
                    CONF_LIMIT_ZONES: user_input.get(CONF_LIMIT_ZONES),
                    CONF_LIMIT_SCENARIOS: user_input.get(CONF_LIMIT_SCENARIOS),
                    CONF_EVENT_LOG_SIZE: min(
                        event_log_size_input, SYSTEM_MAX_EVENT_LOG_SIZE
                    ),
                    CONF_READER_NAMES: user_input.get(CONF_READER_NAMES, ""),
                }
                self.current_settings = {
                    **new_data,
                    **self.config_entry.options,
                    **self._pending_options,
                }
                return await self.async_step_scenario_mappings()

        profile = get_panel_profile(self.current_panel_model)
        refresh_default = (
            self.config_entry.data.get(DATA_INITIAL_PANEL_CONFIG_REVISION)
            != INITIAL_PANEL_CONFIG_REVISION
        )

        options_schema_dict = {
            # Never echo the stored PIN back to the UI/API: an empty field
            # keeps the current PIN (see async_step_init).
            vol.Optional(CONF_PIN): str,
            vol.Optional(
                CONF_PANEL_MODEL,
                default=self.current_panel_model,
            ): vol.In(PANEL_MODEL_OPTIONS),
            vol.Optional(
                CONF_REFRESH_INITIAL_CONFIG,
                default=refresh_default,
            ): cv.boolean,
            vol.Optional(
                CONF_POLLING_INTERVAL,
                default=self.current_settings.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(
                CONF_SLOW_POLLING_INTERVAL,
                default=self.current_settings.get(
                    CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
            vol.Optional(
                CONF_LIMIT_AREAS,
                default=_schema_limit_default(
                    self.current_settings, CONF_LIMIT_AREAS, profile, "max_areas"
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_AREAS)),
            vol.Optional(
                CONF_LIMIT_ZONES,
                default=_schema_limit_default(
                    self.current_settings, CONF_LIMIT_ZONES, profile, "max_zones"
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_ZONES)),
            vol.Optional(
                CONF_LIMIT_SCENARIOS,
                default=_schema_limit_default(
                    self.current_settings, CONF_LIMIT_SCENARIOS, profile, "max_scenarios"
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_SCENARIOS)),
            vol.Optional(
                CONF_EVENT_LOG_SIZE,
                default=self.current_settings.get(
                    CONF_EVENT_LOG_SIZE, DEFAULT_EVENT_LOG_SIZE
                ),
            ): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=SYSTEM_MAX_EVENT_LOG_SIZE)
            ),
            vol.Optional(
                CONF_READER_NAMES,
                default=self.current_settings.get(CONF_READER_NAMES, ""),
            ): str,
        }

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(options_schema_dict), errors=errors
        )

    async def async_step_scenario_mappings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show scenario mapping choices after any requested profile/config refresh."""
        scenario_choices = _build_scenario_choices(self.initial_panel_config)
        settings = {**self.current_settings, **(self._pending_options or {})}

        if user_input is not None:
            updated_options = dict(self._pending_options or {})
            if not updated_options:
                updated_options.update(
                    {
                        CONF_PANEL_MODEL: self.current_panel_model,
                        CONF_POLLING_INTERVAL: settings.get(CONF_POLLING_INTERVAL),
                        CONF_SLOW_POLLING_INTERVAL: settings.get(
                            CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL
                        ),
                        CONF_LIMIT_AREAS: settings.get(CONF_LIMIT_AREAS),
                        CONF_LIMIT_ZONES: settings.get(CONF_LIMIT_ZONES),
                        CONF_LIMIT_SCENARIOS: settings.get(CONF_LIMIT_SCENARIOS),
                        CONF_EVENT_LOG_SIZE: settings.get(
                            CONF_EVENT_LOG_SIZE, DEFAULT_EVENT_LOG_SIZE
                        ),
                        CONF_READER_NAMES: settings.get(CONF_READER_NAMES, ""),
                    }
                )

            for key in SCENARIO_MAPPING_KEYS:
                val = user_input.get(key)
                if val == "none":
                    updated_options[key] = None
                elif val is not None:
                    try:
                        updated_options[key] = int(val)
                    except (ValueError, TypeError):
                        updated_options[key] = None

            _LOGGER.debug("Creating/updating options with: %s", updated_options)
            return self.async_create_entry(title="", data=updated_options)

        scenario_schema_dict = {}
        if len(scenario_choices) > 1:
            scenario_schema_dict.update(
                {
                    vol.Optional(
                        CONF_SCENARIO_ARM_HOME,
                        default=_scenario_default(
                            settings, CONF_SCENARIO_ARM_HOME, scenario_choices
                        ),
                    ): vol.In(scenario_choices),
                    vol.Optional(
                        CONF_SCENARIO_ARM_AWAY,
                        default=_scenario_default(
                            settings, CONF_SCENARIO_ARM_AWAY, scenario_choices
                        ),
                    ): vol.In(scenario_choices),
                    vol.Optional(
                        CONF_SCENARIO_ARM_NIGHT,
                        default=_scenario_default(
                            settings, CONF_SCENARIO_ARM_NIGHT, scenario_choices
                        ),
                    ): vol.In(scenario_choices),
                    vol.Optional(
                        CONF_SCENARIO_ARM_VACATION,
                        default=_scenario_default(
                            settings, CONF_SCENARIO_ARM_VACATION, scenario_choices
                        ),
                    ): vol.In(scenario_choices),
                    vol.Optional(
                        CONF_SCENARIO_DISARM,
                        default=_scenario_default(
                            settings, CONF_SCENARIO_DISARM, scenario_choices
                        ),
                    ): vol.In(scenario_choices),
                }
            )
        else:
            _LOGGER.info("No scenarios available to map in options flow")

        return self.async_show_form(
            step_id="scenario_mappings",
            data_schema=vol.Schema(scenario_schema_dict),
            errors={},
        )
