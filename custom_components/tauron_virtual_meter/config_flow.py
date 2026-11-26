"""UI setup, meter selection, reauthentication and polling options."""
from datetime import date
import voluptuous as vol

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import selector

from .api import ApiError, AuthenticationError, TauronAPI
from .const import DEFAULT_HISTORY_START, DEFAULT_INTERVAL, DOMAIN


def options_schema(options):
    return vol.Schema({
        vol.Required("history_start", default=options.get("history_start", DEFAULT_HISTORY_START)): selector({"date": {}}),
        vol.Required("interval_minutes", default=options.get("interval_minutes", DEFAULT_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=0, max=10080)),
    })


def validate_options(data):
    try:
        if not date(2000, 1, 1) <= date.fromisoformat(data["history_start"]) <= date.today():
            return {"history_start": "invalid_date"}
    except ValueError:
        return {"history_start": "invalid_date"}
    return {}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.credentials = {}
        self.meters = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            session = async_create_clientsession(self.hass)
            try:
                api = TauronAPI(session, user_input["username"], user_input["password"])
                self.meters = await api.login()
                self.credentials = user_input
                if self.source == config_entries.SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if entry.data["meter_id"] not in self.meters:
                        errors["base"] = "meter_missing"
                    else:
                        return self.async_update_reload_and_abort(entry, data_updates=user_input)
                else:
                    return await self.async_step_meter()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except (ApiError, ClientError, OSError):
                errors["base"] = "cannot_connect"
            finally:
                await session.close()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("username"): str,
            vol.Required("password"): selector({"text": {"type": "password"}}),
        }), errors=errors)

    async def async_step_meter(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = validate_options(user_input)
            if user_input["meter_id"] not in self.meters:
                errors["base"] = "meter_missing"
            if not errors:
                await self.async_set_unique_id(user_input["meter_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Tauron {user_input['meter_id']}",
                    data={**self.credentials, "meter_id": user_input["meter_id"]},
                    options={key: user_input[key] for key in ("history_start", "interval_minutes")},
                )
        schema = options_schema(user_input or {}).extend({
            vol.Required("meter_id"): selector({"select": {"options": [
                {"value": key, "label": value["name"] or key} for key, value in self.meters.items()
            ]}})
        })
        return self.async_show_form(step_id="meter", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = validate_options(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=options_schema(self.config_entry.options), errors=errors)
