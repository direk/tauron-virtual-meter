"""Guards around optional cleanup, with mocked Recorder and no live deletion."""
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

path = Path(__file__).parents[1] / "custom_components/tauron_virtual_meter/history.py"
spec = importlib.util.spec_from_file_location("history_cleanup_model", path)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        self.expected = {"start": datetime(2026, 11, 26, tzinfo=timezone.utc), "state": 100.5, "sum": 100.5}
        self.rows = {"sensor.test_meter": [dict(self.expected)]}
        self.events = []

        async def committed():
            self.events.append("committed")

        def read(*args):
            self.events.append("checked")
            return self.rows

        async def job(func, *args):
            return func(*args)

        async def service(*args, **kwargs):
            self.events.append("cleanup_requested")

        self.recorder = types.SimpleNamespace(async_block_till_done=AsyncMock(side_effect=committed),
                                               async_add_executor_job=AsyncMock(side_effect=job))
        self.hass = types.SimpleNamespace(services=types.SimpleNamespace(async_call=AsyncMock(side_effect=service)))
        modules = {name: types.ModuleType(name) for name in (
            "homeassistant", "homeassistant.components", "homeassistant.components.recorder",
            "homeassistant.components.recorder.statistics")}
        modules["homeassistant.components.recorder"].get_instance = lambda hass: self.recorder
        modules["homeassistant.components.recorder.statistics"].get_last_statistics = read
        self.context.enter_context(patch.dict(sys.modules, modules))

    async def test_only_exact_counter_id_is_purged_after_commit_and_verification(self):
        result = await model.async_clean_state_history(self.hass, {"sensor.test_meter": self.expected})
        self.assertTrue(result)
        self.assertEqual(self.events, ["committed", "checked", "cleanup_requested"])
        self.hass.services.async_call.assert_awaited_once_with(
            "recorder", "purge_entities", {"entity_id": ["sensor.test_meter"], "keep_days": 0}, blocking=True)

    async def test_mismatch_does_not_purge_any_states(self):
        for field, value in (("sum", 99), ("state", 99), ("start", 0)):
            self.rows["sensor.test_meter"] = [{**self.expected, field: value}]
            self.assertFalse(await model.async_clean_state_history(self.hass, {"sensor.test_meter": self.expected}))
        self.hass.services.async_call.assert_not_awaited()

    async def test_missing_statistics_does_not_purge(self):
        self.rows = {}
        self.assertFalse(await model.async_clean_state_history(self.hass, {"sensor.test_meter": self.expected}))
        self.hass.services.async_call.assert_not_awaited()

    async def test_commit_failure_does_not_purge(self):
        self.recorder.async_block_till_done.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            await model.async_clean_state_history(self.hass, {"sensor.test_meter": self.expected})
        self.hass.services.async_call.assert_not_awaited()

    async def test_empty_or_non_sensor_targets_do_not_purge(self):
        self.assertFalse(await model.async_clean_state_history(self.hass, {}))
        self.assertFalse(await model.async_clean_state_history(self.hass, {"switch.other": self.expected}))
        self.assertFalse(await model.async_clean_state_history(self.hass, {"sensor.*": self.expected}))
        self.hass.services.async_call.assert_not_awaited()

    async def test_timestamp_and_missing_values_validation(self):
        stored = {**self.expected, "start": self.expected["start"].timestamp()}
        self.assertTrue(model.matches_import(stored, self.expected))
        self.assertFalse(model.matches_import({**stored, "sum": None}, self.expected))
        self.assertFalse(model.matches_import({**stored, "state": "NaN"}, self.expected))
