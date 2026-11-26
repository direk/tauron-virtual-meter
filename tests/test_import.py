"""Offline adapter tests with explicit HA/aiohttp doubles, not a HA runtime test."""
import asyncio
from contextlib import ExitStack
from datetime import date
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).parents[1] / "custom_components/tauron_virtual_meter"


class FakeStore:
    def __init__(self, *args):
        self.saved = None

    async def async_save(self, data):
        self.saved = data


class FakeCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass

    def async_set_updated_data(self, data):
        self.data = data

    def async_update_listeners(self):
        self.listeners_updated = True


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        package = types.ModuleType("test_tauron_adapter")
        package.__path__ = [str(ROOT)]
        modules = {"test_tauron_adapter": package}
        for name in ("aiohttp", "homeassistant", "homeassistant.exceptions",
                     "homeassistant.helpers", "homeassistant.helpers.storage",
                     "homeassistant.helpers.update_coordinator"):
            modules[name] = types.ModuleType(name)
        modules["aiohttp"].ClientSession = object
        modules["aiohttp"].ClientTimeout = lambda **kwargs: kwargs
        modules["aiohttp"].ClientError = type("ClientError", (Exception,), {})
        modules["homeassistant.exceptions"].ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
        modules["homeassistant.helpers.storage"].Store = FakeStore
        modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = FakeCoordinator
        modules["homeassistant.helpers.update_coordinator"].UpdateFailed = type("UpdateFailed", (Exception,), {})
        self.context.enter_context(patch.dict(sys.modules, modules))
        self.api_module = importlib.import_module("test_tauron_adapter.api")
        self.module = importlib.import_module("test_tauron_adapter.coordinator")
        # Remove adapter submodules too; subsequent cases receive fresh doubles.
        self.addCleanup(lambda: [sys.modules.pop(key, None) for key in list(sys.modules)
                                 if key.startswith("test_tauron_adapter.")])
        self.entry = types.SimpleNamespace(options={"history_start": "2026-11-20"},
            entry_id="test", data={"username": "name", "password": "secret", "meter_id": "123"})
        self.coordinator = self.module.MeterCoordinator(types.SimpleNamespace(), self.entry, object())
        self.coordinator.archive = {"profiles": {"consum": {}, "oze": {}}, "issues": {},
                                    "cursor": "2026-11-20", "complete": False}

    async def test_history_checkpoint_and_complete(self):
        meter = self.coordinator
        meter.api = types.SimpleNamespace(select=AsyncMock(), readings=AsyncMock(return_value={"data": []}))
        meter.download_day = AsyncMock()
        meter.raw_save = AsyncMock()
        meter.export = AsyncMock()
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            await meter.history_tick()
        meter.download_day.assert_awaited_once_with(date(2026, 11, 20))
        self.assertEqual(meter.archive["cursor"], "2026-11-19")
        self.assertTrue(meter.archive["complete"])
        meter.export.assert_awaited_once()

    async def test_failed_day_is_retried_without_advancing(self):
        meter = self.coordinator
        meter.api = types.SimpleNamespace(select=AsyncMock())
        meter.download_day = AsyncMock(side_effect=self.api_module.ApiError("offline"))
        await meter.history_tick()
        self.assertEqual(meter.archive["cursor"], "2026-11-20")
        self.assertFalse(meter.archive["complete"])
        self.assertIsNotNone(meter._retry_after)
        self.assertEqual(meter.archive["last_history_error"], "offline")
        self.assertEqual(meter.archive["history_retry_after"], meter._retry_after.isoformat())
        self.assertTrue(meter.listeners_updated)
        self.assertIsNotNone(meter.store.saved["last_history_attempt"])

    async def test_partial_update_keeps_prior_readings_and_flags_issue(self):
        meter = self.coordinator
        day = date(2026, 11, 20)
        stamp = "2026-11-19T23:00:00+00:00"
        meter.archive["profiles"]["consum"][day.isoformat()] = {stamp: "0.7"}
        meter.api = types.SimpleNamespace(profile=AsyncMock(return_value={"data": {"allData": []}}))
        meter.raw_save = AsyncMock()
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            await meter.download_day(day)
        self.assertEqual(meter.archive["profiles"]["consum"][day.isoformat()][stamp], "0.7")
        self.assertIn("2026-11-20.consum", meter.archive["issues"])

    async def test_raw_unknown_profiles_are_archived(self):
        meter = self.coordinator
        raw = {"data": {"values": [1] * 96, "extra": "retain"}}
        meter.api = types.SimpleNamespace(profile=AsyncMock(return_value=raw))
        meter.raw_save = AsyncMock()
        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
            await meter.download_day(date(2026, 11, 20))
        self.assertEqual(meter.raw_save.await_args_list[0].args[1], raw)
        self.assertEqual(len(meter.archive["issues"]), 2)

    async def test_login_rejects_unexpected_credential_destination(self):
        api = self.api_module.TauronAPI(object(), "user", "secret")
        api._text = AsyncMock(side_effect=[
            ("login", "https://elicznik.tauron-dystrybucja.pl"),
            ('<form action="https://example.org/collect" id="kc-form-login">', "https://logowanie.tauron-dystrybucja.pl/login")
        ])
        with self.assertRaises(self.api_module.ApiError):
            await api.login()
        self.assertEqual(api._text.await_count, 2)

    async def test_success_false_is_not_an_empty_day(self):
        api = self.api_module.TauronAPI(object(), "user", "secret")
        api._text = AsyncMock(return_value=('{"success":false}', "https://elicznik.tauron-dystrybucja.pl/energia/api"))
        with self.assertRaises(self.api_module.ApiError):
            await api.profile(date(2026, 11, 20), date(2026, 11, 20))

    def make_sensor(self):
        modules = {}
        for name in ("homeassistant.components", "homeassistant.components.recorder",
                     "homeassistant.components.recorder.models", "homeassistant.components.recorder.statistics",
                     "homeassistant.components.sensor", "homeassistant.const", "homeassistant.helpers.entity"):
            modules[name] = types.ModuleType(name)
        imports = []
        modules["homeassistant.components.recorder.models"].StatisticMeanType = types.SimpleNamespace(NONE=0)
        modules["homeassistant.components.recorder.statistics"].async_import_statistics = lambda *args: imports.append(args)
        modules["homeassistant.components.sensor"].SensorDeviceClass = types.SimpleNamespace(ENERGY="energy")
        modules["homeassistant.components.sensor"].SensorEntity = type("SensorEntity", (), {})
        modules["homeassistant.const"].UnitOfEnergy = types.SimpleNamespace(KILO_WATT_HOUR="kWh")
        modules["homeassistant.helpers.entity"].DeviceInfo = lambda **kwargs: kwargs
        self.context.enter_context(patch.dict(sys.modules, modules))
        sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = type("CoordinatorEntity", (), {})
        sensor_module = importlib.import_module("test_tauron_adapter.sensor")
        sensor = sensor_module.VirtualMeter.__new__(sensor_module.VirtualMeter)
        sensor.coordinator = self.coordinator
        sensor.direction = "consum"
        sensor.hass = object()
        sensor.name = "Counter"
        sensor.entity_id = "sensor.my_virtual_meter"
        sensor.async_write_ha_state = lambda: None
        self.coordinator.archive["complete"] = True
        self.coordinator.statistics = AsyncMock(return_value=[{
            "start": self.module.datetime(2026, 11, 20, tzinfo=self.module.timezone.utc),
            "state": 2.5, "sum": 2.5,
        }])
        return sensor, imports

    async def test_statistics_are_owned_by_sensor_not_external_source(self):
        sensor, imports = self.make_sensor()
        await sensor.import_statistics()
        metadata, rows = imports[0][1:]
        self.assertEqual(metadata["statistic_id"], "sensor.my_virtual_meter")
        self.assertEqual(metadata["source"], "recorder")
        self.assertIsNone(sensor._attr_state_class)
        self.assertEqual([row["sum"] for row in rows], [0.0, 2.5])
        self.assertEqual(sensor._attr_native_value, 2.5)

    async def test_sensor_shows_partial_value_without_waiting_for_history(self):
        sensor, imports = self.make_sensor()
        self.coordinator.archive["complete"] = False
        await sensor.import_statistics()
        self.assertEqual(sensor._attr_native_value, 2.5)
        self.assertEqual(imports, [])
        self.assertTrue(sensor.extra_state_attributes["value_is_partial"])
        self.assertEqual(sensor.extra_state_attributes["history_days_remaining"], 1)

    async def test_partial_archive_is_exported_to_sensors(self):
        self.coordinator.archive["complete"] = False
        exporter = AsyncMock()
        self.coordinator.exporters.append(exporter)
        await self.coordinator.export()
        exporter.assert_awaited_once()

    async def test_empty_archive_does_not_invent_zero(self):
        sensor, imports = self.make_sensor()
        sensor._attr_native_value = None
        self.coordinator.archive["complete"] = False
        self.coordinator.statistics = AsyncMock(return_value=[])
        await sensor.import_statistics()
        self.assertIsNone(sensor._attr_native_value)
        self.assertEqual(imports, [])

    async def test_failed_history_reports_error_and_preserves_partial_values(self):
        meter = self.coordinator
        meter.api = types.SimpleNamespace(select=AsyncMock())
        meter.download_day = AsyncMock(side_effect=self.api_module.ApiError("offline"))
        exporter = AsyncMock()
        meter.exporters.append(exporter)
        await meter.history_tick()
        exporter.assert_awaited_once()
        self.assertTrue(meter.listeners_updated)

    async def test_recover_cached_date_errors_on_load_without_redownloading(self):
        meter = self.coordinator
        meter.archive["issues"] = {
            "2026-11-20.consum": "Response contains a different date",
            "2026-11-20.oze": "Response contains a different date",
            "2026-11-19.oze": "Unknown profile resolution or ambiguous DST day",
        }
        meter.store.async_load = AsyncMock(return_value=meter.archive)
        meter.api.profile = AsyncMock()
        raw = {"data": {"allData": [{"Date": "1999-01-01", "Hour": "1", "EC": "0.45", "Status": "0"}]}}
        stored = types.SimpleNamespace(async_load=AsyncMock(return_value=raw))
        with patch.object(self.module, "Store", return_value=stored):
            await meter.load()
            await meter.repair_cached_dates()
        meter.api.profile.assert_not_awaited()
        self.assertEqual(stored.async_load.await_count, 2)
        self.assertEqual(meter.archive["recovered_profile_count"], 2)
        self.assertEqual(len(meter.archive["profiles"]["consum"]["2026-11-20"]), 1)
        self.assertEqual(len(meter.archive["profiles"]["oze"]["2026-11-20"]), 1)
        self.assertEqual(meter.archive["cursor"], "2026-11-20")
        self.assertEqual(list(meter.archive["issues"]), ["2026-11-19.oze"])
        self.assertEqual(raw["data"]["allData"][0]["Date"], "1999-01-01")

    async def test_cached_date_repair_keeps_newly_detected_profile_errors(self):
        meter = self.coordinator
        meter.archive["issues"]["2026-11-20.consum"] = "Response contains a different date"
        raw = {"data": {"allData": [{"Date": "wrong", "Hour": "bad", "EC": "1"}]}}
        with patch.object(self.module, "Store", return_value=types.SimpleNamespace(async_load=AsyncMock(return_value=raw))):
            await meter.repair_cached_dates()
        self.assertEqual(meter.archive["issues"]["2026-11-20.consum"], "Unrecognized hour labels")
        self.assertEqual(meter.archive["profiles"]["consum"], {})

    async def test_missing_cached_file_preserves_error_and_progress(self):
        meter = self.coordinator
        meter.archive["issues"]["2026-11-20.consum"] = "Response contains a different date"
        with patch.object(self.module, "Store", return_value=types.SimpleNamespace(async_load=AsyncMock(return_value=None))):
            await meter.repair_cached_dates()
        self.assertEqual(meter.archive["issues"]["2026-11-20.consum"], "Response contains a different date")
        self.assertEqual(meter.archive["cursor"], "2026-11-20")


if __name__ == "__main__":
    unittest.main()
