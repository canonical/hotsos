import os
import tempfile
from collections import UserDict

from hotsos.core.host_helpers.common import get_ps_axo_flags_available
from hotsos.core.host_helpers.exceptions import (
    CLIExecError,
    SourceNotFound,
)
from hotsos.core.host_helpers.cli.common import (
    BinCmd,
    DateFileCmd,
    FileCmd,
    CmdOutput
)
from hotsos.core.host_helpers.cli.commands import kubectl
from hotsos.core.log import log


class OVSAppCtlBinCmd(BinCmd):
    """ Implements ovs-appctl binary command. """
    def __call__(self, *args, **kwargs):
        # Set defaults for optional args
        for key in ['flags', 'args']:
            if key not in kwargs:
                kwargs[key] = ''

        return super().__call__(*args, **kwargs)


class OVSAppCtlFileCmd(FileCmd):
    """ Implements ovs-appctl file-based command. """
    def __call__(self, *args, **kwargs):
        for key in ['flags', 'args']:
            if key in kwargs:
                kwargs[key] = f'_{kwargs[key]}'
            else:
                kwargs[key] = ''

        if 'args' in kwargs and kwargs['command'].startswith('dpctl/'):
            # e.g. this would be for dpctl datapath
            kwargs['args'] = kwargs['args'].replace('@', '_')

        kwargs['command'] = kwargs['command'].replace('/', '.')
        try:
            out = super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: source not found: %s", self.__class__.__name__,
                      self.path)
            raise

        return out


OFPROTOCOL_VERSIONS = [
    "OpenFlow15",
    "OpenFlow14",
    "OpenFlow13",
    "OpenFlow12",
    "OpenFlow11",
    "OpenFlow10",
]


class OVSOFCtlBinCmd(BinCmd):
    """ Implementation of ovs-ofctl binary command. """
    BIN_CMD = 'ovs-ofctl'

    def __call__(self, *args, **kwargs):
        """
        First try without specifying protocol version. If error is raised
        try with different versions until we get a result.
        """
        self.cmd = f"{self.BIN_CMD} {self.cmd}"
        try:
            return super().__call__(*args, **kwargs)
        except CLIExecError:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        # If the command raised an exception it will have been caught by the
        # catch_exceptions decorator and [] returned. We have no way of knowing
        # if that was the actual return or an exception was raised so we just
        # go ahead and retry with specific OF versions until we get a result.
        for ver in OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            self.cmd = f"{self.BIN_CMD} -O {ver} {self.cmd}"
            try:
                return super().__call__(*args, **kwargs)
            except CLIExecError:
                log.debug("%s: command with protocol version %s failed",
                          self.__class__.__name__, ver)

        return CmdOutput([])


class SunbeamOVSOFCtlBinCmd(OVSOFCtlBinCmd):
    """ Implementation of Sunbeam openstack-hypervisor.ovs-ofctl binary
    command. """
    BIN_CMD = 'openstack-hypervisor.ovs-ofctl'


class OVNDBCTLShowBinCmd(BinCmd):
    """ Implementation for binary ovndb ctl show commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        cmd = f'{prefix}{ctl_command} --no-leader-only show'
        super().__init__(cmd, *args, **kwargs)


class OVNDBCTLShowFileCmd(FileCmd):
    """ Implementation for file-based ovndb ctl show commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        path = (f'sos_commands/ovn_central/{prefix}{ctl_command}_'
                '--no-leader-only_show')
        super().__init__(path, *args, **kwargs)


class OVNDBCTLListBinCmd(BinCmd):
    """ Implementation for binary ovndb ctl list commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        cmd = f'{prefix}{ctl_command} --no-leader-only list' + ' {table}'
        super().__init__(cmd, *args, **kwargs)


class OVNDBCTLListFileCmd(FileCmd):
    """ Implementation for file-based ovndb ctl list commands providing support
        for different variants.
    """

    def __init__(self, ctl_command, *args, prefix=None, **kwargs):
        prefix = prefix or ''
        path = (f'sos_commands/ovn_central/{prefix}{ctl_command}_'
                '--no-leader-only_list_{table}')
        super().__init__(path, *args, **kwargs)


class OVSOFCtlFileCmd(FileCmd):
    """ Implementation of ovs-ofctl file-based command. """
    def __call__(self, *args, **kwargs):
        """
        We do this in reverse order to bin command since it won't actually
        raise an error.
        """
        for ver in OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            try:
                kwargs['ofversion'] = f'_-O_{ver}'
                out = super().__call__(*args, **kwargs)
                if out.value and 'version negotiation failed' in out.value[0]:
                    continue

                return out
            except SourceNotFound:
                pass

        try:
            kwargs['ofversion'] = ''
            return super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        return None


class DateBinCmd(BinCmd):
    """ Implementation binary date command. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_hook("pre-exec", self.format_date_cmd)

    def format_date_cmd(self, **kwargs):
        """ Add formatting to date command. """
        no_format = kwargs.get('no_format', False)
        fmt = kwargs.get('format')
        if not no_format and fmt is None:
            fmt = '+%s'

        self.cmd = f'{self.cmd} --utc'
        if fmt:
            # this can't get split() so add to the end of the command list
            self.cmd_extras = [fmt]


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


