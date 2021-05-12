import os

import mock
import tempfile

import utils

from common.searchtools import (
    FileSearcher,
    SearchDef,
    SearchResult,
    SequenceSearchDef,
)

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


class TestSearchTools(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(os, "environ", {})
    @mock.patch.object(os, "cpu_count")
    def test_filesearcher_num_cpus_no_override(self, mock_cpu_count):
        mock_cpu_count.return_value = 3
        s = FileSearcher()
        self.assertEquals(s.num_cpus, 3)

    @mock.patch.object(os, "environ", {"USER_MAX_PARALLEL_TASKS": 2})
    @mock.patch.object(os, "cpu_count")
    def test_filesearcher_num_cpus_w_override(self, mock_cpu_count):
        mock_cpu_count.return_value = 3
        s = FileSearcher()
        self.assertEquals(s.num_cpus, 2)

    def test_filesearcher_logs(self):
        expected = {4: '2021-02-25 14:22:18.861',
                    16: '2021-02-25 14:22:19.587'}

        logs_root = "var/log/neutron/"
        filepath = os.path.join(os.environ["DATA_ROOT"], logs_root,
                                'neutron-openvswitch-agent.log')
        globpath = os.path.join(os.environ["DATA_ROOT"], logs_root,
                                'neutron-l3-agent.log*')
        globpath_file1 = os.path.join(os.environ["DATA_ROOT"], logs_root,
                                      'neutron-l3-agent.log')
        globpath_file2 = os.path.join(os.environ["DATA_ROOT"], logs_root,
                                      'neutron-l3-agent.log.1.gz')

        s = FileSearcher()
        sd = SearchDef(r'^(\S+\s+[0-9:\.]+)\s+.+full sync.+', tag="T1")
        s.add_search_term(sd, filepath)
        sd = SearchDef(r'^(\S+\s+[0-9:\.]+)\s+.+ERROR.+', tag="T2")
        s.add_search_term(sd, filepath)
        sd = SearchDef((r'^(\S+\s+[0-9:\.]+)\s+.+ INFO .+ Router '
                        '9b8efc4c-305b-48ce-a5bd-624bc5eeee67.+'), tag="T3")
        s.add_search_term(sd, globpath)
        sd = SearchDef(r'non-existant-pattern', tag="T4")
        # search for something that doesn't exist to test that code path
        s.add_search_term(sd, globpath)

        results = s.search()
        self.assertEquals(set(results.files), set([filepath,
                                                   globpath_file2,
                                                   globpath_file1]))

        self.assertEquals(len(results.find_by_path(filepath)), 37)

        tag_results = results.find_by_tag("T1", path=filepath)
        self.assertEquals(len(tag_results), 2)
        for result in tag_results:
            ln = result.linenumber
            self.assertEquals(result.tag, "T1")
            self.assertEquals(result.get(1), expected[ln])

        tag_results = results.find_by_tag("T1")
        self.assertEquals(len(tag_results), 2)
        for result in tag_results:
            ln = result.linenumber
            self.assertEquals(result.tag, "T1")
            self.assertEquals(result.get(1), expected[ln])

        self.assertEquals(len(results.find_by_path(globpath_file1)), 1)
        self.assertEquals(len(results.find_by_path(globpath_file2)), 0)

        # these files have the same content so expect same result from both
        expected = {81: '2021-03-25 18:10:15.179'}
        path_results = results.find_by_path(globpath_file1)
        for result in path_results:
            ln = result.linenumber
            self.assertEquals(result.tag, "T3")
            self.assertEquals(result.get(1), expected[ln])

        path_results = results.find_by_path(globpath_file2)
        for result in path_results:
            ln = result.linenumber
            self.assertEquals(result.tag, "T3")
            self.assertEquals(result.get(1), expected[ln])

    def test_filesearcher_network_info(self):
        filepath = os.path.join(os.environ["DATA_ROOT"], 'sos_commands',
                                'networking', 'ip_-d_address')
        filepath2 = os.path.join(os.environ["DATA_ROOT"], 'sos_commands',
                                 'networking', 'ip_-s_-d_link')
        ip = "10.10.101.33"
        mac = "ac:1f:6b:9e:d8:44"
        s = FileSearcher()
        sd = SearchDef(r".+({}).+".format(ip))
        s.add_search_term(sd, filepath)
        sd = SearchDef(r"^\s+link/ether\s+({})\s+.+".format(mac))
        s.add_search_term(sd, filepath2)

        results = s.search()
        self.assertEquals(set(results.files), set([filepath, filepath2]))
        self.assertEquals(len(results.find_by_path(filepath)), 1)
        self.assertEquals(len(results.find_by_path(filepath2)), 3)

        self.assertEquals(results.find_by_path(filepath)[0].linenumber, 16)
        for result in results.find_by_path(filepath):
            self.assertEquals(result.get(1), ip)

        expected = {8: mac,
                    15: mac,
                    22: mac}

        for result in results.find_by_path(filepath2):
            ln = result.linenumber
            self.assertEquals(result.tag, None)
            self.assertEquals(result.get(1), expected[ln])

    def test_filesearcher_error(self):
        s = FileSearcher()
        with mock.patch.object(SearchResult, '__init__') as mock_init:

            def fake_init(*args, **kwargs):
                raise EOFError("some error")

            mock_init.side_effect = fake_init
            path = os.path.join(os.environ["DATA_ROOT"])
            s.add_search_term(SearchDef("."), path)
            s.search()

    def test_sequence_searcher(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_1)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(
                                                 r"^a\S* (start\S*) point\S*"),
                                   body=SearchDef(r"leads to"),
                                   end=SearchDef(r"^an (ending)$"),
                                   tag="seq-search-test1")
            s.add_search_term(sd, path=ftmp.name)
            results = s.search()
            sections = results.find_sequence_sections(sd)
            self.assertEqual(len(sections), 1)
            for id in sections:
                for r in sections[id]:
                    if r.tag == sd.start_tag:
                        self.assertEqual(r.get(1), "start")
                    elif r.tag == sd.end_tag:
                        self.assertEqual(r.get(1), "ending")

            os.remove(ftmp.name)

    def test_sequence_searcher_overlapping(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_2)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(
                                               r"^(a\S*) (start\S*) point\S*"),
                                   body=SearchDef(r"leads to"),
                                   end=SearchDef(r"^an (ending)$"),
                                   tag="seq-search-test2")
            s.add_search_term(sd, path=ftmp.name)
            results = s.search()
            sections = results.find_sequence_sections(sd)
            self.assertEqual(len(sections), 1)
            for id in sections:
                for r in sections[id]:
                    if r.tag == sd.start_tag:
                        self.assertEqual(r.get(1), "another")
                    elif r.tag == sd.end_tag:
                        self.assertEqual(r.get(1), "ending")

            os.remove(ftmp.name)

    def test_sequence_searcher_overlapping_incomplete(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_3)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(
                                               r"^(a\S*) (start\S*) point\S*"),
                                   body=SearchDef(r"leads to"),
                                   end=SearchDef(r"^an (ending)$"),
                                   tag="seq-search-test3")
            s.add_search_term(sd, path=ftmp.name)
            results = s.search()
            sections = results.find_sequence_sections(sd)
            self.assertEqual(len(sections), 1)
            for id in sections:
                for r in sections[id]:
                    if r.tag == sd.start_tag:
                        self.assertEqual(r.get(1), "another")
                    elif r.tag == sd.end_tag:
                        self.assertEqual(r.get(1), "ending")

            os.remove(ftmp.name)

    def test_sequence_searcher_incomplete_eof_match(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_4)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(
                                               r"^(a\S*) (start\S*) point\S*"),
                                   body=SearchDef(r"value is (\S+)"),
                                   end=SearchDef(r"^$"),
                                   tag="seq-search-test4")
            s.add_search_term(sd, path=ftmp.name)
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

            os.remove(ftmp.name)

    def test_sequence_searcher_multiple_sections(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_5)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(
                                               r"^(a\S*) (start\S*) point\S*"),
                                   body=SearchDef(r"value is (\S+)"),
                                   end=SearchDef(r"^$"),
                                   tag="seq-search-test5")
            s.add_search_term(sd, path=ftmp.name)
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

            os.remove(ftmp.name)

    def test_sequence_searcher_eof(self):
        """
        Test scenario:
         * multiple sections that end with start of the next
         * start def matches any start
         * end def matches any start
         * file ends before start of next
        """
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_6)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(r"^section (\d+)"),
                                   body=SearchDef(r"\d_\d"),
                                   tag="seq-search-test6")
            s.add_search_term(sd, path=ftmp.name)
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

            os.remove(ftmp.name)

    def test_sequence_searcher_section_start_end_same(self):
        """
        Test scenario:
         * multiple sections that end with start of the next
         * start def matches unique start
         * end def matches any start
        """
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            ftmp.write(SEQ_TEST_7)
            ftmp.close()
            s = FileSearcher()
            sd = SequenceSearchDef(start=SearchDef(r"^section (2)"),
                                   body=SearchDef(r"\d_\d"),
                                   end=SearchDef(
                                               r"^section (\d+)"),
                                   tag="seq-search-test7")
            s.add_search_term(sd, path=ftmp.name)
            results = s.search()
            sections = results.find_sequence_sections(sd)
            self.assertEqual(len(sections), 1)
            for id in sections:
                for r in sections[id]:
                    if r.tag == sd.start_tag:
                        self.assertEqual(r.get(1), "2")
                    elif r.tag == sd.body_tag:
                        self.assertTrue(r.get(0) in ["2_1"])

            os.remove(ftmp.name)
