import mock

import utils

from core import utils as core_utils


class TestUtils(utils.BaseTestCase):

    @mock.patch.object(core_utils, 'CLIHelper')
    def test_get_date_secs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        self.assertEquals(core_utils.get_date_secs(), 1234)

    @mock.patch.object(core_utils, 'CLIHelper')
    def test_get_date_secs_from_timestamp(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        self.assertEquals(core_utils.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(core_utils, 'CLIHelper')
    def test_get_date_secs_from_timestamp_w_tz(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        self.assertEquals(core_utils.get_date_secs(date_string),
                          1616669705)
