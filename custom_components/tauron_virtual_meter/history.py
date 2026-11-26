"""Optional cleanup of download-time states after verified hourly imports."""
import asyncio
from datetime import datetime
from math import isclose
import re


def matches_import(stored, expected):
    """Check the committed endpoint before requesting any state cleanup."""
    try:
        start = stored["start"]
        stamp = start.timestamp() if isinstance(start, datetime) else float(start)
        return (
            abs(stamp - expected["start"].timestamp()) < 0.001
            and isclose(float(stored["state"]), expected["state"], abs_tol=0.000001, rel_tol=1e-10)
            and isclose(float(stored["sum"]), expected["sum"], abs_tol=0.000001, rel_tol=1e-10)
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


async def async_clean_state_history(hass, imported):
    """Use the native Recorder action, never direct SQL or statistics deletion.

    Called only for IDs returned by this integration's sensor exporters, when
    its explicit cleanup option is enabled and HA has completed startup.
    """
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import get_last_statistics

    if not imported:
        return False
    recorder = get_instance(hass)
    async with asyncio.timeout(60):
        await recorder.async_block_till_done()
        for entity_id, expected in imported.items():
            if not re.fullmatch(r"sensor\.[a-z0-9_]+", entity_id):
                return False
            rows = await recorder.async_add_executor_job(
                get_last_statistics, hass, 1, entity_id, True, {"state", "sum"}
            )
            values = rows.get(entity_id, [])
            if not values or not matches_import(values[0], expected):
                return False
        await hass.services.async_call(
            "recorder", "purge_entities",
            {"entity_id": sorted(imported), "keep_days": 0}, blocking=True,
        )
    return True  # The native service queued cleanup; it finishes asynchronously.
