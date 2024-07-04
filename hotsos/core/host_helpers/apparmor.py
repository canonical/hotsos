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


class AAProfile():

    def __init__(self, name):
        self.name = name
        self.mode = ApparmorHelper().get_profile_mode(name)


class ApparmorHelper():

    @cached_property
    def profiles(self):
        """
        Fetch all profiles and their mode from apparmor_status.

        @return: dictionary of {<mode>: {'profiles': <list>, 'count': <int>}}
        """
        s = FileSearcher()
        seqdef = SequenceSearchDef(
                     start=SearchDef(r"(\d+) profiles are in (\S+) mode."),
                     body=SearchDef(r"\s+(\S+)"),
                     tag="aastatus")
        info = {}
        with CLIHelperFile() as cli:
            s.add(seqdef, path=cli.apparmor_status())
            results = s.run()
            for section in results.find_sequence_sections(seqdef).values():
                count = 0
                mode = None
                for result in section:
                    if result.tag == seqdef.start_tag:
                        count = int(result.get(1))
                        mode = result.get(2)
                        if mode not in info:
                            info[mode] = {'profiles': [], 'count': count}
                    elif result.tag == seqdef.body_tag:
                        if count == 0:
                            continue

                        info[mode]['profiles'].append(result.get(1))

        return info

    def get_profile_mode(self, name):
        for mode, profiles in self.profiles.items():
            if name in profiles['profiles']:
                return mode

        return None

    @property
    def profiles_enforce(self):
        return self.profiles.get('enforce', {}).get('profiles', [])

    @property
    def profiles_complain(self):
        return self.profiles.get('complain', {}).get('profiles', [])

    @property
    def profiles_kill(self):
        return self.profiles.get('kill', {}).get('profiles', [])

    @property
    def profiles_unconfined(self):
        return self.profiles.get('unconfined', {}).get('profiles', [])


class AAProfileFactory(FactoryBase):
    """
    Dynamically create AAProfile objects using profile name.
    """

    def __getattr__(self, profile):
        return AAProfile(profile)
