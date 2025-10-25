"""Adds config flow for CAME Integration.

Versione ottimizzata da Stefano Paoletti
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import logging
from typing import Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.typing import ConfigType

from .pycame.came_manager import CameManager
from .pycame.exceptions import ETIDomoConnectionError, ETIDomoConnectionTimeoutError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CameFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for CAME Integration."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[ConfigType] = None):
        """Handle a flow initialized by the user."""
        errors = {}
        
        # Verifica se già configurato
        if self._async_current_entries():
            _LOGGER.warning("CAME integration already configured")
            return self.async_abort(reason="single_instance_allowed")
        
        if user_input is not None:
            _LOGGER.debug("Testing CAME connection for host: %s", user_input.get(CONF_HOST))
            
            # Testa la connessione
            valid, error = await self._test_credentials(user_input)
            
            if valid:
                _LOGGER.info("CAME connection successful for %s", user_input[CONF_HOST])
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=user_input[CONF_HOST], 
                    data=user_input
                )
            else:
                _LOGGER.warning("CAME connection failed: %s", error)
                errors["base"] = error
        
        return await self._show_config_form(user_input, errors)

    async def _show_config_form(self, cfg: ConfigType, errors):
        """Show the configuration form."""
        if cfg is None:
            cfg = {}
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=cfg.get(CONF_HOST, "")): cv.string,
                    vol.Required(CONF_USERNAME, default=cfg.get(CONF_USERNAME, "admin")): cv.string,
                    vol.Required(CONF_PASSWORD, default=cfg.get(CONF_PASSWORD, "admin")): cv.string,
                }
            ),
            errors=errors,
        )

    async def _test_credentials(self, config: ConfigType) -> tuple[bool, str]:
        """Test if connection is valid.
        
        Returns:
            tuple: (is_valid, error_code)
        """
        try:
            _LOGGER.debug("Creating CAME manager to test connection")
            manager = CameManager(
                config[CONF_HOST],
                config[CONF_USERNAME],
                config[CONF_PASSWORD],
            )
            
            # Tenta la connessione
            await self.hass.async_add_executor_job(manager.login)
            _LOGGER.debug("CAME connection successful")
            return True, None
            
        except ETIDomoConnectionTimeoutError as exc:
            _LOGGER.error("CAME connection timeout: %s", exc)
            return False, "timeout"
        
        except ETIDomoConnectionError as exc:
            _LOGGER.error("CAME connection error: %s", exc)
            return False, "cannot_connect"
        
        except ValueError as exc:
            _LOGGER.error("CAME invalid configuration: %s", exc)
            return False, "invalid_auth"
        
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error testing CAME connection: %s", exc)
            return False, "unknown"
