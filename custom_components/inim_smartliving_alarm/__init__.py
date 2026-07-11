"""The Inim Alarm integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_HOST,
    CONF_PANEL_MODEL,
    CONF_PIN,
    CONF_POLLING_INTERVAL,
    CONF_PORT,
    DATA_API_CLIENT,
    DATA_COORDINATOR,
    DATA_INITIAL_PANEL_CONFIG,
    DATA_INITIAL_PANEL_CONFIG_REVISION,
    DEFAULT_PANEL_MODEL,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    INITIAL_PANEL_CONFIG_REVISION,
    PLATFORMS,
)

# Import the custom coordinator
from .coordinator import InimDataUpdateCoordinator
from .effective_entities import build_automatic_options

# Import API
from .inim_api import InimAlarmAPI
from .panel_profiles import (
    PANEL_MODEL_10100,
    apply_panel_profile_api_patches,
    configure_api_for_panel,
)
from .smartliving_10100 import apply_smartliving_10100_precheck_fix

_LOGGER = logging.getLogger(__name__)


# SmartLiving model compatibility:
# - panel_profiles keeps the 1050-compatible layout as default and adds an
#   explicit 10100/10100L profile for larger area/zone/keyboard counts.
# - smartliving_10100 keeps the pre-check enabled but reads the full 27-byte
#   response observed on SmartLiving 10100 panels.
apply_panel_profile_api_patches()
apply_smartliving_10100_precheck_fix()

_ESSENTIAL_INITIAL_CONFIG_KEYS = (
    "system_info",
    "areas",
    "zones",
    "zones_config",
    "scenarios",
    "scenario_activations",
)


def _initial_config_is_usable(initial_config: dict[str, Any] | None) -> bool:
    """Return True when initial panel config has all essential sections."""
    if not initial_config:
        return False
    return all(initial_config.get(key) is not None for key in _ESSENTIAL_INITIAL_CONFIG_KEYS)


async def _refresh_initial_config_if_stale(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: InimAlarmAPI,
    panel_model: str,
) -> None:
    """Refresh stored static panel data when the parser/profile revision changed."""
    stored_revision = entry.data.get(DATA_INITIAL_PANEL_CONFIG_REVISION)
    if stored_revision == INITIAL_PANEL_CONFIG_REVISION and _initial_config_is_usable(
        entry.data.get(DATA_INITIAL_PANEL_CONFIG)
    ):
        return

    _LOGGER.info(
        "Refreshing stored Inim initial panel config for %s: stored_revision=%s current_revision=%s panel_model=%s",
        entry.title,
        stored_revision,
        INITIAL_PANEL_CONFIG_REVISION,
        panel_model,
    )

    try:
        refreshed_config = await hass.async_add_executor_job(
            api.get_initial_panel_configuration
        )
    except Exception as exc:  # Keep the old config if refresh fails at startup.
        _LOGGER.warning(
            "Could not refresh initial panel config for %s; keeping stored config: %s",
            entry.title,
            exc,
        )
        return

    if not _initial_config_is_usable(refreshed_config):
        _LOGGER.warning(
            "Initial panel config refresh for %s returned incomplete data; keeping stored config",
            entry.title,
        )
        return

    new_data = {
        **entry.data,
        CONF_PANEL_MODEL: panel_model,
        DATA_INITIAL_PANEL_CONFIG: refreshed_config,
        DATA_INITIAL_PANEL_CONFIG_REVISION: INITIAL_PANEL_CONFIG_REVISION,
    }
    hass.config_entries.async_update_entry(entry, data=new_data)
    _LOGGER.info("Stored Inim initial panel config refreshed for %s", entry.title)


def _apply_automatic_10100_runtime_options(
    entry: ConfigEntry, panel_model: str
) -> dict[str, Any] | None:
    """Apply derived 10100 limits and mappings to the active config entry.

    Derived values are runtime state, not user preferences. Updating the active
    options mapping directly makes every platform see the effective values in
    the same setup pass and avoids depending on config-entry storage timing.
    Existing manual scenario mappings remain authoritative.
    """
    if panel_model != PANEL_MODEL_10100:
        return None

    initial_panel_config = entry.data.get(DATA_INITIAL_PANEL_CONFIG, {})
    if not _initial_config_is_usable(initial_panel_config):
        _LOGGER.warning(
            "Cannot derive automatic SmartLiving 10100 runtime options for %s: initial config is incomplete",
            entry.title,
        )
        return None

    current_options = dict(entry.options)
    runtime_options, summary = build_automatic_options(
        initial_panel_config, current_options
    )

    # ConfigEntry.options is a mutable mapping in Home Assistant. Keep derived
    # limits runtime-only: they are recalculated on every setup from panel data.
    # This also makes stale saved limits harmless (for example a historical 34
    # when the last programmed zone is currently Z032).
    entry.options.clear()
    entry.options.update(runtime_options)

    if runtime_options != current_options:
        _LOGGER.warning(
            "Applied runtime SmartLiving 10100 import values for %s: %s",
            entry.title,
            summary,
        )
    else:
        _LOGGER.debug(
            "Runtime SmartLiving 10100 import values already current for %s: %s",
            entry.title,
            summary,
        )

    return summary


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Inim Alarm from a config entry."""
    _LOGGER.info(
        "Setting up Inim Alarm integration for entry: %s (%s)",
        entry.title,
        entry.entry_id,
    )

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    pin = entry.data[CONF_PIN]
    panel_model = entry.options.get(
        CONF_PANEL_MODEL, entry.data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL)
    )

    # Polling interval from options (if user changed it) or from initial data
    polling_interval = entry.options.get(
        CONF_POLLING_INTERVAL,
        entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
    )

    api = InimAlarmAPI(host=host, port=port, pin_code_str=pin)
    configure_api_for_panel(api, panel_model)

    # Refresh static config before platforms are created if parser/profile offsets changed.
    await _refresh_initial_config_if_stale(hass, entry, api, panel_model)

    # SmartLiving 10100/10100L imports are derived from programmed names. Apply
    # them to the active entry before platforms read entry.options. Saved legacy
    # limits remain untouched and are ignored at runtime.
    _apply_automatic_10100_runtime_options(entry, panel_model)

    # Create the custom coordinator instance
    coordinator_name = f"{DOMAIN} data ({entry.title})"
    coordinator = InimDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        api_client=api,
        name=coordinator_name,
        update_interval_seconds=polling_interval,
    )

    # Fetch initial data to ensure coordinator has data before entities are set up.
    # This also serves as a connection test on startup for the coordinator's update loop.
    _LOGGER.debug(
        "(%s) Performing initial data refresh for coordinator...", entry.title
    )
    await coordinator.async_config_entry_first_refresh()

    # Check if the first refresh failed critically (e.g., connection error, auth error handled by coordinator)
    if not coordinator.last_update_success:
        _LOGGER.error(
            "(%s) Initial data fetch failed. Integration setup will be retried.",
            entry.title,
        )
        # ConfigEntryNotReady tells HA to retry setup later.
        # The specific error (ConnectionError, AuthError) would have been logged by the coordinator.
        raise ConfigEntryNotReady(
            f"Failed to fetch initial data from Inim panel at {host}:{port}"
        )

    # Store the API instance and coordinator in hass.data for platforms to access.
    # Platforms will also access static config from entry.data (set by config_flow).
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_API_CLIENT: api,
        DATA_COORDINATOR: coordinator,
        # Static config like scenario names, zone types, etc., is in entry.data
        # (e.g., entry.data[DATA_INITIAL_PANEL_CONFIG])
    }

    # Set up platforms (alarm_control_panel, binary_sensor, switch, button, sensor)
    _LOGGER.debug("(%s) Forwarding setup to platforms: %s", entry.title, PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for option updates (e.g., if user changes polling interval via UI)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.info("Inim Alarm integration for %s set up successfully.", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Inim Alarm integration for %s", entry.title)
    # This is called when an integration entry is removed from HA or HA is shutting down.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Clean up data stored in hass.data
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
            _LOGGER.debug("Cleaned up data for %s", entry.title)
        if not hass.data[DOMAIN]:  # If no more entries for this domain
            hass.data.pop(DOMAIN)
            _LOGGER.debug("Cleaned up domain data for %s", DOMAIN)
    else:
        _LOGGER.error("Failed to unload platforms for %s", entry.title)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Checking migration for Inim Alarm config entry version %s",
        config_entry.version,
    )
    # Add migration logic if config entry version changes in the future.
    # For now, assuming version 1 is the current version and requires no migration.
    if config_entry.version == 1:
        # No migration needed from version 1 to 1
        return True

    _LOGGER.error(
        "Unsupported Inim Alarm config entry version for migration: %s",
        config_entry.version,
    )
    return False  # Return False if migration fails or is not supported


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.info(
        "Inim Alarm configuration options updated for %s, reloading entry to apply changes.",
        entry.title,
    )
    # This is called when options (e.g., polling interval, scenario mappings) are changed via UI.
    # Reload the entry to apply the new options.
    await hass.config_entries.async_reload(entry.entry_id)
