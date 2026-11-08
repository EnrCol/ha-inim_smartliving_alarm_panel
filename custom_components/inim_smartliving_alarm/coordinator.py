"""DataUpdateCoordinator for the Inim Alarm integration."""

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EVENT_LOG_SIZE,
    CONF_SLOW_POLLING_INTERVAL,
    DEFAULT_EVENT_LOG_SIZE,
    DEFAULT_SLOW_POLLING_INTERVAL,
    KEY_LATEST_EVENT_INDEX_VAL,
    KEY_PROCESSED_EVENTS,
)
from .inim_api import InimAlarmAPI

KEEP_ALIVE_MAX_INTERVAL = 10  # seconds
SLOW_STATUS_KEYS = ("zones_excluded_status", "zones_triggered_status")

_LOGGER = logging.getLogger(__name__)


class InimDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages fetching data from the Inim alarm panel."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api_client: InimAlarmAPI,
        name: str,
        update_interval_seconds: int,
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        self.panel_host_port = f"{api_client.host}:{api_client.port}"
        self._last_known_event_index_val: int | None = None
        self.config_entry = entry
        # The panel drops idle connections after 15-30 s: keep the connection
        # open between cycles only when polling is comfortably faster.
        self._keep_alive = update_interval_seconds <= KEEP_ALIVE_MAX_INTERVAL
        api_client.keep_connection_open = self._keep_alive
        # Light cycles read zones/areas/scenario; a full cycle also reads
        # exclusions, zone alarm memory and events, at most this often.
        self._slow_interval = entry.options.get(
            CONF_SLOW_POLLING_INTERVAL, DEFAULT_SLOW_POLLING_INTERVAL
        )
        self._last_full_read: float | None = None
        self._force_full_read = True
        self._slow_data: dict[str, Any] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        _LOGGER.info(
            "InimDataUpdateCoordinator initialized for %s with update interval %ss",
            self.name,
            update_interval_seconds,
        )

    async def async_request_refresh(self) -> None:
        """Refresh after a user command: read everything, exclusions included."""
        self._force_full_read = True
        await super().async_request_refresh()

    def _full_read_due(self) -> bool:
        if self._force_full_read or self._last_full_read is None:
            return True
        # Small margin so a 5 s slow interval is not pushed to 6 s by jitter.
        return time.monotonic() - self._last_full_read >= self._slow_interval - 0.5

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Inim Alarm panel using the API."""
        current_data: dict[str, Any] = {}
        full = self._full_read_due()

        try:
            event_fetch_count_config = self.config_entry.options.get(
                CONF_EVENT_LOG_SIZE, DEFAULT_EVENT_LOG_SIZE
            )
            api_call_count_param: int | None = None
            api_call_last_index_param: int | None = self._last_known_event_index_val
            if full and self._last_known_event_index_val is None:
                # First run after startup/reload: fetch a backlog of recent events.
                api_call_count_param = event_fetch_count_config
                api_call_last_index_param = None
                _LOGGER.info(
                    "First event poll for %s, requesting up to %s recent events",
                    self.name,
                    api_call_count_param,
                )

            # Status and events share one TCP connection: a second connection
            # right after the first costs ~2 s on the SmartLAN interface.
            status_data = await self.hass.async_add_executor_job(
                lambda: self.api_client.execute_poll_cycle(
                    count=api_call_count_param,
                    last_processed_compact_event_index_val=api_call_last_index_param,
                    keep_alive=self._keep_alive,
                    full=full,
                )
            )

            if status_data is None:
                raise UpdateFailed(
                    f"Failed to get live status snapshot from Inim panel at {self.panel_host_port} (API returned None)"
                )
            if status_data.get("error") == "Connection failure":
                raise UpdateFailed(
                    f"Failed to connect to Inim panel at {self.panel_host_port} for live update"
                )
            if status_data.get("errors"):
                _LOGGER.warning(
                    "(%s) Errors during live status update: %s",
                    self.name,
                    status_data["errors"],
                )

            event_result = status_data.pop("events_result", None)
            if full:
                if not status_data.get("errors"):
                    self._last_full_read = time.monotonic()
                    self._force_full_read = False
                self._slow_data = {
                    key: status_data.get(key)
                    for key in SLOW_STATUS_KEYS
                }
            else:
                # Keep the last exclusion / alarm-memory values between full reads.
                status_data.update(self._slow_data)
            current_data.update(status_data)

            newly_fetched_events_raw: list[dict[str, Any]] = []
            panel_latest_index: int | None = None

            if event_result:
                newly_fetched_events_raw = event_result.get("events", [])
                panel_latest_index = event_result.get("latest_event_index_val")

                if newly_fetched_events_raw:
                    _LOGGER.info(
                        "Fetched %s new compact events for %s",
                        len(newly_fetched_events_raw),
                        self.name,
                    )

                if panel_latest_index is not None:
                    # Always update to the panel's current head.
                    # The sensor will decide which of these newly_fetched_events to add to its internal log.
                    self._last_known_event_index_val = panel_latest_index

            current_data[KEY_PROCESSED_EVENTS] = (
                newly_fetched_events_raw  # Raw events from THIS poll
            )
            current_data[KEY_LATEST_EVENT_INDEX_VAL] = (
                self._last_known_event_index_val
            )  # Panel's absolute latest event index

            return current_data

        except ConfigEntryAuthFailed as auth_err:
            _LOGGER.error("(%s) Authentication failed: %s", self.name, auth_err)
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {auth_err}"
            ) from auth_err
        except UpdateFailed as uf_err:
            _LOGGER.warning(
                "(%s) UpdateFailed during data fetch: %s", self.name, uf_err
            )
            raise
        except Exception as err:
            _LOGGER.error(
                "(%s) Unexpected error fetching data: %s", self.name, err, exc_info=True
            )
            raise UpdateFailed(
                f"Error communicating with API for {self.panel_host_port}: {err}"
            ) from err
