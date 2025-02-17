from hotsos.core.ycheck.common import GlobalSearcherPreloaderBase

from .. import utils


class TestYcheckCommon(utils.BaseTestCase):
    """
    Tests common ycheck functionality.
    """

    def test_skip_filtered(self):
        pf = 'a.b.c'
        p = 'a.b.c.d'
        self.assertFalse(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.c.e'
        self.assertTrue(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.c'
        p = 'a.b'
        self.assertTrue(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.*'
        p = 'a.b.c'
        self.assertFalse(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
