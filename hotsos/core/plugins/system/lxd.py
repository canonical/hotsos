from hotsos.core.utils import cached_property, mktemp_dump
from hotsos.core.search.searchtools import (
    FileSearcher, SearchDef,
    SequenceSearchDef
)
from hotsos.core.host_helpers.cli import CLIHelper


class LXD(object):

    @cached_property
    def buginfo_tmpfile(self):
        out = CLIHelper().lxd_buginfo()
        return mktemp_dump(''.join(out))

    @cached_property
    def instances(self):
        """ Return a list of instance names. """
        _instances = []
        s = FileSearcher()
        seq = SequenceSearchDef(start=SearchDef(r'^## Instances$'),
                                body=SearchDef(r'^\|\s+(\S+)'),
                                end=SearchDef(r'##.*'),
                                tag='instances')
        s.add_search_term(seq, path=self.buginfo_tmpfile)
        results = s.search()
        for section in results.find_sequence_sections(seq).values():
            for r in section:
                if 'body' in r.tag:
                    if r.get(1) != 'NAME':
                        _instances.append(r.get(1))

        return _instances
