from functools import cached_property

# NOTE: we import direct from searchkit rather than hotsos.core.search to
#       avoid circular dependency issues.
from searchkit import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers.cli import CLIHelperFile


class AAProfile(object):

    def __init__(self, name):
        self.name = name
        self.mode = ApparmorHelper().get_profile_mode(name)


class ApparmorHelper(object):

    @cached_property
    def profiles(self):
        """
        Fetch all profiles and their mode from apparmor_status.

        @return: dictionary of {<mode>: {'profiles': <list>, 'count': <int>}}
        """
        s = FileSearcher()
        seqdef = SequenceSearchDef(
                            start=SearchDef(r"(\d+) (\S+) are in (\S+) mode."),
                            body=SearchDef(r"\s+(\S+)"),
                            tag="aastatus")
        info = {}
        with CLIHelperFile() as cli:
            s.add(seqdef, path=cli.apparmor_status())
            results = s.run()
            for section in results.find_sequence_sections(seqdef).values():
                count = 0
                mode = None
                is_profiles = False
                for result in section:
                    if result.tag == seqdef.start_tag:
                        count = int(result.get(1))
                        is_profiles = result.get(2) == 'profiles'
                        mode = result.get(3)
                        if mode not in info:
                            info[mode] = {'profiles': [], 'count': count}
                    elif result.tag == seqdef.body_tag:
                        if not is_profiles or count == 0:
                            continue

                        info[mode]['profiles'].append(result.get(1))

        return info

    def get_profile_mode(self, name):
        for mode, profiles in self.profiles.items():
            if name in profiles['profiles']:
                return mode

    @property
    def profiles_enforce(self):
        return self.profiles.get('enforce', {}).get('profiles', [])

    @property
    def profiles_complain(self):
        return self.profiles.get('complain', {}).get('profiles', [])


class AAProfileFactory(FactoryBase):
    """
    Dynamically create AAProfile objects using profile name.
    """

    def __getattr__(self, profile):
        return AAProfile(profile)
