import tempfile

from common import constants


def mktemp_dump(data):
    """Create a temporary file under the current plugin tmp directory and write
    data to the file.
    """
    ftmp = tempfile.mktemp(dir=constants.PLUGIN_TMP_DIR)
    with open(ftmp, 'w') as fd:
        fd.write(data)

    return ftmp
