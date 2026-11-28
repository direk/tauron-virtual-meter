"""A virtual counter with imported statistics owned by the sensor entity."""
from datetime import date, timedelta
import logging

from homeassistant.components.recorder import is_entity_recorded
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([VirtualMeter(entry, direction) for direction in ("consum", "oze")])


class VirtualMeter(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # A supported class is safe only after Recorder excludes automatic samples.
    # Otherwise delayed readings would be compiled under their download time.
    _attr_state_class = None
    _attr_suggested_display_precision = 3

    def __init__(self, entry, direction):
        super().__init__(entry.runtime_data)
        self.direction = direction
        self._attr_unique_id = f"{entry.data['meter_id']}_{direction}"
        self._attr_name = "Energia pobrana" if direction == "consum" else "Energia oddana"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["meter_id"])}, name=f"{NAME} {entry.data['meter_id']}",
            manufacturer="Tauron", model="Wirtualny licznik eLicznik",
        )
        self._attr_native_value = None
        self._downloaded_energy_value = None
        self._last_measurement = None
        self._first_measurement = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.exporters.append(self.import_statistics)
        self.async_on_remove(lambda: self.coordinator.exporters.remove(self.import_statistics))
        await self.import_statistics()

    async def import_statistics(self):
        self._configure_statistics()
        stats = await self.coordinator.statistics(self.direction)
        if not stats:
            return
        # Backfill changes the sum of downloaded data without representing
        # new consumption. Expose progress as an attribute, never as changes
        # to the main counter recorded at the time of the download.
        self._downloaded_energy_value = stats[-1]["state"]
        self._last_measurement = (stats[-1]["start"] + timedelta(hours=1)).isoformat()
        self._first_measurement = stats[0]["start"].isoformat()
        if not self.coordinator.archive.get("complete"):
            self.async_write_ha_state()
            return
        self._attr_native_value = stats[-1]["state"]
        self.async_write_ha_state()
        metadata = {
            "statistic_id": self.entity_id, "source": "recorder",
            "name": self.name, "has_sum": True,
            "mean_type": StatisticMeanType.NONE, "unit_class": "energy",
            "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        }
        # The baseline is synthetic, not a measured value; it preserves the
        # first interval in difference-based charts.
        baseline = {"start": stats[0]["start"] - timedelta(hours=1), "state": 0.0, "sum": 0.0}
        rows = [baseline, *stats]
        for offset in range(0, len(rows), 1000):
            async_import_statistics(self.hass, metadata, rows[offset:offset + 1000])
        return {"entity_id": self.entity_id, "last": stats[-1]}

    def _configure_statistics(self):
        excluded = not is_entity_recorded(self.hass, self.entity_id)
        self._attr_state_class = SensorStateClass.TOTAL if excluded else None
        self._recorder_exclusion_required = not excluded
        if not excluded and not getattr(self, "_recorder_warning_logged", False):
            _LOGGER.warning(
                "%s must be excluded in recorder.exclude.entities and Home Assistant "
                "restarted to enable state_class without counting delayed readings "
                "at download time. Keep imported statistics; do not delete them. "
                "See the integration README: Historia tej samej encji",
                self.entity_id,
            )
        self._recorder_warning_logged = not excluded

    @property
    def extra_state_attributes(self):
        archive = self.coordinator.archive
        profiles = archive["profiles"][self.direction]
        issues = archive["issues"]
        reading_issues = archive.get("reading_issues", {})
        skipped = archive.get("history_skipped_months", {})
        availability = archive.get("availability_months", {})
        last_month = next(reversed(availability), None)
        sync_issues = archive.get("sync_issues", {})
        last_sync_issue = next(reversed(sync_issues.values()), {})
        remaining = max(0, (self.coordinator.history_cursor - self.coordinator.history_start).days + 1)
        return {
            "history_scan_complete": archive.get("complete", False),
            "history_scan_next_day": archive["cursor"],
            "history_start": self.coordinator.history_start.isoformat(),
            "last_successful_sync": archive.get("last_sync"),
            "last_sync_attempt": archive.get("last_sync_attempt"),
            "last_sync_error": archive.get("last_sync_error"),
            "api_retry_after": self.coordinator.api_retry_after.isoformat() if self.coordinator.api_retry_after else None,
            "last_sync_request": archive.get("last_sync_request"),
            "sync_issue_count": len(sync_issues),
            "last_sync_issue_request": last_sync_issue.get("request"),
            "last_sync_issue": last_sync_issue.get("reason"),
            "last_measurement_end": self._last_measurement,
            "profile_issue_count": len(archive["issues"]),
            "value_is_partial": not archive.get("complete", False),
            "history_days_remaining": remaining,
            "downloaded_interval_count": sum(len(values) for values in profiles.values()),
            "empty_profile_day_count": sum(not values for values in profiles.values()),
            "first_available_measurement": getattr(self, "_first_measurement", None),
            "history_discovery_enabled": self.coordinator.entry.options.get("auto_detect_history", True),
            "history_skipped_month_count": len(skipped),
            "history_skipped_day_count": sum(
                (date.fromisoformat(item["to"]) - date.fromisoformat(item["from"])).days + 1
                for item in skipped.values()
            ),
            "last_availability_month": last_month,
            "last_availability_result": availability.get(last_month) if last_month else None,
            "downloaded_energy_kwh": getattr(self, "_downloaded_energy_value", None),
            "recovered_profile_count": archive.get("recovered_profile_count", 0),
            "last_history_attempt": archive.get("last_history_attempt"),
            "last_history_error": archive.get("last_history_error"),
            "history_retry_after": archive.get("history_retry_after"),
            "history_retry_kind": archive.get("history_retry_kind"),
            "last_profile_issue": next(reversed(issues.values()), None),
            "last_profile_issue_key": next(reversed(issues), None),
            "last_history_request": archive.get("last_history_request"),
            "last_api_error_request": archive.get("last_api_error_request"),
            "last_api_response_summary": archive.get("last_api_response_summary"),
            "reading_issue_count": len(reading_issues),
            "last_reading_issue_key": next(reversed(reading_issues), None),
            "last_reading_issue": next(reversed(reading_issues.values()), None),
            "auto_clean_state_history": self.coordinator.entry.options.get("auto_clean_state_history", False),
            "state_history_cleanup_last_requested": archive.get("state_history_cleanup_last_requested"),
            "state_history_cleanup_error": archive.get("state_history_cleanup_error"),
            "recorder_exclusion_required": getattr(self, "_recorder_exclusion_required", True),
            "counter_origin": "zero_before_first_available_interval",
        }
