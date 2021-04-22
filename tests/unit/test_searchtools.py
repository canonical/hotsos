import os

import mock

import utils

from common.searchtools import (
    FileSearcher,
    SearchDef,
    SearchResult,
)


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
