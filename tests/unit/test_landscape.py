from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.landscape import summary

from . import utils

SYSTEMD_UNITS = """
  UNIT                                                                           LOAD   ACTIVE SUB       DESCRIPTION
  landscape-api.service                                                          loaded active running   LSB: Enable Landscape API
  landscape-appserver.service                                                    loaded active running   LSB: Enable Landscape frontend UI
  landscape-async-frontend.service                                               loaded active running   LSB: Enable Landscape async frontend
  landscape-job-handler.service                                                  loaded active running   LSB: Enable Landscape job handler
  landscape-msgserver.service                                                    loaded active running   LSB: Enable Landscape message processing
  landscape-package-upload.service                                               loaded active exited    LSB: Enable Landscape Package Upload service
  landscape-pingserver.service                                                   loaded active running   LSB: Enable Landscape ping server
"""  # noqa

SYSTEMD_UNIT_FILES = """
UNIT FILE                                    STATE           PRESET
landscape-api.service                        generated       -
landscape-appserver.service                  generated       -
landscape-async-frontend.service             generated       -
landscape-client.service                     enabled         enabled
landscape-hostagent-consumer.service         enabled         enabled
landscape-hostagent-messenger.service        enabled         enabled
landscape-job-handler.service                generated       -
landscape-msgserver.service                  generated       -
landscape-package-search.service             enabled         enabled
landscape-package-upload.service             generated       -
landscape-pingserver.service                 generated       -
landscape-secrets-service.service            enabled         enabled
landscape_api.service                        alias           -
landscape_appserver.service                  alias           -
landscape_async_frontend.service             alias           -
landscape_job_handler.service                alias           -
landscape_msgserver.service                  alias           -
landscape_package_upload.service             alias           -
landscape_pingserver.service                 alias           -
"""  # noqa

LANDSCAPE_DPKG = """
ii  landscape-client                24.04-0landscape0                       amd64        Landscape administration system client
ii  landscape-common                24.04-0landscape0                       amd64        Landscape administration system client - Common files
ii  landscape-hashids               23.10+8-landscape0                      all          initial package databases for landscape-server
ii  landscape-server                24.04.6-0landscape0                     amd64        computer management and monitoring service
"""  # noqa


class LandscapeTestsBase(utils.BaseTestCase):
    """ Custom base testcase that sets Landscape plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'landscape'


class TestLandscapeSummary(LandscapeTestsBase):
    """ Unit tests for Landscape summary """
    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': LANDSCAPE_DPKG})
    def test_dpkg(self):
        inst = summary.LandscapeSummary()
        expected = {'dpkg': ['landscape-client 24.04-0landscape0',
                             'landscape-common 24.04-0landscape0',
                             'landscape-hashids 23.10+8-landscape0',
                             'landscape-server 24.04.6-0landscape0']}
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l': '',
                             'sos_commands/systemd/systemctl_list-unit-files':
                             SYSTEMD_UNIT_FILES,
                             'sos_commands/systemd/systemctl_list-units':
                             SYSTEMD_UNITS})
    def test_services(self):
        with mock.patch('hotsos.core.plugins.landscape.LandscapeChecks',
                        'is_installed', lambda: True):
            expected = {'services': {
                            'ps': [],
                            'systemd': {
                                'enabled': ['landscape-client',
                                            'landscape-hostagent-consumer',
                                            'landscape-hostagent-messenger',
                                            'landscape-package-search',
                                            'landscape-secrets-service'],
                                'generated': ['landscape-api',
                                              'landscape-appserver',
                                              'landscape-async-frontend',
                                              'landscape-job-handler',
                                              'landscape-msgserver',
                                              'landscape-package-upload',
                                              'landscape-pingserver']}}}

            inst = summary.LandscapeSummary()
            self.assertEqual(self.part_output_to_actual(inst.output), expected)


@utils.load_templated_tests('scenarios/landscape')
class TestLandscapeScenarios(LandscapeTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
