
from hotsos.core.host_helpers import apparmor as host_apparmor

from .. import utils


class TestApparmorHelper(utils.BaseTestCase):
    """ Unit tests for apparmor helper """
    def test_aa_status_profiles(self):
        helper = host_apparmor.ApparmorHelper()
        profiles = helper.profiles
        num_profiles = 2
        self.assertEqual(profiles['enforce']['count'], 253)
        self.assertEqual(len(profiles['enforce']['profiles']), 253)
        self.assertEqual(profiles['enforce']['profiles'][-1], 'virt-aa-helper')
        self.assertEqual(helper.profiles_enforce,
                         profiles['enforce']['profiles'])
        self.assertEqual(profiles['complain']['count'], 0)
        self.assertEqual(len(profiles['complain']['profiles']), 0)
        self.assertEqual(helper.profiles_complain, [])
        if 'kill' in profiles:
            num_profiles += 1
            self.assertEqual(profiles['kill']['count'], 0)
            self.assertEqual(len(profiles['kill']['profiles']), 0)
            self.assertEqual(helper.profiles_kill, [])
        if 'unconfined' in profiles:
            num_profiles += 1
            self.assertEqual(profiles['unconfined']['count'], 0)
            self.assertEqual(len(profiles['unconfined']['profiles']), 0)
            self.assertEqual(helper.profiles_unconfined, [])
        self.assertEqual(len(profiles), num_profiles)

    def test_aa_profile_factory(self):
        profile = getattr(host_apparmor.AAProfileFactory(),
                          'virt-aa-helper')
        self.assertEqual(profile.name, 'virt-aa-helper')
        self.assertEqual(profile.mode, 'enforce')
