"""Tauron Virtual Meter setup."""
import asyncio
from datetime import timedelta

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .coordinator import MeterCoordinator


async def async_setup_entry(hass, entry):
    # HA-managed, separate cookie jar for each meter/account.
    session = async_create_clientsession(hass)
    coordinator = MeterCoordinator(hass, entry, session)
    try:
        await coordinator.load()
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await session.close()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    if entry.options.get("auto_clean_state_history", False):
        from homeassistant.helpers.start import async_at_started

        async def clean_after_start(_hass):
            # Recorder must be able to commit queued statistics; waiting for
            # it inside integration startup would hold up HA's startup itself.
            coordinator._startup_cleanup_task = asyncio.current_task()
            try:
                async with coordinator.lock:
                    await coordinator.export()
                    coordinator.async_update_listeners()
            finally:
                coordinator._startup_cleanup_task = None

        entry.async_on_unload(async_at_started(hass, clean_after_start))
    entry.async_on_unload(async_track_time_interval(hass, coordinator.history_tick, timedelta(minutes=1)))
    entry.async_on_unload(entry.add_update_listener(_reload))

    if not hass.services.has_service(DOMAIN, "sync"):
        async def sync(call):
            entry_id = call.data["entry_id"]
            target = hass.config_entries.async_get_entry(entry_id)
            if target and target.domain == DOMAIN and getattr(target, "runtime_data", None):
                await target.runtime_data.async_request_refresh()

        hass.services.async_register(DOMAIN, "sync", sync,
                                     schema=vol.Schema({vol.Required("entry_id"): str}))
        async def rescan(call):
            from datetime import datetime, timedelta
            from .profile import WARSAW
            target = hass.config_entries.async_get_entry(call.data["entry_id"])
            if target and target.domain == DOMAIN and getattr(target, "runtime_data", None):
                meter = target.runtime_data
                async with meter.lock:
                    meter.archive["cursor"] = (datetime.now(WARSAW).date() - timedelta(days=1)).isoformat()
                    meter.archive["complete"] = False
                    meter._retry_after = None
                    meter.archive.pop("history_day_progress", None)
                    meter.archive.pop("availability_months", None)
                    meter.archive.pop("history_skipped_months", None)
                    meter.archive["history_connection_failures"] = 0
                    meter.archive["history_retry_after"] = None
                    meter.archive["history_retry_kind"] = None
                    await meter.store.async_save(meter.archive)
                    meter.async_set_updated_data(meter.archive)

        hass.services.async_register(DOMAIN, "rescan_history", rescan,
                                     schema=vol.Schema({vol.Required("entry_id"): str}))
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])
    if unloaded:
        await entry.runtime_data.stop()
        await entry.runtime_data.api.session.close()
    return unloaded
