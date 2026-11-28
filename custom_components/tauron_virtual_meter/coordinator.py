"""Persistent raw archive, resumable history scan and scheduled refresh."""
from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import logging

from aiohttp import ClientConnectionError, ClientError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, ApiResponseError, AuthenticationError, RateLimitError, TauronAPI, TransientApiError
from .const import DEFAULT_HISTORY_START, DEFAULT_INTERVAL, DOMAIN
from .profile import ProfileError, WARSAW, cumulative_statistics, month_summary_status, parse_day
from .storage import async_migrate_storage, storage_key
from .history import async_clean_state_history

_LOGGER = logging.getLogger(__name__)


class MeterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, session):
        minutes = entry.options.get("interval_minutes", DEFAULT_INTERVAL)
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(minutes=minutes) if minutes else None)
        self.entry = entry
        self.api = TauronAPI(session, entry.data["username"], entry.data["password"])
        self.store = Store(hass, 1, storage_key(entry.entry_id, "index"))
        self.archive = None
        self.lock = asyncio.Lock()
        self.exporters = []
        self._retry_after = None
        self._history_task = None
        self._startup_cleanup_task = None
        self._stopping = False

    @property
    def history_start(self):
        return date.fromisoformat(self.entry.options.get("history_start", DEFAULT_HISTORY_START))

    @property
    def history_cursor(self):
        return date.fromisoformat(self.archive["cursor"])

    async def load(self):
        await async_migrate_storage(self.hass, self.entry.entry_id)
        self.archive = await self.store.async_load() or {
            "profiles": {"consum": {}, "oze": {}}, "issues": {},
            "cursor": (datetime.now(WARSAW).date() - timedelta(days=1)).isoformat(),
            "last_sync": None,
        }
        # If the configured lower bound moved earlier, resume below the previous bound.
        if date.fromisoformat(self.archive["cursor"]) >= self.history_start:
            self.archive["complete"] = False
        if not self.entry.options.get("auto_detect_history", True) and self.archive.get("history_skipped_months"):
            latest_skipped = max(item["to"] for item in self.archive["history_skipped_months"].values())
            self.archive["cursor"] = max(self.archive["cursor"], latest_skipped)
            self.archive["complete"] = False
            self.archive.pop("history_skipped_months", None)
            self.archive.pop("availability_months", None)
        await self.repair_cached_dates()
        # Preserve an explicit cooldown across restarts. Older versions had
        # no retry category and imposed an hour on every transient disconnect.
        if self.archive.get("history_retry_kind") and self.archive.get("history_retry_after"):
            self._retry_after = datetime.fromisoformat(self.archive["history_retry_after"])
        progress = self.archive.get("history_day_progress", {})
        if (self.archive.get("history_retry_kind") == "api_error"
                and self.archive.get("last_history_error") == "Tauron API did not confirm a successful response"
                and {"profile.consum", "profile.oze"}.issubset(progress.get("completed", []))):
            # Previous releases paused the entire scan after an auxiliary
            # register rejection. Resume that exact pending day on next tick.
            self._retry_after = None
            self.archive["history_retry_after"] = None
            self.archive["history_retry_kind"] = None
            self.archive["last_history_error"] = None
            await self.store.async_save(self.archive)

    def apply_profile(self, day, direction, response):
        """Apply a downloaded or stored daily response with the same rules."""
        issue_key = f"{day.isoformat()}.{direction}"
        try:
            intervals = parse_day(day, response)
            previous = self.archive["profiles"][direction].get(day.isoformat(), {})
            withdrawn = previous.keys() - intervals.keys()
            self.archive["profiles"][direction][day.isoformat()] = {**previous, **intervals}
            if withdrawn:
                self.archive["issues"][issue_key] = "Earlier intervals missing in latest response; retained"
            else:
                self.archive["issues"].pop(issue_key, None)
            return True
        except ProfileError as err:
            self.archive["issues"][issue_key] = str(err)
            return False

    async def repair_cached_dates(self):
        """Reparse profiles affected by known parser fixes, without API calls.

        Raw files are keyed by the single day actually requested from Tauron.
        Keep them untouched, reparse only the known date/resolution errors, and leave
        unrelated parse errors visible for further diagnosis.
        """
        repaired = 0
        for key, reason in tuple(self.archive["issues"].items()):
            if reason not in {"Response contains a different date",
                              "Unknown profile resolution or ambiguous DST day"}:
                continue
            try:
                day_text, direction = key.rsplit(".", 1)
                day = date.fromisoformat(day_text)
            except ValueError:
                continue
            if direction not in ("consum", "oze"):
                continue
            response = await Store(self.hass, 1, storage_key(self.entry.entry_id, key)).async_load()
            if response is not None and self.apply_profile(day, direction, response):
                repaired += 1
        if repaired:
            self.archive["recovered_profile_count"] = self.archive.get("recovered_profile_count", 0) + repaired
            _LOGGER.info("Ponownie przetworzono %s zapisanych profili po poprawce parsera", repaired)
        await self.store.async_save(self.archive)

    async def raw_save(self, key, response):
        await Store(self.hass, 1, storage_key(self.entry.entry_id, key)).async_save(response)

    async def history_response(self, day, kind, direction, fetch):
        """Resume the failed day's requests without reusing old data on a rescan."""
        progress = self.archive.get("history_day_progress", {})
        if progress.get("day") != day.isoformat():
            progress = {"day": day.isoformat(), "completed": []}
            self.archive["history_day_progress"] = progress
        stage = f"{kind}.{direction}"
        key = f"{day.isoformat()}.{'readings.' if kind == 'readings' else ''}{direction}"
        if stage in progress["completed"]:
            cached = await Store(self.hass, 1, storage_key(self.entry.entry_id, key)).async_load()
            if cached is not None:
                return cached
        request = {"day": day.isoformat(), "kind": kind, "direction": direction}
        self.archive["last_history_request"] = request
        try:
            response = await fetch(day, day, direction)
        except ApiResponseError as err:
            self.archive["last_api_error_request"] = request
            self.archive["last_api_response_summary"] = err.summary
            rejected = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request": request, "endpoint": err.endpoint, "response": err.response,
            }
            await self.raw_save("last_api_error", rejected)
            await self.raw_save(f"{key}.error", rejected)
            raise
        await self.raw_save(key, response)
        if kind == "readings":
            self.archive.setdefault("reading_issues", {}).pop(f"{day.isoformat()}.{direction}", None)
        if stage not in progress["completed"]:
            progress["completed"].append(stage)
        return response

    async def sync_response(self, request, key, fetch, *args, optional=False):
        """Isolate rejected profiles and auxiliary failures during a refresh.

        Authentication and explicit rate limits always stop the refresh. Missing
        responses remain missing; retain earlier raw files and never insert zeros.
        """
        self.archive["last_sync_request"] = request
        issue_key = f"{request['day']}.{request['kind']}.{request['direction']}"
        try:
            response = await fetch(*args)
        except (AuthenticationError, RateLimitError):
            raise
        except (ApiError, ClientError, OSError, ValueError) as err:
            if not optional and not isinstance(err, ApiResponseError):
                raise
            reason = str(err) if isinstance(err, ApiError) else type(err).__name__
            self.archive.setdefault("sync_issues", {})[issue_key] = {
                "request": request, "reason": reason,
            }
            if isinstance(err, ApiResponseError):
                await self.raw_save(f"{key}.error", {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request": request, "endpoint": err.endpoint, "response": err.response,
                })
            return None
        self.archive.setdefault("sync_issues", {}).pop(issue_key, None)
        await self.raw_save(key, response)
        return response

    async def download_day(self, day, *, resume=False, periodic=False):
        accepted = 0
        for direction in ("consum", "oze"):
            if resume:
                response = await self.history_response(day, "profile", direction, self.api.profile)
            elif periodic:
                response = await self.sync_response(
                    {"day": day.isoformat(), "kind": "profile", "direction": direction},
                    f"{day.isoformat()}.{direction}", self.api.profile, day, day, direction,
                )
            else:
                response = await self.api.profile(day, day, direction)
                # Periodic refresh always fetches new data, regardless of cache.
                await self.raw_save(f"{day.isoformat()}.{direction}", response)
            if response is not None and self.apply_profile(day, direction, response):
                accepted += 1
            await asyncio.sleep(0.5)
        return accepted

    async def snapshots(self, today):
        start = today - timedelta(days=7)
        for direction in ("consum", "oze"):
            await self.sync_response(
                {"day": start.isoformat(), "to": today.isoformat(), "kind": "readings", "direction": direction},
                f"latest_readings.{direction}", self.api.readings, start, today, direction, optional=True,
            )
            for profile, begin in (("month", today.replace(day=1)), ("year", today.replace(day=1, month=1))):
                await self.sync_response(
                    {"day": begin.isoformat(), "to": today.isoformat(), "kind": profile, "direction": direction},
                    f"latest_{profile}.{direction}", self.api.profile, begin, today, direction, profile, optional=True,
                )
                await asyncio.sleep(0.5)
        await self.raw_save("meters", self.api.meters)

    async def skip_empty_month(self, day):
        """Use two monthly charts instead of four requests per empty day."""
        if not self.entry.options.get("auto_detect_history", True):
            return False
        start = day.replace(day=1)
        end = day.replace(day=monthrange(day.year, day.month)[1])
        if end >= datetime.now(WARSAW).date() - timedelta(days=7):
            return False  # Recent data may still be arriving.
        month = day.strftime("%Y-%m")
        if any(key.startswith(month) for key in self.archive["issues"]):
            return False  # An unresolved raw profile can contain real measurements.
        # Recorded hourly observations always override an empty summary.
        if any(values for direction in ("consum", "oze")
               for key, values in self.archive["profiles"][direction].items()
               if key.startswith(month)):
            return False
        cache = self.archive.setdefault("availability_months", {})
        summary = cache.get(month)
        now = datetime.now(timezone.utc)
        if summary is None or now - datetime.fromisoformat(summary["checked_at"]) >= timedelta(days=1):
            summary = {"checked_at": now.isoformat()}
            for direction in ("consum", "oze"):
                self.archive["last_history_request"] = {
                    "day": start.isoformat(), "to": end.isoformat(),
                    "kind": "availability_month", "direction": direction,
                }
                try:
                    response = await self.api.profile(start, end, direction, "month")
                except ApiResponseError as err:
                    summary[direction] = "unknown"
                    await self.raw_save(f"availability.{month}.{direction}.error", {
                        "request": self.archive["last_history_request"],
                        "endpoint": err.endpoint, "response": err.response,
                    })
                else:
                    await self.raw_save(f"availability.{month}.{direction}", response)
                    summary[direction] = month_summary_status(start, response)
                await asyncio.sleep(0.5)
            cache[month] = summary
            await self.store.async_save(self.archive)
        if any(summary.get(direction) != "empty" for direction in ("consum", "oze")):
            return False
        first = max(start, self.history_start)
        # Never infer that all older months are empty: the next iteration
        # checks the preceding month, even across a gap in observations.
        skipped = self.archive.setdefault("history_skipped_months", {})
        previous = skipped.get(month)
        skipped[month] = {
            "from": min(first.isoformat(), previous["from"]) if previous else first.isoformat(),
            "to": max(day.isoformat(), previous["to"]) if previous else day.isoformat(),
            "checked_at": summary["checked_at"],
        }
        self.archive["cursor"] = (first - timedelta(days=1)).isoformat()
        self.archive.pop("history_day_progress", None)
        self.archive["history_connection_failures"] = 0
        await self.store.async_save(self.archive)
        return True

    async def _async_update_data(self):
        async with self.lock:
            self.archive["last_sync_attempt"] = datetime.now(timezone.utc).isoformat()
            self.archive["last_sync_request"] = None
            self.archive["sync_issues"] = {}
            try:
                await self.api.select(self.entry.data["meter_id"])
                today = datetime.now(WARSAW).date()
                # Recheck the entire rolling week, including partial current day.
                accepted = 0
                for offset in range(0, 8):
                    day = today - timedelta(days=offset)
                    if day >= self.history_start:
                        accepted += await self.download_day(day, periodic=True)
                if not accepted:
                    raise ApiError("No daily profiles accepted during refresh")
                await self.snapshots(today)
                self.archive["last_sync"] = datetime.now(timezone.utc).isoformat()
                self.archive["last_sync_error"] = None
                await self.store.async_save(self.archive)
                await self.export()
                return self.archive
            except AuthenticationError as err:
                self.archive["last_sync_error"] = "AuthenticationError: credentials rejected"
                await self.store.async_save(self.archive)
                raise ConfigEntryAuthFailed(str(err)) from err
            except (ApiError, ClientError, OSError, ValueError) as err:
                # Preserve downloaded days even after a partially successful sync.
                reason = str(err) if isinstance(err, ApiError) else type(err).__name__
                self.archive["last_sync_error"] = reason
                await self.store.async_save(self.archive)
                await self.export()
                raise UpdateFailed(f"Nie udało się zsynchronizować danych eLicznik: {reason}") from err

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
        for task in (self._history_task, self._startup_cleanup_task):
            if task is None or task is asyncio.current_task():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _history_work(self):
        if self.lock.locked() or self.archive.get("complete"):
            return
        if self._retry_after and datetime.now(timezone.utc) < self._retry_after:
            return
        async with self.lock:
            self.archive["last_history_attempt"] = datetime.now(timezone.utc).isoformat()
            self.async_update_listeners()
            try:
                await self.api.select(self.entry.data["meter_id"])
                for _ in range(14):
                    day = self.history_cursor
                    if day < self.history_start:
                        self.archive["complete"] = True
                        break
                    if await self.skip_empty_month(day):
                        continue
                    await self.download_day(day, resume=True)
                    # Daily register responses are archived too; no unproven
                    # assumptions about the register timestamp are used in sums.
                    for direction in ("consum", "oze"):
                        try:
                            await self.history_response(day, "readings", direction, self.api.readings)
                        except ApiResponseError as err:
                            # Hourly profiles above already succeeded. The
                            # register is auxiliary and never used in the counter.
                            # Preserve the rejection, not a zero/empty reading,
                            # without blocking all subsequent historical days.
                            self.archive.setdefault("reading_issues", {})[f"{day.isoformat()}.{direction}"] = str(err)
                        await asyncio.sleep(0.5)
                    self.archive["cursor"] = (day - timedelta(days=1)).isoformat()
                    self.archive.pop("history_day_progress", None)
                    self.archive["history_connection_failures"] = 0
                    await self.store.async_save(self.archive)
                self.archive["last_history_error"] = None
                self.archive["history_retry_after"] = None
                self.archive["history_retry_kind"] = None
                self._retry_after = None
                await self.store.async_save(self.archive)
                await self.export()
                self.async_set_updated_data(self.archive)
            except AuthenticationError:
                self._retry_after = datetime.now(timezone.utc) + timedelta(hours=1)
                self.archive["last_history_error"] = "AuthenticationError: credentials rejected"
                self.archive["history_retry_after"] = self._retry_after.isoformat()
                self.archive["history_retry_kind"] = "authentication"
                await self.store.async_save(self.archive)
                self.async_update_listeners()
                self.entry.async_start_reauth(self.hass)
            except (ApiError, ClientError, OSError, ValueError) as err:
                if isinstance(err, RateLimitError):
                    delay = err.retry_after_seconds
                    kind = "rate_limit"
                elif isinstance(err, (TransientApiError, ClientConnectionError, OSError)):
                    failures = min(self.archive.get("history_connection_failures", 0) + 1, 5)
                    self.archive["history_connection_failures"] = failures
                    delay = min(60 * 2 ** (failures - 1), 900)
                    kind = "connection"
                else:
                    delay = 3600
                    kind = "api_error"
                self._retry_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
                # Only our fixed-message API errors are exposed; third-party
                # exception text can contain request details.
                reason = str(err) if isinstance(err, ApiError) else type(err).__name__
                self.archive["last_history_error"] = reason
                self.archive["history_retry_after"] = self._retry_after.isoformat()
                self.archive["history_retry_kind"] = kind
                await self.store.async_save(self.archive)
                await self.export()
                self.async_update_listeners()
                _LOGGER.warning("Import historii wstrzymany na %s s (%s); postęp zachowano", delay, reason)

    async def export(self):
        # Sensors expose partial totals as progress attributes, then publish
        # the main counter and hourly statistics once its origin is established.
        imported = {}
        for exporter in tuple(self.exporters):
            result = await exporter()
            if isinstance(result, dict) and "entity_id" in result and "last" in result:
                imported[result["entity_id"]] = result["last"]
        if (imported and self.archive.get("complete")
                and self.entry.options.get("auto_clean_state_history", False)
                and self.hass.is_running):
            try:
                requested = await async_clean_state_history(self.hass, imported)
                if requested:
                    self.archive["state_history_cleanup_last_requested"] = datetime.now(timezone.utc).isoformat()
                    self.archive["state_history_cleanup_error"] = None
                else:
                    self.archive["state_history_cleanup_error"] = "Committed statistics did not match import; no states removed"
            except Exception as err:
                # A cleanup failure must not invalidate a successful Tauron sync.
                self.archive["state_history_cleanup_error"] = type(err).__name__
                _LOGGER.warning("Nie zlecono czyszczenia historii stanów: %s", type(err).__name__)
            await self.store.async_save(self.archive)

    async def statistics(self, direction):
        return await self.hass.async_add_executor_job(
            cumulative_statistics, self.archive["profiles"][direction]
        )
