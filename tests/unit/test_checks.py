import utils

from common import checks


class TestChecks(utils.BaseTestCase):

    def setUp(self):
        # NOTE: remember that data_root is configured so helpers will always
        # use fake_data_root if possible. If you write a test that wants to
        # test scenario where no data root is set (i.e. no sosreport) you need
        # to unset it as part of the test.
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_APTPackageChecksBase(self):
        expected = ['python3-systemd 231-2build1',
                    'systemd 229-4ubuntu21.28',
                    'systemd-sysv 229-4ubuntu21.28']
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "229-4ubuntu21.28")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "1.2.32ubuntu0.2")

    def test_SnapPackageChecksBase(self):
        expected = ['core 16-2.48.2']
        obj = checks.SnapPackageChecksBase(["core"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core"), "16-2.48.2")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("juju"), "2.7.8")
