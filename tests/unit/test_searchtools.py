import glob
import os
import multiprocessing
import tempfile

from unittest import mock

from . import utils

from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.searchtools import (
    FileSearcher,
    SearchDef,
    SearchResult,
    SequenceSearchDef,
)

FILTER_TEST_1 = """blah blah ERROR blah
blah blah ERROR blah
blah blah INFO blah
"""

SEQ_TEST_1 = """a start point
leads to
an ending
"""

SEQ_TEST_2 = """a start point
another start point
leads to
an ending
"""

SEQ_TEST_3 = """a start point
another start point
leads to
an ending
a start point
"""

SEQ_TEST_4 = """a start point
another start point
value is 3
"""

SEQ_TEST_5 = """a start point
another start point
value is 3

another start point
value is 4
"""

SEQ_TEST_6 = """section 1
1_1
1_2
section 2
2_1
"""

SEQ_TEST_7 = """section 1
1_1
1_2
section 2
2_1
section 3
3_1
"""

MULTI_SEQ_TEST = """
sectionB 1
1_1
sectionA 1
1_1
sectionB 2
2_2
sectionA 2
2_1
"""


class TestSearchTools(utils.BaseTestCase):

    @mock.patch.object(os, "environ", {})
    @mock.patch.object(os, "cpu_count")
    def test_filesearcher_num_cpus_no_override(self, mock_cpu_count):
        mock_cpu_count.return_value = 3
        with mock.patch.object(FileSearcher, 'num_files_to_search', 4):
            s = FileSearcher()
            self.assertEqual(s.num_cpus, 3)

    @mock.patch.object(os, "environ", {})
    @mock.patch.object(os, "cpu_count")
    def test_filesearcher_num_cpus_files_capped(self, mock_cpu_count):
        mock_cpu_count.return_value = 3
        with mock.patch.object(FileSearcher, 'num_files_to_search', 2):
            s = FileSearcher()
            self.assertEqual(s.num_cpus, 2)

    @mock.patch.object(os, "cpu_count")
    def test_filesearcher_num_cpus_w_override(self, mock_cpu_count):
        setup_config(MAX_PARALLEL_TASKS=2)
        mock_cpu_count.return_value = 3
        with mock.patch.object(FileSearcher, 'num_files_to_search', 4):
            s = FileSearcher()
            self.assertEqual(s.num_cpus, 2)

    def test_filesearcher_logs(self):
        expected = {9891: '2022-02-09 22:50:18.131',
                    9892: '2022-02-09 22:50:19.703'}

        logs_root = "var/log/neutron/"
        filepath = os.path.join(HotSOSConfig.DATA_ROOT, logs_root,
                                'neutron-openvswitch-agent.log.2.gz')
        globpath = os.path.join(HotSOSConfig.DATA_ROOT, logs_root,
                                'neutron-l3-agent.log')
        globpath_file1 = os.path.join(HotSOSConfig.DATA_ROOT, logs_root,
                                      'neutron-l3-agent.log')
        globpath_file2 = os.path.join(HotSOSConfig.DATA_ROOT, logs_root,
                                      'neutron-l3-agent.log.1.gz')

        s = FileSearcher()
        sd = SearchDef(r'^(\S+\s+[0-9:\.]+)\s+.+full sync.+', tag="T1")
        s.add_search_term(sd, filepath)
        sd = SearchDef(r'^(\S+\s+[0-9:\.]+)\s+.+ERROR.+', tag="T2")
        s.add_search_term(sd, filepath)
        sd = SearchDef((r'^(\S+\s+[0-9:\.]+)\s+.+ INFO .+ Router [0-9a-f\-]+'
                        '.+'), tag="T3")
        s.add_search_term(sd, globpath)
        sd = SearchDef(r'non-existant-pattern', tag="T4")
        # search for something that doesn't exist to test that code path
        s.add_search_term(sd, globpath)

        results = s.search()
        self.assertEqual(set(results.files), set([filepath, globpath]))

        self.assertEqual(len(results.find_by_path(filepath)), 1220)

        tag_results = results.find_by_tag("T1", path=filepath)
        self.assertEqual(len(tag_results), 2)
        for result in tag_results:
            ln = result.linenumber
            self.assertEqual(result.tag, "T1")
            self.assertEqual(result.get(1), expected[ln])

        tag_results = results.find_by_tag("T1")
        self.assertEqual(len(tag_results), 2)
        for result in tag_results:
            ln = result.linenumber
            self.assertEqual(result.tag, "T1")
            self.assertEqual(result.get(1), expected[ln])

        self.assertEqual(len(results.find_by_path(globpath_file1)), 1)
        self.assertEqual(len(results.find_by_path(globpath_file2)), 0)

        # these files have the same content so expect same result from both
        expected = {5380: '2022-02-10 16:09:22.641'}
        path_results = results.find_by_path(globpath_file1)
        for result in path_results:
            ln = result.linenumber
            self.assertEqual(result.tag, "T3")
            self.assertEqual(result.get(1), expected[ln])

        path_results = results.find_by_path(globpath_file2)
        for result in path_results:
            ln = result.linenumber
            self.assertEqual(result.tag, "T3")
            self.assertEqual(result.get(1), expected[ln])

    def test_filesearcher_network_info(self):
        filepath = os.path.join(HotSOSConfig.DATA_ROOT, 'sos_commands',
                                'networking', 'ip_-d_address')
        filepath2 = os.path.join(HotSOSConfig.DATA_ROOT, 'sos_commands',
                                 'networking', 'ip_-s_-d_link')
        ip = "10.0.0.128"
        mac = "22:c2:7b:1c:12:1b"
        s = FileSearcher()
        sd = SearchDef(r".+({}).+".format(ip))
        s.add_search_term(sd, filepath)
        sd = SearchDef(r"^\s+link/ether\s+({})\s+.+".format(mac))
        s.add_search_term(sd, filepath2)

        results = s.search()
        self.assertEqual(set(results.files), set([filepath, filepath2]))
        self.assertEqual(len(results.find_by_path(filepath)), 1)
        self.assertEqual(len(results.find_by_path(filepath2)), 2)

        self.assertEqual(results.find_by_path(filepath)[0].linenumber, 38)
        for result in results.find_by_path(filepath):
            self.assertEqual(result.get(1), ip)

        expected = {52: mac,
                    141: mac}

        for result in results.find_by_path(filepath2):
            ln = result.linenumber
            self.assertEqual(result.tag, None)
            self.assertEqual(result.get(1), expected[ln])

    def test_filesearcher_error(self):
        s = FileSearcher()
        with mock.patch.object(SearchResult, '__init__') as mock_init:

            def fake_init(*args, **kwargs):
                raise EOFError("some error")

            mock_init.side_effect = fake_init
            path = os.path.join(HotSOSConfig.DATA_ROOT)
            s.add_search_term(SearchDef("."), path)
            s.search()

    def test_filesearch_filesort(self):
        ordered_contents = []
        with tempfile.TemporaryDirectory() as dtmp:
            os.mknod(os.path.join(dtmp, "my-test-agent.log"))
            ordered_contents.append("my-test-agent.log")
            os.mknod(os.path.join(dtmp, "my-test-agent.log.1"))
            ordered_contents.append("my-test-agent.log.1")
            # add in an erroneous file that does not follow logrotate format
            os.mknod(os.path.join(dtmp, "my-test-agent.log.tar.gz"))
            for i in range(2, 100):
                fname = "my-test-agent.log.{}.gz".format(i)
                os.mknod(os.path.join(dtmp, fname))
                ordered_contents.append(fname)
                self.assertEqual(FileSearcher().logrotate_file_sort(fname), i)

            ordered_contents.append("my-test-agent.log.tar.gz")

            contents = os.listdir(dtmp)
            self.assertEqual(sorted(contents,
                                    key=FileSearcher().logrotate_file_sort),
                             ordered_contents)

    def test_filesearch_glob_filesort(self):
        dir_contents = []
        with tempfile.TemporaryDirectory() as dtmp:
            dir_contents.append(os.path.join(dtmp, "my-test-agent.0.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.1.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.1.log.1"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.2.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.16.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.49.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.49.log.1"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.77.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.100.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.100.log.1"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.110.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.142.log"))
            dir_contents.append(os.path.join(dtmp, "my-test-agent.183.log"))
            for e in dir_contents:
                os.mknod(e)

            for i in range(2, HotSOSConfig.MAX_LOGROTATE_DEPTH + 10):
                fname = os.path.join(dtmp,
                                     "my-test-agent.1.log.{}.gz".format(i))
                os.mknod(fname)
                if i <= HotSOSConfig.MAX_LOGROTATE_DEPTH:
                    dir_contents.append(fname)

            for i in range(2, HotSOSConfig.MAX_LOGROTATE_DEPTH + 10):
                fname = os.path.join(dtmp,
                                     "my-test-agent.49.log.{}.gz".format(i))
                os.mknod(fname)
                if i <= HotSOSConfig.MAX_LOGROTATE_DEPTH:
                    dir_contents.append(fname)

            for i in range(2, HotSOSConfig.MAX_LOGROTATE_DEPTH + 10):
                fname = os.path.join(dtmp,
                                     "my-test-agent.100.log.{}.gz".format(i))
                os.mknod(fname)
                if i <= HotSOSConfig.MAX_LOGROTATE_DEPTH:
                    dir_contents.append(fname)

            exp = sorted(dir_contents)
            path = os.path.join(dtmp, 'my-test-agent*.log*')
            act = sorted(FileSearcher().filtered_paths(glob.glob(path)))
            self.assertEqual(act, exp)

    @utils.create_test_files({'atestfile': SEQ_TEST_1})
    def test_sequence_searcher(self):
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(
                                             r"^a\S* (start\S*) point\S*"),
                               body=SearchDef(r"leads to"),
                               end=SearchDef(r"^an (ending)$"),
                               tag="seq-search-test1")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 1)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "start")
                elif r.tag == sd.end_tag:
                    self.assertEqual(r.get(1), "ending")

    @utils.create_test_files({'atestfile': SEQ_TEST_2})
    def test_sequence_searcher_overlapping(self):
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(
                                           r"^(a\S*) (start\S*) point\S*"),
                               body=SearchDef(r"leads to"),
                               end=SearchDef(r"^an (ending)$"),
                               tag="seq-search-test2")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 1)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "another")
                elif r.tag == sd.end_tag:
                    self.assertEqual(r.get(1), "ending")

    @utils.create_test_files({'atestfile': SEQ_TEST_3})
    def test_sequence_searcher_overlapping_incomplete(self):
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(
                                           r"^(a\S*) (start\S*) point\S*"),
                               body=SearchDef(r"leads to"),
                               end=SearchDef(r"^an (ending)$"),
                               tag="seq-search-test3")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 1)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "another")
                elif r.tag == sd.end_tag:
                    self.assertEqual(r.get(1), "ending")

    @utils.create_test_files({'atestfile': SEQ_TEST_4})
    def test_sequence_searcher_incomplete_eof_match(self):
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(
                                           r"^(a\S*) (start\S*) point\S*"),
                               body=SearchDef(r"value is (\S+)"),
                               end=SearchDef(r"^$"),
                               tag="seq-search-test4")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 1)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "another")
                elif r.tag == sd.body_tag:
                    self.assertEqual(r.get(1), "3")
                elif r.tag == sd.end_tag:
                    self.assertEqual(r.get(0), "")

    @utils.create_test_files({'atestfile': SEQ_TEST_5})
    def test_sequence_searcher_multiple_sections(self):
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(
                                           r"^(a\S*) (start\S*) point\S*"),
                               body=SearchDef(r"value is (\S+)"),
                               end=SearchDef(r"^$"),
                               tag="seq-search-test5")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 2)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "another")
                elif r.tag == sd.body_tag:
                    self.assertTrue(r.get(1) in ["3", "4"])
                elif r.tag == sd.end_tag:
                    self.assertEqual(r.get(0), "")

    @utils.create_test_files({'atestfile': SEQ_TEST_6})
    def test_sequence_searcher_eof(self):
        """
        Test scenario:
         * multiple sections that end with start of the next
         * start def matches any start
         * end def matches any start
         * file ends before start of next
        """
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^section (\d+)"),
                               body=SearchDef(r"\d_\d"),
                               tag="seq-search-test6")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 2)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    section = r.get(1)
                    self.assertTrue(r.get(1) in ["1", "2"])
                elif r.tag == sd.body_tag:
                    if section == "1":
                        self.assertTrue(r.get(0) in ["1_1", "1_2"])
                    else:
                        self.assertTrue(r.get(0) in ["2_1"])

    @utils.create_test_files({'atestfile': SEQ_TEST_7})
    def test_sequence_searcher_section_start_end_same(self):
        """
        Test scenario:
         * multiple sections that end with start of the next
         * start def matches unique start
         * end def matches any start
        """
        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^section (2)"),
                               body=SearchDef(r"\d_\d"),
                               end=SearchDef(
                                           r"^section (\d+)"),
                               tag="seq-search-test7")
        s.add_search_term(sd,
                          path=os.path.join(HotSOSConfig.DATA_ROOT,
                                            'atestfile'))
        results = s.search()
        sections = results.find_sequence_sections(sd)
        self.assertEqual(len(sections), 1)
        for id in sections:
            for r in sections[id]:
                if r.tag == sd.start_tag:
                    self.assertEqual(r.get(1), "2")
                elif r.tag == sd.body_tag:
                    self.assertTrue(r.get(0) in ["2_1"])

    @utils.create_test_files({'atestfile': MULTI_SEQ_TEST})
    def test_sequence_searcher_multi_sequence(self):
        """
        Test scenario:
         * search containing multiple seqeunce definitions
         * data containing 2 results of each where one is incomplete
         * test that single incomplete result gets removed
        """
        s = FileSearcher()
        sdA = SequenceSearchDef(start=SearchDef(r"^sectionA (\d+)"),
                                body=SearchDef(r"\d_\d"),
                                end=SearchDef(
                                            r"^section\S+ (\d+)"),
                                tag="seqA-search-test")
        sdB = SequenceSearchDef(start=SearchDef(r"^sectionB (\d+)"),
                                body=SearchDef(r"\d_\d"),
                                end=SearchDef(
                                            r"^section\S+ (\d+)"),
                                tag="seqB-search-test")
        fname = os.path.join(HotSOSConfig.DATA_ROOT, 'atestfile')
        s.add_search_term(sdA, path=fname)
        s.add_search_term(sdB, path=fname)
        results = s.search()
        sections = results.find_sequence_sections(sdA)
        self.assertEqual(len(sections), 1)
        sections = results.find_sequence_sections(sdB)
        self.assertEqual(len(sections), 2)
