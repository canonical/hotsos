import platform
import os


def get_platform():
    """Return the current OS platform.

    For example: if current os platform is Ubuntu then a string "ubuntu"
    will be returned (which is the name of the module).
    This string is used to decide which platform module should be imported.
    """
    # linux_distribution is deprecated and will be removed in Python 3.7
    # Warnings *not* disabled, as we certainly need to fix this.
    if hasattr(platform, 'linux_distribution'):
        tuple_platform = platform.linux_distribution()
        current_platform = tuple_platform[0]
    else:
        current_platform = _get_platform_from_fs()

    if "Ubuntu" in current_platform:
        return "ubuntu"
    elif "CentOS" in current_platform:
        return "centos"
    elif "debian" in current_platform:
        # Stock Python does not detect Ubuntu and instead returns debian.
        # Or at least it does in some build environments like Travis CI
        return "ubuntu"
    elif "elementary" in current_platform:
        # ElementaryOS fails to run tests locally without this.
        return "ubuntu"
    elif "Pop!_OS" in current_platform:
        # Pop!_OS also fails to run tests locally without this.
        return "ubuntu"
    else:
        raise RuntimeError("This module is not supported on {}."
                           .format(current_platform))


def _get_platform_from_fs():
    """Get Platform from /etc/os-release."""
    with open(os.path.join(os.sep, 'etc', 'os-release')) as fin:
        content = dict(
            line.split('=', 1)
            for line in fin.read().splitlines()
            if '=' in line
        )
    for k, v in content.items():
        content[k] = v.strip('"')
    return content["NAME"]
