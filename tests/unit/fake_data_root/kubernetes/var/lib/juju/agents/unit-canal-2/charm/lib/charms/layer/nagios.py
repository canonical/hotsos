from pathlib import Path

NAGIOS_PLUGINS_DIR = '/usr/lib/nagios/plugins'


def install_nagios_plugin_from_text(text, plugin_name):
    """ Install a nagios plugin.

    Args:
        text: Plugin source code (str)
        plugin_name: Name of the plugin in nagios

    Returns: Full path to installed plugin
    """
    dest_path = Path(NAGIOS_PLUGINS_DIR) / plugin_name
    if dest_path.exists():
        # we could complain here, test the files are the same contents, or
        # just bail. Idempotency is a big deal in Juju, so I'd like to be
        # ok with being called with the same file multiple times, but we
        # certainly want to catch the case where multiple layers are using
        # the same filename for their nagios checks.
        dest = dest_path.read_text()
        if dest == text:
            # same file
            return dest_path
        # different file contents!
        # maybe someone changed options or something so we need to write
        # it again

    dest_path.write_text(text)
    dest_path.chmod(0o755)

    return dest_path


def install_nagios_plugin_from_file(source_file_path, plugin_name):
    """ Install a nagios plugin.

    Args:
        source_file_path: Path to plugin source file
        plugin_name: Name of the plugin in nagios

    Returns: Full path to installed plugin
    """

    return install_nagios_plugin_from_text(Path(source_file_path).read_text(),
                                           plugin_name)


def remove_nagios_plugin(plugin_name):
    """ Remove a nagios plugin.

    Args:
        plugin_name: Name of the plugin in nagios

    Returns: None
    """
    dest_path = Path(NAGIOS_PLUGINS_DIR) / plugin_name
    if dest_path.exists():
        dest_path.unlink()
