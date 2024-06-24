import io

from hotsos.core.ycheck.engine.common import YDefsLoader

from . import utils


class TestYdefsLoaderRefs(utils.BaseTestCase):
    def test_yaml_def_seq_search(self):

        ydef = r"""
        a: 1
        x:
            y: ${a}
            z: ${x.y}
            t: ${a}${a}
        q: ${x.y}
        h: ${x.t}
        """
        ldr = YDefsLoader("none")
        content = ldr.load(io.StringIO(ydef))
        self.assertEqual(content["a"], 1)
        self.assertEqual(content["x"]["y"], "1")
        self.assertEqual(content["x"]["z"], "1")
        self.assertEqual(content["x"]["t"], "11")
        self.assertEqual(content["q"], "1")
        self.assertEqual(content["h"], "11")
