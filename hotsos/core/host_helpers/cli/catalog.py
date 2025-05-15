from collections import UserDict

from hotsos.core.host_helpers.common import get_ps_axo_flags_available
from hotsos.core.host_helpers.cli.common import (
    BinCmd,
    DateFileCmd,
    FileCmd,
)
from hotsos.core.host_helpers.cli.commands import kubectl, ovs, ovn, ceph


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
            'ceph_health_detail_json_decoded': ceph.CephHealthDetailCommands(),
            'ceph_mon_dump_json_decoded': ceph.CephMonDumpCommands(),
            'ceph_osd_dump_json_decoded': ceph.CephOSDDumpCommands(),
            'ceph_df_json_decoded': ceph.CephDFCommands(),
            'ceph_osd_df_tree_json_decoded': ceph.CepOSDDFTreeCommands(),
            'ceph_osd_crush_dump_json_decoded':
                ceph.CephOSDCrushDumpCommands(),
            'ceph_pg_dump_json_decoded': ceph.CephPGDumpCommands(),
            'ceph_status_json_decoded': ceph.CephStatusCommands(),
            'ceph_versions': ceph.CephVersionsCommands(),
            'ceph_volume_lvm_list': ceph.CephVolumeLVMListCommands(),
            'ceph_report_json_decoded': ceph.CephReportCommands(),
            'ceph_mgr_module_ls': ceph.CephMgrModuleLsCommands(),
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
                kubectl.KubectlGetCmds(),
            'kubectl_logs':
                kubectl.KubectlLogsCmds(),
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
                ovn.OVNDBCTLListCmds(ctl_command='ovn-nbctl'),
            'ovn_sbctl_list':
                ovn.OVNDBCTLListCmds(ctl_command='ovn-sbctl'),
            'ovn_nbctl_show':
                ovn.OVNDBCTLShowCmds(ctl_command='ovn-nbctl'),
            'ovn_sbctl_show':
                ovn.OVNDBCTLShowCmds(ctl_command='ovn-sbctl'),
            'ovs_vsctl_get': ovs.OVSVSCtlGetCmds(),
            'ovs_vsctl_list': ovs.OVSVSCtlListCmds(),
            'ovs_vsctl_list_br': ovs.OVSVSCtlListBrCmds(),
            'ovs_appctl': ovs.OVSAppCtlCmds(),
            'ovs_ofctl': ovs.OVSOFCtlCmds(),
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
