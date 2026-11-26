"""eLicznik transport, based on Piotr Machowski's MIT Tauron AMIplus.

Endpoint and Keycloak protocol reference: upstream commit
eff7c51b473af0300be8e4ae8087310b563d3bbf. No credentials or responses logged.
"""
from __future__ import annotations

import asyncio
from datetime import date
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from aiohttp import ClientConnectionError, ClientSession, ClientTimeout

from .const import BASE_URL, LOGIN_URL


class ApiError(Exception):
    """Request failed; do not mistake this for an empty historical day."""


class AuthenticationError(ApiError):
    """Credentials need updating."""


class ApiResponseError(ApiError):
    """Preserve a rejected measurement response for local diagnostics."""

    def __init__(self, endpoint, response):
        super().__init__("Tauron API did not confirm a successful response")
        self.endpoint = endpoint
        self.response = response

    @property
    def summary(self):
        result = {"json_type": type(self.response).__name__}
        if isinstance(self.response, dict):
            result["fields"] = list(self.response)[:20]
            result["success_type"] = type(self.response.get("success")).__name__
            success = self.response.get("success")
            if isinstance(success, (bool, int, float)) or success is None:
                result["success"] = success
        return result


class TransientApiError(ApiError):
    """A connection failure or temporary server error; retry with backoff."""


class RateLimitError(ApiError):
    """Tauron explicitly requested a longer pause."""

    def __init__(self, message, retry_after_seconds=3600):
        super().__init__(message)
        self.retry_after_seconds = max(3600, retry_after_seconds)


class LoginPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.meters = {}
        self._meter = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs.get("action")
        if tag == "option" and "data-data" in attrs:
            self._meter = attrs.get("value")
            if self._meter:
                self.meters[self._meter] = {
                    "name": "", "business": '"WO"' in attrs["data-data"]
                }

    def handle_data(self, data):
        if self._meter:
            self.meters[self._meter]["name"] += data.strip()

    def handle_endtag(self, tag):
        if tag == "option":
            self._meter = None


class TauronAPI:
    """One private cookie session per account/meter, reused between syncs."""

    def __init__(self, session: ClientSession, username: str, password: str):
        self.session = session
        self.username = username
        self.password = password
        self.meters = {}
        self.business = False
        self.selected = None

    async def _text(self, method, url, **kwargs):
        try:
            async with self.session.request(
                method, url, timeout=ClientTimeout(total=45), **kwargs
            ) as response:
                if response.status == 429:
                    from datetime import datetime, timezone
                    from email.utils import parsedate_to_datetime
                    delay = 3600
                    header = response.headers.get("Retry-After", "")
                    try:
                        delay = int(header)
                    except ValueError:
                        try:
                            delay = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            pass
                    raise RateLimitError("Tauron rate limit: retry later", delay)
                if response.status >= 500:
                    raise TransientApiError("Tauron server temporarily unavailable")
                response.raise_for_status()
                text = await response.text()
                if "Przekroczono maksymalną liczbę logowań" in text:
                    raise RateLimitError("Tauron login limit: retry later")
                return text, str(response.url)
        except (ClientConnectionError, asyncio.TimeoutError, OSError) as err:
            raise TransientApiError("Tauron connection failed") from err

    async def login(self):
        text, _ = await self._text("GET", BASE_URL)
        page = LoginPage()
        page.feed(text)
        if not page.meters:
            text, url = await self._text("GET", LOGIN_URL, params={"service": BASE_URL})
            page = LoginPage()
            page.feed(text)
            if not page.action:
                raise ApiError("Unrecognized Tauron login page")
            action = urljoin(url, unescape(page.action))
            parsed = urlparse(action)
            if parsed.scheme != "https" or parsed.hostname != urlparse(LOGIN_URL).hostname:
                raise ApiError("Unexpected Tauron authentication host")
            text, _ = await self._text("POST", action, data={
                "username": self.username, "password": self.password, "credentialId": ""
            })
            page = LoginPage()
            page.feed(text)
            if page.action:
                raise AuthenticationError("Credentials rejected")
        if not page.meters:
            raise ApiError("No eLicznik meters found")
        self.meters = page.meters
        return self.meters

    async def select(self, meter_id):
        await self.login()
        if meter_id not in self.meters:
            raise ApiError("Selected meter is no longer available on this account")
        await self._text("POST", BASE_URL + "/ustaw_punkt", data={"site[client]": meter_id})
        self.business = self.meters[meter_id]["business"]
        self.selected = meter_id

    async def post(self, endpoint, payload):
        import json

        text, _ = await self._text("POST", BASE_URL + endpoint, data=payload)
        try:
            result = json.loads(text)
        except ValueError as err:
            raise ApiError("Tauron returned a page instead of JSON") from err
        if not isinstance(result, dict) or result.get("success") is not True:
            raise ApiResponseError(endpoint, result)
        return result

    async def profile(self, start: date, end: date, direction="consum", profile="full time"):
        endpoint = "/energia/wo/api" if self.business else "/energia/api"
        return await self.post(endpoint, {
            "from": start.strftime("%d.%m.%Y"), "to": end.strftime("%d.%m.%Y"),
            "profile": profile, "type": direction,
            "energy": 2 if direction == "oze" else 1,
        })

    async def readings(self, start: date, end: date, direction="consum"):
        return await self.post("/odczyty/api", {
            "from": start.strftime("%d.%m.%Y"), "to": end.strftime("%d.%m.%Y"),
            "type": "energia-oddana" if direction == "oze" else "energia-pobrana",
        })
