from unittest.mock import patch, Mock

import pytest

from reactive.vault_kv import update_app_kv_hashes
from charms.layer.vault_kv import VaultAppKV


@pytest.fixture()
def mock_vault_config():
    with patch(
        "charms.layer.vault_kv.get_vault_config",
        return_value={
            "secret_backend": "charm-unit-test",
            "vault_url": "http://vault",
            "role_id": 1234,
            "secret_id": "super-secret",
        },
    ) as vc:
        yield vc


@pytest.fixture()
def destroy_vault_kv():
    """Teardown singleton instance created in each unit test."""
    yield
    del VaultAppKV._singleton_instance


@patch("hvac.Client", autospec=True)
@patch("charmhelpers.core.hookenv.local_unit", Mock(return_value="unit-test/0"))
@patch("charmhelpers.core.hookenv.is_leader", Mock(return_value=True))
@patch("charmhelpers.core.hookenv.leader_set")
def test_update_app_kv_hashes_leader(
    mock_leader_set, mock_hvac_client, mock_vault_config, destroy_vault_kv
):
    def mock_read(path):
        if path == "charm-unit-test/kv/app":
            return dict(data={"tested-key": "tested-value"})
        elif path == "charm-unit-test/kv/app-hashes/0":
            return {}

    client = mock_hvac_client.return_value
    client.read.side_effect = mock_read

    # --------------------------------
    # exit #1
    # Both leader_set and update_hashes should be executed
    update_app_kv_hashes()
    client.write.assert_called_once_with(
        "charm-unit-test/kv/app-hashes/0",
        **{"tested-key": "b40d0066377d3ec7015ab9f498699940"}
    )
    mock_leader_set.assert_called_once()

    # --------------------------------
    # exit #2
    # Neither leader_set nor update_hashes should be executed
    mock_leader_set.reset_mock()
    client.write.reset_mock()
    update_app_kv_hashes()
    client.write.assert_not_called()
    mock_leader_set.assert_not_called()


@patch("hvac.Client", autospec=True)
@patch("charmhelpers.core.hookenv.local_unit", Mock(return_value="unit-test/0"))
@patch("charmhelpers.core.hookenv.is_leader", Mock(return_value=False))
@patch("charmhelpers.core.hookenv.leader_set")
def test_update_app_kv_hashes_follower(
    mock_leader_set, mock_hvac_client, mock_vault_config, destroy_vault_kv
):
    def mock_read(path):
        if path == "charm-unit-test/kv/app":
            return dict(data={"tested-key": "tested-value"})
        elif path == "charm-unit-test/kv/app-hashes/0":
            return {}

    client = mock_hvac_client.return_value
    client.read.side_effect = mock_read

    # --------------------------------
    # exit #1
    # Only update_hashes should be executed, not leader_set
    update_app_kv_hashes()
    client.write.assert_called_once_with(
        "charm-unit-test/kv/app-hashes/0",
        **{"tested-key": "b40d0066377d3ec7015ab9f498699940"}
    )
    mock_leader_set.assert_not_called()

    # --------------------------------
    # exit #2
    # Neither leader_set nor update_hashes should be executed
    mock_leader_set.reset_mock()
    client.write.reset_mock()
    update_app_kv_hashes()
    client.write.assert_not_called()
    mock_leader_set.assert_not_called()
