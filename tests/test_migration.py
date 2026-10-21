"""Exercise identity upgrades using real Home Assistant registries."""

from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr, entity_registry as er

import custom_components.evchargo as integration
from custom_components.evchargo.const import CONF_CHARGER_ID, DOMAIN
from custom_components.evchargo.migration import async_migrate_charger_identity


class IdentityMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        self.entry = MagicMock()
        self.entry.entry_id = "evchargo-entry"
        self.entry.domain = DOMAIN
        self.entry.data = {CONF_CHARGER_ID: " CP-123 "}
        self.entry.unique_id = " CP-123 "
        self.entry.disabled_by = None
        self.entry.subentries = {}
        self.entry.pref_disable_new_entities = False
        self.manager = MagicMock()
        self.manager.async_get_entry.return_value = self.entry
        self.manager.async_entries.return_value = [self.entry]

        def update_entry(entry, **changes):
            for key, value in changes.items():
                setattr(entry, key, value)
            return True

        self.manager.async_update_entry.side_effect = update_entry
        self.hass.config_entries = self.manager
        self.devices = dr.DeviceRegistry(self.hass)
        self.entities = er.EntityRegistry(self.hass)
        await self.devices.async_load()
        await self.entities.async_load()
        device_patch = patch.object(dr, "async_get", return_value=self.devices)
        entity_patch = patch.object(er, "async_get", return_value=self.entities)
        device_patch.start()
        entity_patch.start()
        self.addCleanup(device_patch.stop)
        self.addCleanup(entity_patch.stop)

    async def asyncTearDown(self):
        await self.hass.async_stop()

    def device(self, charger_id):
        return self.devices.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, charger_id)},
            manufacturer="EN+",
            name="Home",
        )

    def entity(self, device, charger_id, key="status", suggested="garden_home_status"):
        return self.entities.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{charger_id}_{key}",
            config_entry=self.entry,
            device_id=device.id,
            suggested_object_id=suggested,
        )

    async def test_upgrade_before_duplicates_preserves_registry_identity(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        self.devices.async_update_device(original.id, name_by_user="Garden charger")
        self.entities.async_update_entity(old.entity_id, name="My status")

        async_migrate_charger_identity(self.hass, self.entry)

        self.assertEqual(len(self.devices.devices), 1)
        self.assertEqual(
            self.devices.async_get_device(identifiers={(DOMAIN, "CP-123")}).id,
            original.id,
        )
        updated = self.entities.async_get(old.entity_id)
        self.assertEqual(updated.id, old.id)
        self.assertEqual(updated.unique_id, "CP-123_status")
        self.assertEqual(updated.name, "My status")
        self.assertEqual(updated.device_id, original.id)
        self.assertEqual(self.devices.async_get(original.id).name_by_user, "Garden charger")
        self.assertEqual(self.entry.data[CONF_CHARGER_ID], "CP-123")
        self.assertEqual(self.entry.unique_id, "CP-123")

    async def test_repair_duplicates_preserves_original_and_moves_new_entities(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        original = self.devices.async_update_device(
            original.id, area_id="garden", name_by_user="Garden charger",
            labels={"original-label"},
        )
        old = self.entities.async_update_entity(
            old.entity_id, name="Original status", icon="mdi:car",
            aliases={"car status"}, labels={"status-label"},
            disabled_by=er.RegistryEntryDisabler.USER,
        )
        duplicate = self.device("CP-123")
        redundant = self.entity(duplicate, "CP-123", suggested="home_status")
        new_sensor = self.entity(
            duplicate, "CP-123", "charging_state", "home_charging_state"
        )
        helper = self.entities.async_get_or_create(
            "sensor", "integration", "energy-helper",
            config_entry=self.entry, device_id=duplicate.id,
            suggested_object_id="home_energy_helper",
        )
        original_helper = self.entities.async_get_or_create(
            "sensor", "integration", "old-energy-helper",
            config_entry=self.entry, device_id=original.id,
            suggested_object_id="garden_home_energy",
        )

        with self.assertLogs("custom_components.evchargo.migration", level="WARNING"):
            async_migrate_charger_identity(self.hass, self.entry)

        self.assertEqual(len(self.devices.devices), 1)
        self.assertIsNone(self.entities.async_get(redundant.entity_id))
        updated = self.entities.async_get(old.entity_id)
        self.assertEqual(updated.id, old.id)
        self.assertEqual(updated.name, "Original status")
        self.assertEqual(updated.aliases, {"car status"})
        self.assertEqual(updated.labels, {"status-label"})
        self.assertEqual(updated.icon, "mdi:car")
        self.assertEqual(updated.disabled_by, er.RegistryEntryDisabler.USER)
        self.assertEqual(updated.unique_id, "CP-123_status")
        for item in (new_sensor, helper, original_helper):
            self.assertEqual(self.entities.async_get(item.entity_id).device_id, original.id)
        device = self.devices.async_get(original.id)
        self.assertEqual(device.area_id, "garden")
        self.assertEqual(device.name_by_user, "Garden charger")
        self.assertEqual(device.labels, {"original-label"})
        self.assertEqual(device.identifiers, {(DOMAIN, "CP-123")})
        before = [entity.as_partial_dict for entity in self.entities.entities.values()]
        async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(
            [entity.as_partial_dict for entity in self.entities.entities.values()], before
        )

    async def test_already_trimmed_entry_still_repairs_legacy_registry(self):
        original = self.device("CP-123 ")
        old = self.entity(original, "CP-123 ")
        self.device("CP-123")
        self.entry.data = {CONF_CHARGER_ID: "CP-123"}
        self.entry.unique_id = "CP-123"
        async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(len(self.devices.devices), 1)
        self.assertEqual(self.entities.async_get(old.entity_id).unique_id, "CP-123_status")

    async def test_clean_install_is_unchanged(self):
        self.entry.data = {CONF_CHARGER_ID: "CP-123"}
        self.entry.unique_id = "CP-123"
        original = self.device("CP-123")
        old = self.entity(original, "CP-123")
        async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(self.entities.async_get(old.entity_id), old)
        self.manager.async_update_entry.assert_not_called()

    async def test_all_platform_identities_keep_their_original_entity_ids(self):
        original = self.device("CP-123 ")
        duplicate = self.device("CP-123")
        originals = []
        for domain, key in (
            ("sensor", "power"),
            ("binary_sensor", "plugged_in"),
            ("switch", "charging_control"),
            ("number", "current_limit"),
            ("button", "start_charging"),
        ):
            originals.append(self.entities.async_get_or_create(
                domain, DOMAIN, f"CP-123 _{key}", config_entry=self.entry,
                device_id=original.id, suggested_object_id=f"garden_home_{key}",
            ))
            self.entities.async_get_or_create(
                domain, DOMAIN, f"CP-123_{key}", config_entry=self.entry,
                device_id=duplicate.id, suggested_object_id=f"home_{key}",
            )
        with self.assertLogs("custom_components.evchargo.migration", level="WARNING"):
            async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(len(self.entities.entities), len(originals))
        for entity in originals:
            updated = self.entities.async_get(entity.entity_id)
            self.assertEqual(updated.id, entity.id)
            self.assertEqual(updated.device_id, original.id)
            self.assertEqual(updated.unique_id, entity.unique_id.replace("CP-123 _", "CP-123_"))

    async def test_foreign_entity_collision_fails_before_mutation(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        collision = self.entities.async_get_or_create(
            "sensor", DOMAIN, "CP-123_status", suggested_object_id="other_status"
        )
        with self.assertRaisesRegex(ConfigEntryError, "another config entry"):
            async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(self.entities.async_get(old.entity_id), old)
        self.assertEqual(self.entities.async_get(collision.entity_id), collision)
        self.assertEqual(self.devices.async_get(original.id), original)
        self.manager.async_update_entry.assert_not_called()

    async def test_shared_duplicate_device_fails_before_mutation(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        duplicate = self.device("CP-123")
        self.devices.async_update_device(duplicate.id, add_config_entry_id="other-entry")
        with self.assertRaisesRegex(ConfigEntryError, "shared"):
            async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(len(self.devices.devices), 2)
        self.assertEqual(self.entities.async_get(old.entity_id), old)

    async def test_duplicate_config_entry_fails_before_mutation(self):
        other = MagicMock()
        other.entry_id = "other-entry"
        other.unique_id = "CP-123"
        self.manager.async_entries.return_value = [self.entry, other]
        with self.assertRaisesRegex(ConfigEntryError, "duplicate integration entries"):
            async_migrate_charger_identity(self.hass, self.entry)
        self.manager.async_update_entry.assert_not_called()

    async def test_ambiguous_legacy_devices_fail_before_mutation(self):
        original = self.device(" CP-123 ")
        self.device("CP-123 ")
        with self.assertRaisesRegex(ConfigEntryError, "Multiple legacy"):
            async_migrate_charger_identity(self.hass, self.entry)
        self.assertEqual(len(self.devices.devices), 2)
        self.assertEqual(self.devices.async_get(original.id), original)

    async def test_repair_is_saved_and_survives_registry_reload(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        duplicate = self.device("CP-123")
        self.entity(duplicate, "CP-123", suggested="home_status")
        new_sensor = self.entity(
            duplicate, "CP-123", "charging_state", "home_charging_state"
        )
        with self.assertLogs("custom_components.evchargo.migration", level="WARNING"):
            async_migrate_charger_identity(self.hass, self.entry)
        # Flush HA's delayed registry saves, then exercise its normal load path.
        await self.devices._store.async_save(self.devices._data_to_save())
        await self.entities._store.async_save(self.entities._data_to_save())
        restored_devices = dr.DeviceRegistry(self.hass)
        restored_entities = er.EntityRegistry(self.hass)
        await restored_devices.async_load()
        await restored_entities.async_load()
        self.assertEqual(len(restored_devices.devices), 1)
        self.assertEqual(
            restored_devices.async_get_device(identifiers={(DOMAIN, "CP-123")}).id,
            original.id,
        )
        self.assertEqual(
            restored_entities.async_get_entity_id("sensor", DOMAIN, "CP-123_status"),
            old.entity_id,
        )
        self.assertEqual(
            restored_entities.async_get(new_sensor.entity_id).device_id, original.id
        )

    async def test_setup_migrates_before_listeners_and_platforms(self):
        original = self.device(" CP-123 ")
        old = self.entity(original, " CP-123 ")
        self.entry.data = {
            **self.entry.data, "username": "test@example.invalid", "password": "test"
        }
        self.entry.options = {}
        coordinator = MagicMock()
        coordinator.charger_id = "CP-123"
        coordinator.async_config_entry_first_refresh = AsyncMock()
        order = []

        def listen(*args):
            self.assertEqual(self.entry.data[CONF_CHARGER_ID], "CP-123")
            self.assertEqual(
                self.entities.async_get(old.entity_id).unique_id, "CP-123_status"
            )
            order.append("listener")
            return MagicMock()

        async def forward(*args):
            self.assertEqual(order, ["listener"])
            self.assertEqual(self.entry.runtime_data.charger_id, "CP-123")
            order.append("platforms")

        self.entry.add_update_listener.side_effect = listen
        self.manager.async_forward_entry_setups = AsyncMock(side_effect=forward)
        with (
            patch.object(integration, "async_get_clientsession"),
            patch.object(integration, "EvchargoApi"),
            patch.object(integration, "EvchargoDataUpdateCoordinator", return_value=coordinator),
        ):
            self.assertTrue(await integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(order, ["listener", "platforms"])
