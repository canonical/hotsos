import os
import utils

from common import searchtools


class TestSearchTools(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

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

        s = searchtools.FileSearcher()
        s.add_search_term(r'^(\S+\s+[0-9:\.]+)\s+.+full sync.+', [1], filepath,
                          tag="T1")
        s.add_search_term(r'^(\S+\s+[0-9:\.]+)\s+.+ERROR.+', [1], filepath,
                          tag="T2")
        s.add_search_term(r'^(\S+\s+[0-9:\.]+)\s+.+INFO.+', [1], globpath,
                          tag="T3")
        # search for something that doesn't exist to test that code path
        s.add_search_term(r'non-existant-pattern', [1], globpath,
                          tag="T4")

        results = s.search()
        self.assertEquals(set(results.files), set([filepath,
                                                   globpath_file2,
                                                   globpath_file1]))

        self.assertEquals(len(results.find_by_path(filepath)), 6)

        tag_results = results.find_by_tag(filepath, "T1")
        self.assertEquals(len(tag_results), 2)
        for result in tag_results:
            ln = result.linenumber
            self.assertEquals(result.tag, "T1")
            self.assertEquals(result.get(1), expected[ln])

        self.assertEquals(len(results.find_by_path(globpath_file1)), 1)
        self.assertEquals(len(results.find_by_path(globpath_file2)), 1)

        # these files have the same content so expect same result from both
        expected = {12: '2021-02-26 14:10:29.729'}
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
        s = searchtools.FileSearcher()
        s.add_search_term(r".+({}).+".format(ip), [1], filepath)
        s.add_search_term(r"^\s+link/ether\s+({})\s+.+".format(mac), [1],
                          filepath2)

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
