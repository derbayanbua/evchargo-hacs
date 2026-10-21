from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import normalize_charger_id
from .const import CONF_CHARGER_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_migrate_charger_identity(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Normalize registry identities while preserving the original entity IDs."""
    charger_id = normalize_charger_id(entry.data[CONF_CHARGER_ID])
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and (
            other.unique_id == charger_id
            or other.data.get(CONF_CHARGER_ID, "").strip() == charger_id
        ):
            raise ConfigEntryError(
                "Another Evchargo config entry uses the same trimmed charger ID; "
                "resolve the duplicate integration entries before retrying"
            )

    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    aliases = {entry.data[CONF_CHARGER_ID], charger_id}
    legacy_devices = []
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        ids = {
            identifier
            for domain, identifier in device.identifiers
            if domain == DOMAIN and identifier.strip() == charger_id
        }
        if not ids:
            continue
        aliases.update(ids)
        if ids - {charger_id}:
            legacy_devices.append(device)

    if len(legacy_devices) > 1:
        raise ConfigEntryError(
            "Multiple legacy Evchargo devices match the trimmed charger ID; "
            "registry migration needs manual review"
        )
    original = legacy_devices[0] if legacy_devices else None
    canonical = devices.async_get_device(identifiers={(DOMAIN, charger_id)})
    if canonical is not None and entry.entry_id not in canonical.config_entries:
        raise ConfigEntryError(
            "The trimmed Evchargo device ID belongs to another integration entry"
        )
    duplicate = canonical if original and canonical and original.id != canonical.id else None
    if duplicate and duplicate.config_entries != {entry.entry_id}:
        raise ConfigEntryError(
            "The duplicate Evchargo device is shared with another integration; "
            "registry migration needs manual review"
        )

    # Plan and validate every unique-ID collision before changing any registry.
    updates: dict[str, er.RegistryEntry] = {}
    for entity in er.async_entries_for_config_entry(entities, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        for alias in aliases - {charger_id}:
            if entity.unique_id.startswith(f"{alias}_"):
                new_id = f"{charger_id}_{entity.unique_id[len(alias) + 1:]}"
                if new_id in updates:
                    raise ConfigEntryError(
                        "Multiple legacy Evchargo entities match one trimmed unique ID; "
                        "registry migration needs manual review"
                    )
                updates[new_id] = entity
                break

    collisions: dict[str, str] = {}
    for new_id, entity in updates.items():
        collision = entities.async_get_entity_id(entity.domain, DOMAIN, new_id)
        if collision is None:
            continue
        existing = entities.async_get(collision)
        if existing is None or existing.config_entry_id != entry.entry_id:
            raise ConfigEntryError(
                "A trimmed Evchargo entity unique ID belongs to another config entry"
            )
        collisions[new_id] = collision

    for new_id, entity in updates.items():
        if collision := collisions.get(new_id):
            _LOGGER.warning(
                "Removing duplicate registry entity %s in favor of original %s; "
                "references to the duplicate entity must use the original entity ID",
                collision,
                entity.entity_id,
            )
            entities.async_remove(collision)
        entities.async_update_entity(entity.entity_id, new_unique_id=new_id)

    if original:
        if duplicate:
            # Move all remaining entities, including the new normalized-state
            # sensor and helper entities, before removing the duplicate device.
            for entity in er.async_entries_for_device(
                entities, duplicate.id, include_disabled_entities=True
            ):
                entities.async_update_entity(entity.entity_id, device_id=original.id)
            for device in list(devices.devices.values()):
                if device.via_device_id == duplicate.id:
                    devices.async_update_device(device.id, via_device_id=original.id)
            devices.async_remove_device(duplicate.id)
        identifiers = {
            (domain, identifier)
            for domain, identifier in original.identifiers
            if domain != DOMAIN or identifier.strip() != charger_id
        }
        devices.async_update_device(
            original.id, new_identifiers=identifiers | {(DOMAIN, charger_id)}
        )

    if entry.data[CONF_CHARGER_ID] != charger_id or entry.unique_id != charger_id:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_CHARGER_ID: charger_id},
            unique_id=charger_id,
        )
