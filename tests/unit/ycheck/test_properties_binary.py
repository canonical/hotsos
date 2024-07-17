
from hotsos.core.host_helpers import (
    DPKGVersion
)
from hotsos.core.ycheck.engine.properties.requires.types import (
    binary,
)
from hotsos.core.plugins import juju

from .. import utils


class TestYamlRequiresTypeBinary(utils.BaseTestCase):
    """ Tests requires type binary property. """

    def test_binary_check_comparison(self):
        items = binary.BinCheckItems({'juju': [{'min': '3.0', 'max': '3.2'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertFalse(DPKGVersion.is_version_within_ranges(version,
                                                              versions))

        items = binary.BinCheckItems({'juju': [{'min': '2.9', 'max': '3.2'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertTrue(DPKGVersion.is_version_within_ranges(version,
                                                             versions))

        items = binary.BinCheckItems({'juju': [{'min': '2.9.2',
                                                'max': '2.9.22'}]},
                                     bin_handler=juju.JujuBinaryInterface)
        self.assertEqual(items.installed, ['juju'])
        self.assertEqual(items.not_installed, set())
        _bin, versions = list(items)[0]
        version = items.packaging_helper.get_version(_bin)
        self.assertTrue(DPKGVersion.is_version_within_ranges(version,
                                                             versions))
