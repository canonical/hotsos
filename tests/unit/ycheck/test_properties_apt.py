
import yaml
from hotsos.core.ycheck.engine.properties.requires.types import (
    apt,
)

from .. import utils

DPKG_L = """
ii  openssh-server                       1:8.2p1-4ubuntu0.4                                   amd64        secure shell (SSH) server, for secure access from remote machines
"""  # noqa


class TestYamlRequiresTypeAPT(utils.BaseTestCase):
    """ Tests requires type apt property. """

    @staticmethod
    def load_apt_requires(yaml_content):
        """ Load apt requires from YAML content. """
        return apt.YRequirementTypeAPT(
            "requires",
            "apt",
            yaml.safe_load(yaml_content),
            "requires.apt")

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria(self):
        """ Test apt requires with no version criteria. """
        content = r"""
        openssh-server:
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria_alt_form(self):
        """ Test apt requires with list form and no criteria. """
        content = r"""
        - openssh-server
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_no_criteria_name_mismatch(self):
        """ Test apt requires fails for nonexistent package. """
        # We expect test to fail because no such package exist.
        content = r"""
        openssh-serverx:
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_name_mismatch(self):
        """ Test apt requires with eq and wrong package name. """
        content = r"""
        openssh-serverx:
            - eq: '1:8.2p1-4ubuntu0.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_gt_single_true(self):
        """ Test apt gt comparison returns true. """
        content = r"""
        openssh-server:
            - gt: '1:8.2'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_gt_single_false(self):
        """ Test apt gt comparison returns false. """
        content = r"""
        openssh-server:
            - gt: '1:8.2p1-4ubuntu0.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_single_true(self):
        """ Test apt ge comparison returns true. """
        content = r"""
        openssh-server:
            - ge: '1:8.2'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_single_false(self):
        """ Test apt ge comparison returns false. """
        content = r"""
        openssh-server:
            - ge: '1:8.2p1-4ubuntu0.5'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_lt_single_true(self):
        """ Test apt lt comparison returns true. """
        content = r"""
        openssh-server:
            - lt: '1:8.2p1-4ubuntu0.5'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_lt_single_false(self):
        """ Test apt lt comparison returns false. """
        content = r"""
        openssh-server:
            - lt: '1:8.2p1-4ubuntu0.3'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_le_single_true(self):
        """ Test apt le comparison returns true. """
        content = r"""
        openssh-server:
            - le: '1:8.2p1-4ubuntu0.4'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_le_single_false(self):
        """ Test apt le comparison returns false. """
        content = r"""
        openssh-server:
            - le: '1:8.2p1-4ubuntu0.3'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_single_true(self):
        """ Test apt eq comparison returns true. """
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.4'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_single_false(self):
        """ Test apt eq comparison returns false. """
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.4.4'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_multiple_true(self):
        """ Test apt eq with multiple candidates, one matches. """
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.1'
            - eq: '1:8.2p1-4ubuntu0.2'
            - eq: '1:8.2p1-4ubuntu0.3'
            - eq: '1:8.2p1-4ubuntu0.4' # <-- should match this
            - eq: '1:8.2p1-4ubuntu0.5'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_eq_multiple_false(self):
        """ Test apt eq with multiple candidates, none match. """
        content = r"""
        openssh-server:
            - eq: '1:8.2p1-4ubuntu0.1'
            - eq: '1:8.2p1-4ubuntu0.2'
            - eq: '1:8.2p1-4ubuntu0.3'
            - eq: '1:8.2p1-4ubuntu0.5'
            - eq: '1:8.2p1-4ubuntu0.6'
        """
        self.assertFalse(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_ge_multiple(self):
        """ Test apt ge with multiple criteria including range. """
        content = r"""
        openssh-server:
            - ge: '1:8.9'
            - gt: '1:8.1' # <-- should match
              lt: '1:8.3'
        """
        self.assertTrue(self.load_apt_requires(content).result)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': DPKG_L})
    def test_apt_mixed(self):
        """ Test apt with mixed comparison operators, none match. """
        content = r"""
        openssh-server:
            - ge: '1:8.9 '
            - lt: '1:4'
            - ge: '1:6.3'
              lt: '1:7.2'
        """
        self.assertFalse(self.load_apt_requires(content).result)