class CommandCatalog(UserDict):
    """ Catalog of all supported commands. """

    def __init__(self):
        super().__init__()
        self.data = {
            'apt_config_dump':
                [BinCmd('apt-config dump'),
                 FileCmd('sos_commands/apt/apt-config_dump')],
            'apparmor_status':
                [BinCmd('apparmor_status'),
                 FileCmd('sos_commands/apparmor/apparmor_status')],
            'ceph_daemon_osd_config_show':
                [BinCmd('ceph daemon osd.{osd_id} config show',
                        json_decode=True),
                 # requires sosreport 4.3 or above
                 FileCmd('sos_commands/ceph_osd/'
                         'ceph_daemon_osd.{osd_id}_config_show',
                         json_decode=True)],
            'ceph_daemon_osd_dump_mempools':
                [BinCmd('ceph daemon osd.{osd_id} dump mempools',
                        json_decode=True),
                 # requires sosreport 4.3 or above
                 FileCmd('sos_commands/ceph_osd/'
                         'ceph_daemon_osd.{osd_id}_dump_mempools',
                         json_decode=True)],
            'ceph_health_detail_json_decoded':
                [BinCmd('ceph health detail --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_health_detail_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_health_detail_--format_json-pretty',
                         json_decode=True)],
            'ceph_mon_dump_json_decoded':
                [BinCmd('ceph mon dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/json_output/'
                                 'ceph_mon_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped monmap epoch',
                                 last_line_filter='dumped monmap epoch'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                 'ceph_mon_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped monmap epoch',
                                 last_line_filter='dumped monmap epoch')],
            'ceph_osd_dump_json_decoded':
                [BinCmd('ceph osd dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_osd_dump_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_osd_dump_--format_json-pretty',
                         json_decode=True)],
            'ceph_df_json_decoded':
                [BinCmd('ceph df --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_df_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_df_--format_json-pretty',
                         json_decode=True)],
            'ceph_osd_df_tree_json_decoded':
                [BinCmd('ceph osd df tree --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_osd_df_tree_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_osd_df_tree_--format_json-pretty',
                         json_decode=True)],
            'ceph_osd_crush_dump_json_decoded':
                [BinCmd('ceph osd crush dump', json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph_osd_crush_dump',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/ceph_osd_crush_dump',
                         json_decode=True),
                 ],
            'ceph_pg_dump_json_decoded':
                [BinCmd('ceph pg dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/json_output/'
                                 'ceph_pg_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped all',
                                 last_line_filter='dumped all'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                 'ceph_pg_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped all',
                                 last_line_filter='dumped all')],
            'ceph_status_json_decoded':
                [BinCmd('ceph status --format json-pretty', json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_status_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/'
                         'json_output/ceph_status_--format_json-pretty',
                         json_decode=True),
                 ],
            'ceph_versions':
                [BinCmd('ceph versions'),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph_versions'),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/ceph_versions'),
                 ],
            'ceph_volume_lvm_list':
                [BinCmd('ceph-volume lvm list'),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph-volume_lvm_list'),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_osd/ceph-volume_lvm_list'),
                 ],
            'ceph_report_json_decoded':
                [BinCmd('ceph report', json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/ceph_report',
                                 json_decode=True,
                                 first_line_filter='report',
                                 last_line_filter='report'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/ceph_report',
                                 json_decode=True,
                                 first_line_filter='report',
                                 last_line_filter='report'),
                 ],
            'ceph_mgr_module_ls':
                [BinCmd('ceph mgr module ls', json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/ceph_mgr_module_ls',
                                 json_decode=True),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/ceph_mgr_module_ls',
                                 json_decode=True),
                 ],
            'date':
                [DateBinCmd('date', singleline=True),
                 DateFileCmd('sos_commands/date/date', singleline=True),
                 # this is for legacy sosreport versions
                 DateFileCmd('sos_commands/general/date', singleline=True)],
            'df':
                [BinCmd('df'),
                 FileCmd('df')],
            'dmesg':
                [BinCmd('dmesg'),
                 FileCmd('sos_commands/kernel/dmesg')],
            'docker_images':
                [BinCmd('docker images'),
                 FileCmd('sos_commands/docker/docker_images')],
            'docker_ps':
                [BinCmd('docker ps'),
                 FileCmd('sos_commands/docker/docker_ps')],
            'dpkg_l':
                [BinCmd('dpkg -l'),
                 FileCmd('sos_commands/dpkg/dpkg_-l',
                         decode_error_handling='surrogateecape')],
            'ethtool':
                [BinCmd('ethtool {interface}'),
                 FileCmd('sos_commands/networking/ethtool_{interface}')],
            'hostname':
                [BinCmd('hostname', singleline=True),
                 FileCmd('hostname', singleline=True)],
            'hostnamectl':
                [BinCmd('hostnamectl'),
                 FileCmd('sos_commands/host/hostnamectl_status')],
            'ip_netns':
                [BinCmd('ip netns'),
                 FileCmd('sos_commands/networking/ip_netns')],
            'ip_addr':
                [BinCmd('ip -d address'),
                 FileCmd('sos_commands/networking/ip_-d_address')],
            'ip_link':
                [BinCmd('ip -s -d link'),
                 FileCmd('sos_commands/networking/ip_-s_-d_link')],
            'kubectl_get':
                [kubectl.KubectlGetBinCmd('kubectl'),
                 # MicroK8s
                 kubectl.KubectlGetBinCmd('microk8s.kubectl'),
                 # Canonical K8s
                 kubectl.KubectlGetBinCmd('k8s kubectl'),
                 # Native
                 kubectl.KubectlGetFileCmd('kubectl'),
                 # MicroK8s
                 kubectl.KubectlGetFileCmd('microk8s_kubectl'),
                 # Canonical K8s
                 kubectl.KubectlGetFileCmd('k8s_kubectl')],
            'kubectl_logs':
                [kubectl.KubectlLogsBinCmd('kubectl'),
                 # MicroK8s
                 kubectl.KubectlLogsBinCmd('microk8s.kubectl'),
                 # Canonical K8s
                 kubectl.KubectlLogsBinCmd('k8s kubectl'),
                 # Native
                 kubectl.KubectlLogsFileCmd('kubectl'),
                 # MicroK8s
                 kubectl.KubectlLogsFileCmd('microk8s_kubectl'),
                 # Canonical K8s
                 kubectl.KubectlLogsFileCmd('k8s_kubectl')],
            'ls_lanR_sys_block':
                [BinCmd('ls -lanR /sys/block/'),
                 FileCmd('sos_commands/block/ls_-lanR_.sys.block')],
            'lscpu':
                [BinCmd('lscpu'),
                 FileCmd('sos_commands/processor/lscpu')],
            'lsof_Mnlc':
                [BinCmd('lsof +M -n -l -c ""'),
                 FileCmd('sos_commands/process/lsof_M_-n_-l_-c')],
            'lxd_buginfo':
                [BinCmd('lxd.buginfo'),
                 FileCmd('sos_commands/lxd/lxd.buginfo')],
            'numactl':
                [BinCmd('numactl --hardware'),
                 FileCmd('sos_commands/numa/numactl_--hardware')],
            'ns_ip_addr':
                [BinCmd('ip netns exec {namespace} ip address show'),
                 FileCmd('sos_commands/networking/'
                         'ip_netns_exec_{namespace}_ip_address_show'),
                 FileCmd('sos_commands/networking/namespaces/{namespace}/'
                         'ip_netns_exec_{namespace}_ip_-d_address_show')],
            'ovn_nbctl_list':
                [OVNDBCTLListBinCmd(ctl_command='ovn-nbctl'),
                 OVNDBCTLListBinCmd(ctl_command='ovn-nbctl',
                                    prefix='openstack-hypervisor.'),
                 OVNDBCTLListBinCmd(ctl_command='ovn-nbctl',
                                    prefix='microovn.'),
                 # sosreport: noalias
                 OVNDBCTLListFileCmd(ctl_command='ovn-nbctl'),
                 # sosreport: sunbeam
                 OVNDBCTLListFileCmd(ctl_command='ovn-nbctl',
                                     prefix='openstack-hypervisor.'),
                 # sosreport: microovn
                 OVNDBCTLListFileCmd(ctl_command='ovn-nbctl',
                                     prefix='microovn.'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-nbctl_list')],
            'ovn_sbctl_list':
                [OVNDBCTLListBinCmd(ctl_command='ovn-sbctl'),
                 OVNDBCTLListBinCmd(ctl_command='ovn-sbctl',
                                    prefix='openstack-hypervisor.'),
                 OVNDBCTLListBinCmd(ctl_command='ovn-sbctl',
                                    prefix='microovn.'),
                 # sosreport: noalias
                 OVNDBCTLListFileCmd(ctl_command='ovn-sbctl'),
                 # sosreport: sunbeam
                 OVNDBCTLListFileCmd(ctl_command='ovn-sbctl',
                                     prefix='openstack-hypervisor.'),
                 # sosreport: microovn
                 OVNDBCTLListFileCmd(ctl_command='ovn-sbctl',
                                     prefix='microovn.'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-sbctl_list')],
            'ovn_nbctl_show':
                [OVNDBCTLShowBinCmd(ctl_command='ovn-nbctl'),
                 OVNDBCTLShowBinCmd(ctl_command='ovn-nbctl',
                                    prefix='openstack-hypervisor.'),
                 OVNDBCTLShowBinCmd(ctl_command='ovn-nbctl',
                                    prefix='microovn.'),
                 # sosreport: noalias
                 OVNDBCTLShowFileCmd(ctl_command='ovn-nbctl'),
                 # sosreport: sunbeam
                 OVNDBCTLShowFileCmd(ctl_command='ovn-nbctl',
                                     prefix='openstack-hypervisor.'),
                 # sosreport: microovn
                 OVNDBCTLShowFileCmd(ctl_command='ovn-nbctl',
                                     prefix='microovn.'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-nbctl_show')],
            'ovn_sbctl_show':
                [OVNDBCTLShowBinCmd(ctl_command='ovn-sbctl'),
                 OVNDBCTLShowBinCmd(ctl_command='ovn-sbctl',
                                    prefix='openstack-hypervisor.'),
                 OVNDBCTLShowBinCmd(ctl_command='ovn-sbctl',
                                    prefix='microovn.'),
                 # sosreport: noalias
                 OVNDBCTLShowFileCmd(ctl_command='ovn-sbctl'),
                 # sosreport: sunbeam
                 OVNDBCTLShowFileCmd(ctl_command='ovn-sbctl',
                                     prefix='openstack-hypervisor.'),
                 # sosreport: microovn
                 OVNDBCTLShowFileCmd(ctl_command='ovn-sbctl',
                                     prefix='microovn.'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-sbctl_show')],
            'ovs_vsctl_get':
                [BinCmd('ovs-vsctl get {table} {record} {column}',
                        singleline=True),
                 BinCmd('openstack-hypervisor.'
                        'ovs-vsctl get {table} {record} {column}',
                        singleline=True),
                 FileCmd('sos_commands/openvswitch/ovs-vsctl_-t_5_get_'
                         '{table}_{record}_{column}', singleline=True),
                 FileCmd('sos_commands/openvswitch/openstack-hypervisor.'
                         'ovs-vsctl_-t_5_get_'
                         '{table}_{record}_{column}', singleline=True)],
            'ovs_vsctl_list':
                [BinCmd('ovs-vsctl list {table}'),
                 BinCmd('openstack-hypervisor.ovs-vsctl list {table}'),
                 FileCmd('sos_commands/openvswitch/'
                         'ovs-vsctl_-t_5_list_{table}'),
                 FileCmd('sos_commands/ovn_host/ovs-vsctl_list_{table}'),
                 FileCmd('sos_commands/openvswitch/'
                         'openstack-hypervisor.ovs-vsctl_-t_5_list_{table}')],
            'ovs_vsctl_list_br':
                [BinCmd('ovs-vsctl list-br'),
                 BinCmd('openstack-hypervisor.ovs-vsctl list-br'),
                 FileCmd('sos_commands/openvswitch/ovs-vsctl_-t_5_list-br'),
                 FileCmd('sos_commands/openvswitch/openstack-hypervisor.'
                         'ovs-vsctl_-t_5_list-br')],
            'ovs_appctl':
                [OVSAppCtlBinCmd('ovs-appctl {command} {flags} {args}'),
                 OVSAppCtlBinCmd('openstack-hypervisor.'
                                 'ovs-appctl {command} {flags} {args}'),
                 OVSAppCtlFileCmd('sos_commands/openvswitch/ovs-appctl_'
                                  '{command}{flags}{args}'),
                 OVSAppCtlFileCmd('sos_commands/openvswitch/'
                                  'openstack-hypervisor.ovs-appctl_'
                                  '{command}{flags}{args}')],
            'ovs_ofctl':
                [OVSOFCtlBinCmd('{command} {args}'),
                 SunbeamOVSOFCtlBinCmd('{command} {args}'),
                 OVSOFCtlFileCmd('sos_commands/openvswitch/'
                                 'ovs-ofctl{ofversion}_{command}_{args}'),
                 OVSOFCtlFileCmd('sos_commands/openvswitch/'
                                 'openstack-hypervisor.'
                                 'ovs-ofctl{ofversion}_{command}_{args}')],
            'pacemaker_crm_status':
                [BinCmd('crm status'),
                 FileCmd('sos_commands/pacemaker/crm_status')],
            'pebble_services':
                [BinCmd('pebble services'),
                 # This is how operator charms run it
                 BinCmd('/charm/bin/pebble services'),
                 # The following does not exist in sosreport yet but adding
                 # since it is useful for testing and will hopefully be
                 # supported in sos at some point.
                 FileCmd('sos_commands/pebble/pebble_services')],
            'ps':
                [BinCmd('ps auxwww'),
                 FileCmd('ps')],
            'ps_axo_flags':
                [BinCmd('ps axo flags,state,uid,pid,ppid,pgid,sid,cls,'
                        'pri,addr,sz,wchan:20,lstart,tty,time,cmd'),
                 # Older sosrepot uses 'wchan' option while newer ones use
                 # 'wchan:20' - thus the glob is to cover both
                 FileCmd(get_ps_axo_flags_available() or "")],
            'pro_status':
                [BinCmd('ua status'),
                 FileCmd('sos_commands/ubuntu/ua_status')],
            'rabbitmqctl_report':
                [BinCmd('rabbitmqctl report'),
                 FileCmd('sos_commands/rabbitmq/rabbitmqctl_report')],
            'sunbeam_cluster_list':
                [BinCmd('sunbeam cluster list'),
                 FileCmd('sos_commands/sunbeam/sunbeam_cluster_list')],
            'sunbeam_cluster_list_yaml_decoded':
                [BinCmd('sunbeam cluster list --format yaml'),
                 FileCmd('sos_commands/sunbeam/'
                         'sunbeam_cluster_list_--format_yaml',
                         yaml_decode=True)],
            'snap_list_all':
                [BinCmd('snap list --all'),
                 FileCmd('sos_commands/snap/snap_list_--all'),
                 # sos legacy
                 FileCmd('sos_commands/snappy/snap_list_--all')],
            'sysctl_all':
                [BinCmd('sysctl -a'),
                 FileCmd('sos_commands/kernel/sysctl_-a')],
            'systemctl_status_all':
                [BinCmd('systemctl status --all'),
                 FileCmd('sos_commands/systemd/systemctl_status_--all',
                         decode_error_handling='backslashreplace')],
            'systemctl_list_units':
                [BinCmd('systemctl list-units'),
                 FileCmd('sos_commands/systemd/systemctl_list-units')],
            'systemctl_list_unit_files':
                [BinCmd('systemctl list-unit-files'),
                 FileCmd('sos_commands/systemd/systemctl_list-unit-files')],
            'udevadm_info_dev':
                [BinCmd('udevadm info /dev/{device}'),
                 FileCmd('sos_commands/block/udevadm_info_.dev.{device}')],
            'udevadm_info_exportdb':
                [BinCmd('udevadm info --export-db'),
                 FileCmd('sos_commands/devices/udevadm_info_--export-db')],
            'uname':
                [BinCmd('uname -a', singleline=True),
                 FileCmd('sos_commands/kernel/uname_-a', singleline=True)],
            'uptime':
                [BinCmd('uptime', singleline=True),
                 FileCmd('uptime', singleline=True)],
        }
