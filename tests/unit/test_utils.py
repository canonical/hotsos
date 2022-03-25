import mock

from tests.unit import utils

from core import utils as core_utils


class TestUtils(utils.BaseTestCase):

    @mock.patch.object(core_utils, 'CLIHelper')
    def test_get_date_secs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.date.return_value = "1234\n"
        self.assertEqual(core_utils.get_date_secs(), 1234)

    def test_get_date_secs_from_timestamp(self):
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        self.assertEqual(core_utils.get_date_secs(date_string),
                         1616691305)

    def test_get_date_secs_from_timestamp_w_tz(self):
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        self.assertEqual(core_utils.get_date_secs(date_string),
                         1616669705)

    def test_sample_set_regressions(self):
        samples = [1, 2, 3]
        self.assertEqual(core_utils.sample_set_regressions(samples), 0)
        samples = [1, 2, 3, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)
        samples = [1, 2, 3, 4, 1, 3]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)
        samples = [1, 2, 3, 4, 1, 4, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 2)
        samples = [1, 2, 1, 2, 1, 5, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 3)
        samples = [1, 1, 1, 2, 2, 2]
        self.assertEqual(core_utils.sample_set_regressions(samples), 0)
        samples = [1, 1, 1, 2, 2, 2, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples), 1)

        samples = [1, 1, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 0)
        samples = [2, 1, 1]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 0)
        samples = [2, 1, 2]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 1)
        samples = [100, 99, 98, 100, 60, 60]
        self.assertEqual(core_utils.sample_set_regressions(samples,
                                                           ascending=False), 1)
