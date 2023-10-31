from hotsos.core import utils as core_utils

from . import utils


class TestUtils(utils.BaseTestCase):

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

    def test_sort_suffixed_integers(self):
        self.assertEqual(core_utils.sort_suffixed_integers(
                         [1, '300', 2]),
                         [1, 2, '300'])
        self.assertEqual(core_utils.sort_suffixed_integers(
                         [1, '300', 2], reverse=True),
                         ['300', 2, 1])
        self.assertEqual(core_utils.sort_suffixed_integers(
                         ['1', '3', '2']),
                         ['1', '2', '3'])
        self.assertEqual(core_utils.sort_suffixed_integers(
                         [1, 3, '22k', '111k']),
                         [1, 3, '22k', '111k'])
        self.assertEqual(core_utils.sort_suffixed_integers(
                         [1, 3, '22k', '111k'], reverse=True),
                         ['111k', '22k', 3, 1])

        melange = ['111k', '22k', '12P', 3, '1', '0.0k', '0.002k', '3g']
        self.assertEqual(core_utils.sort_suffixed_integers(
                         melange, reverse=True),
                         ['12P', '3g', '111k', '22k', 3, '0.002k', '1',
                          '0.0k'])
        self.assertEqual(core_utils.sort_suffixed_integers(
                         melange, reverse=False),
                         ['0.0k', '1', '0.002k', 3, '22k', '111k', '3g',
                          '12P'])
