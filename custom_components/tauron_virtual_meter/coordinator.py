"""Persistent raw archive, resumable history scan and scheduled refresh."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging

from aiohttp import ClientError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthenticationError, TauronAPI
from .const import DEFAULT_HISTORY_START, DEFAULT_INTERVAL, DOMAIN
from .profile import ProfileError, WARSAW, cumulative_statistics, parse_day

_LOGGER = logging.getLogger(__name__)


class MeterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, session):
        minutes = entry.options.get("interval_minutes", DEFAULT_INTERVAL)
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(minutes=minutes) if minutes else None)
        self.entry = entry
        self.api = TauronAPI(session, entry.data["username"], entry.data["password"])
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.index")
        self.archive = None
        self.lock = asyncio.Lock()
        self.exporters = []
        self._retry_after = None
        self._history_task = None
        self._stopping = False

    @property
    def history_start(self):
        return date.fromisoformat(self.entry.options.get("history_start", DEFAULT_HISTORY_START))

    @property
    def history_cursor(self):
        return date.fromisoformat(self.archive["cursor"])

    async def load(self):
        self.archive = await self.store.async_load() or {
            "profiles": {"consum": {}, "oze": {}}, "issues": {},
            "cursor": (datetime.now(WARSAW).date() - timedelta(days=1)).isoformat(),
            "last_sync": None,
        }
        # If the configured lower bound moved earlier, resume below the previous bound.
        if date.fromisoformat(self.archive["cursor"]) >= self.history_start:
            self.archive["complete"] = False

    async def raw_save(self, key, response):
        await Store(self.hass, 1, f"{DOMAIN}.{self.entry.entry_id}.{key}").async_save(response)

    async def download_day(self, day):
        for direction in ("consum", "oze"):
            response = await self.api.profile(day, day, direction)
            # Keep the finest response, zones, status flags and unrecognized fields.
            await self.raw_save(f"{day.isoformat()}.{direction}", response)
            issue_key = f"{day.isoformat()}.{direction}"
            try:
                intervals = parse_day(day, response)
                previous = self.archive["profiles"][direction].get(day.isoformat(), {})
                # Omit null intervals, but retain an earlier real observation if the
                # provider temporarily withdraws it. Flag the discrepancy for review.
                withdrawn = previous.keys() - intervals.keys()
                self.archive["profiles"][direction][day.isoformat()] = {**previous, **intervals}
                if withdrawn:
                    self.archive["issues"][issue_key] = "Earlier intervals missing in latest response; retained"
                else:
                    self.archive["issues"].pop(issue_key, None)
            except ProfileError as err:
                self.archive["issues"][issue_key] = str(err)
            await asyncio.sleep(0.5)

    async def snapshots(self, today):
        start = today - timedelta(days=7)
        for direction in ("consum", "oze"):
            await self.raw_save(f"latest_readings.{direction}", await self.api.readings(start, today, direction))
            for profile, begin in (("month", today.replace(day=1)), ("year", today.replace(day=1, month=1))):
                await self.raw_save(f"latest_{profile}.{direction}", await self.api.profile(begin, today, direction, profile))
                await asyncio.sleep(0.5)
        await self.raw_save("meters", self.api.meters)

    async def _async_update_data(self):
        async with self.lock:
            try:
                await self.api.select(self.entry.data["meter_id"])
                today = datetime.now(WARSAW).date()
                await self.snapshots(today)
                # Recheck the entire rolling week, including partial current day.
                for offset in range(7, -1, -1):
                    day = today - timedelta(days=offset)
                    if day >= self.history_start:
                        await self.download_day(day)
                self.archive["last_sync"] = datetime.now(timezone.utc).isoformat()
                await self.store.async_save(self.archive)
                await self.export()
                return self.archive
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (ApiError, ClientError, OSError, ValueError) as err:
                # Preserve downloaded days even after a partially successful sync.
                await self.store.async_save(self.archive)
                raise UpdateFailed("Nie udało się zsynchronizować danych eLicznik") from err

    async def history_tick(self, _now=None):
        """Fourteen days per minute; checkpoint each complete day, resume on restart."""
        if self._stopping or self._history_task is not None:
            return
        self._history_task = asyncio.current_task()
        try:
            await self._history_work()
        finally:
            self._history_task = None

    async def stop(self):
        self._stopping = True
        if self._history_task is not None:
            self._history_task.cancel()
            try:
                await self._history_task
            except asyncio.CancelledError:
                pass

    async def _history_work(self):
        if self.lock.locked() or self.archive.get("complete"):
            return
        if self._retry_after and datetime.now(timezone.utc) < self._retry_after:
            return
        async with self.lock:
            self.archive["last_history_attempt"] = datetime.now(timezone.utc).isoformat()
            try:
                await self.api.select(self.entry.data["meter_id"])
                for _ in range(14):
                    day = self.history_cursor
                    if day < self.history_start:
                        self.archive["complete"] = True
                        break
                    await self.download_day(day)
                    # Daily register responses are archived too; no unproven
                    # assumptions about the register timestamp are used in sums.
                    for direction in ("consum", "oze"):
                        await self.raw_save(f"{day.isoformat()}.readings.{direction}",
                                            await self.api.readings(day, day, direction))
                        await asyncio.sleep(0.5)
                    self.archive["cursor"] = (day - timedelta(days=1)).isoformat()
                    await self.store.async_save(self.archive)
                self.archive["last_history_error"] = None
                self.archive["history_retry_after"] = None
                self._retry_after = None
                await self.store.async_save(self.archive)
                await self.export()
                self.async_set_updated_data(self.archive)
            except AuthenticationError:
                self._retry_after = datetime.now(timezone.utc) + timedelta(hours=1)
                self.archive["last_history_error"] = "AuthenticationError: credentials rejected"
                self.archive["history_retry_after"] = self._retry_after.isoformat()
                await self.store.async_save(self.archive)
                self.async_update_listeners()
                self.entry.async_start_reauth(self.hass)
            except (ApiError, ClientError, OSError, ValueError) as err:
                self._retry_after = datetime.now(timezone.utc) + timedelta(hours=1)
                # Only our fixed-message API errors are exposed; third-party
                # exception text can contain request details.
                reason = str(err) if isinstance(err, ApiError) else type(err).__name__
                self.archive["last_history_error"] = reason
                self.archive["history_retry_after"] = self._retry_after.isoformat()
                await self.store.async_save(self.archive)
                await self.export()
                self.async_update_listeners()
                _LOGGER.warning("Import historii wstrzymany na godzinę (%s); postęp zachowano", reason)

    async def export(self):
        # Sensors expose partial values immediately. Each exporter still waits
        # for scan completion before committing the final historical origin.
        for exporter in tuple(self.exporters):
            await exporter()

    async def statistics(self, direction):
        return await self.hass.async_add_executor_job(
            cumulative_statistics, self.archive["profiles"][direction]
        )
