"""A virtual counter with imported statistics owned by the sensor entity."""
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([VirtualMeter(entry, direction) for direction in ("consum", "oze")])


class VirtualMeter(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # Deliberately no state_class: Recorder must not create a second stream
    # that counts delayed data as consumption at its download time.
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
        self._last_measurement = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.exporters.append(self.import_statistics)
        self.async_on_remove(lambda: self.coordinator.exporters.remove(self.import_statistics))
        await self.import_statistics()

    async def import_statistics(self):
        if not self.coordinator.archive.get("complete"):
            return
        stats = await self.coordinator.statistics(self.direction)
        if not stats:
            return
        metadata = {
            "statistic_id": self.entity_id, "source": "recorder",
            "name": self.name, "has_sum": True,
            "mean_type": StatisticMeanType.NONE, "unit_class": "energy",
            "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        }
        # The baseline is synthetic, not a measured value; it preserves the
        # first interval in difference-based charts.
        from datetime import timedelta
        baseline = {"start": stats[0]["start"] - timedelta(hours=1), "state": 0.0, "sum": 0.0}
        rows = [baseline, *stats]
        for offset in range(0, len(rows), 1000):
            async_import_statistics(self.hass, metadata, rows[offset:offset + 1000])
        self._attr_native_value = stats[-1]["state"]
        self._last_measurement = (stats[-1]["start"] + timedelta(hours=1)).isoformat()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        archive = self.coordinator.archive
        return {
            "history_scan_complete": archive.get("complete", False),
            "history_scan_next_day": archive["cursor"],
            "history_start": self.coordinator.history_start.isoformat(),
            "last_successful_sync": archive.get("last_sync"),
            "last_measurement_end": self._last_measurement,
            "profile_issue_count": len(archive["issues"]),
            "counter_origin": "zero_before_first_available_interval",
        }
