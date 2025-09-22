import os
import tempfile
from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd
from hotsos.core.host_helpers.exceptions import SourceNotFound


CephAliases = ['microceph.']


class CephJSONFileCmd(FileCmd):
    """
    Some ceph commands that use --format json have some extra text added to the
    end of the file (typically from stderr) which causes it to be invalid json
    so we have to strip that final line before decoding the contents.
    """
    def __init__(self, *args, first_line_filter=None, last_line_filter=None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        if first_line_filter or last_line_filter:
            self.register_hook('pre-exec', self.format_json_contents)
            self.register_hook('post-exec', self.cleanup)
            self.orig_path = None
            self.first_line_filter = first_line_filter
            self.last_line_filter = last_line_filter

    def format_json_contents(self, *_args, **_kwargs):
        if not os.path.exists(self.path):
            raise SourceNotFound(self.path)

        with open(self.path, encoding='utf-8') as f:
            lines = f.readlines()

        if self.first_line_filter:
            line_filter = self.first_line_filter
        else:
            line_filter = self.last_line_filter

        if lines and lines[-1].startswith(line_filter):
            lines = lines[:-1]
            with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as tmp:
                tmp.write(''.join(lines))
                tmp.close()
                self.orig_path = self.path
                self.path = tmp.name

    def cleanup(self, output, **_kwargs):
        """
        @param output: CmdOutput object
        """
        if self.orig_path:
            os.unlink(self.path)
            self.path = self.orig_path
            self.orig_path = None

        return output


class CephHealthDetailCommands(UserList):
    """ Generate ceph heath detail command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph health detail --format json-pretty',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/json_output/'
                            'ceph_health_detail_--format_json-pretty',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/json_output/'
                             f'{prefix}ceph_health_detail_'
                             '--format_json-pretty', json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CephMonDumpCommands(UserList):
    """ Generate ceph mon dump command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph mon dump --format json-pretty',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(CephJSONFileCmd('sos_commands/ceph/json_output/'
                                    'ceph_mon_dump_--format_json-pretty',
                                    json_decode=True,
                                    first_line_filter='dumped monmap epoch',
                                    last_line_filter='dumped monmap epoch'))
        # sosreport >= 4.2
        cmds.extend([CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                     f'{prefix}ceph_mon_dump_'
                                     '--format_json-pretty',
                                     json_decode=True,
                                     first_line_filter='dumped monmap epoch',
                                     last_line_filter='dumped monmap epoch')
                     for prefix in prefixes])
        super().__init__(cmds)


class CephOSDDumpCommands(UserList):
    """ Generate ceph osd dump command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph osd dump --format json-pretty',
                       json_decode=True)
                for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/json_output/'
                            'ceph_osd_dump_--format_json-pretty',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/json_output/'
                             f'{prefix}ceph_osd_dump_--format_json-pretty',
                             json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CephDFCommands(UserList):
    """ Generate ceph df command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph df --format json-pretty',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/json_output/'
                            'ceph_df_--format_json-pretty',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/json_output/'
                             f'{prefix}ceph_df_--format_json-pretty',
                             json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CepOSDDFTreeCommands(UserList):
    """ Generate ceph df tree command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph osd df tree --format json-pretty',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/json_output/'
                            'ceph_osd_df_tree_--format_json-pretty',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/json_output/'
                             f'{prefix}ceph_osd_df_tree_--format_json-pretty',
                             json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CephOSDCrushDumpCommands(UserList):
    """ Generate ceph osd crush dump command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph osd crush dump',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/ceph_osd_crush_dump',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/'
                             f'{prefix}ceph_osd_crush_dump',
                             json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CephPGDumpCommands(UserList):
    """ Generate ceph pg dump command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph pg dump --format json-pretty',
                       json_decode=True)
                for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(CephJSONFileCmd('sos_commands/ceph/json_output/'
                                    'ceph_pg_dump_--format_json-pretty',
                                    json_decode=True,
                                    first_line_filter='dumped all',
                                    last_line_filter='dumped all'))
        # sosreport >= 4.2
        cmds.extend([CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                     f'{prefix}ceph_pg_dump_'
                                     '--format_json-pretty',
                                     json_decode=True,
                                     first_line_filter='dumped all',
                                     last_line_filter='dumped all')
                     for prefix in prefixes])
        super().__init__(cmds)


class CephStatusCommands(UserList):
    """ Generate ceph status command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph status --format json-pretty',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/json_output/'
                            'ceph_status_--format_json-pretty',
                            json_decode=True))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/json_output/'
                             f'{prefix}ceph_status_--format_json-pretty',
                             json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)


class CephVersionsCommands(UserList):
    """ Generate ceph versions command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph versions') for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/ceph_versions'))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_mon/'
                             f'{prefix}ceph_versions')
                     for prefix in prefixes])
        super().__init__(cmds)


class CephVolumeLVMListCommands(UserList):
    """ Generate ceph-volume lvm list command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph-volume lvm list') for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(FileCmd('sos_commands/ceph/ceph-volume_lvm_list'))
        # sosreport >= 4.2
        cmds.extend([FileCmd('sos_commands/ceph_osd/'
                             f'{prefix}ceph-volume_lvm_list')
                     for prefix in prefixes])
        super().__init__(cmds)


class CephReportCommands(UserList):
    """ Generate ceph XXX command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph report', json_decode=True)
                for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(CephJSONFileCmd('sos_commands/ceph/ceph_report',
                                    json_decode=True,
                                    first_line_filter='report',
                                    last_line_filter='report'))
        # sosreport >= 4.2
        cmds.extend([CephJSONFileCmd('sos_commands/ceph_mon/'
                                     f'{prefix}ceph_report',
                                     json_decode=True,
                                     first_line_filter='report',
                                     last_line_filter='report')
                     for prefix in prefixes])
        super().__init__(cmds)


class CephMgrModuleLsCommands(UserList):
    """ Generate ceph XXX command variants. """

    def __init__(self):
        prefixes = [""] + CephAliases
        # binary
        cmds = [BinCmd(f'{prefix}ceph mgr module ls',
                       json_decode=True) for prefix in prefixes]
        # file-based
        # sosreport < 4.2
        cmds.append(CephJSONFileCmd('sos_commands/ceph/ceph_mgr_module_ls',
                                    json_decode=True))
        # sosreport >= 4.2
        cmds.extend([CephJSONFileCmd('sos_commands/ceph_mon/'
                                     f'{prefix}ceph_mgr_module_ls',
                                     json_decode=True)
                     for prefix in prefixes])
        super().__init__(cmds)
