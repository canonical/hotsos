import pytest
from unittest.mock import patch, ANY

from charms.reactive import set_flag
from reactive import container_runtime_common


def patch_fixture(patch_target):
    @pytest.fixture()
    def _fixture():
        with patch(patch_target) as m:
            yield m
    return _fixture


check_call = patch_fixture('reactive.container_runtime_common.check_call')
hookenv = patch_fixture('reactive.container_runtime_common.hookenv')
install_ca = patch_fixture('charmhelpers.core.host.install_ca_cert')
status = patch_fixture('reactive.container_runtime_common.status')


def test_enable_cgroups(hookenv, check_call):
    """Verify expected flags for enable-groups config."""
    # Should not set a flag when config is false
    hookenv.config.return_value = {'enable-cgroups': False}
    container_runtime_common.enable_grub_cgroups()
    set_flag.assert_not_called()

    # Should set a flag when config is true
    hookenv.config.return_value = {'enable-cgroups': True}
    container_runtime_common.enable_grub_cgroups()
    set_flag.assert_called_once_with('cgroups.modified')


def test_install_custom_ca(hookenv, install_ca, status):
    """Verify we set a custom CA cert when appropriate."""
    # Should not block nor call install_ca_cert when no config is present
    hookenv.config.return_value = {}
    container_runtime_common.install_custom_ca()
    status.blocked.assert_not_called()
    install_ca.assert_not_called()

    status.reset_mock()
    install_ca.reset_mock()

    # Should block and not call install_ca_cert if called with bad data
    hookenv.config.return_value = {'custom-registry-ca': 'bad'}
    container_runtime_common.install_custom_ca()
    status.blocked.assert_called_once_with(ANY)
    install_ca.assert_not_called()

    status.reset_mock()
    install_ca.reset_mock()

    # Should call install_ca_cert and not block if called with good data
    hookenv.config.return_value = {'custom-registry-ca': 'Z29vZAo='}
    container_runtime_common.install_custom_ca()
    status.blocked.assert_not_called()
    install_ca.assert_called_once_with(ANY, name='juju-custom-registry')

    status.reset_mock()
    install_ca.reset_mock()
