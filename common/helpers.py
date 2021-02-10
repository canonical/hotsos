#!/usr/bin/python3
import glob
import os
import subprocess

# HOTSOS GLOBALS
DATA_ROOT = os.environ.get('DATA_ROOT', '/')


def get_ip_addr():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ip', '-d', 'address'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/networking/ip_-d_address")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_dpkg_l():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['dpkg', '-l'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/dpkg/dpkg_-l")
    if os.path.exists(path):
        # I have observed UnicodeDecodeError with this file so switching to
        # surrogateescape.
        return open(path, 'r', errors="surrogateescape").readlines()


def get_ps():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ps', 'auxwww'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "ps")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_ps_axo_flags():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ps', 'axo', 'flags,state,uid,pid,'
                                          'ppid,pgid,sid,cls,pri,addr,sz,'
                                          'wchan:20,lstart,tty,time,cmd'])
        return output.decode('UTF-8').splitlines()

    # Older sosrepot uses 'wchan' option while newer ones use 'wchan:20' -
    # thus the glob is to cover both
    path = os.path.join(DATA_ROOT, "sos_commands/process/ps_axo_flags_state_"
                        "uid_pid_ppid_pgid_sid_cls_pri_addr_sz_wchan*_lstart_"
                        "tty_time_cmd")
    for path in glob.glob(path):
        return open(path, 'r').readlines()


def get_numactl():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['numactl', '--hardware'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/numa/numactl_--hardware")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_lscpu():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['lscpu'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/processor/lscpu")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_uptime():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['uptime'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "uptime")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_df():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['df'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "df")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_apt_config_dump():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['apt-config', 'dump'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/apt/apt-config_dump")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_snap_list_all():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['snap', 'list', '--all'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/snappy/snap_list_--all")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_ceph_osd_df_tree():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'osd', 'df', 'tree'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_osd_df_tree")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_ceph_osd_tree():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'osd', 'tree'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_osd_tree")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_ceph_versions():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'versions'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_versions")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_sosreport_time():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['date', '+%s'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/date/date")
    if os.path.exists(path):
        with open(path, 'r') as fd:
            date = fd.read()
            output = subprocess.check_output(["date", "--date={}".format(date),
                                              "+%s"])
            return output.decode('UTF-8').splitlines()[0]


def get_ceph_volume_lvm_list():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph-volume', 'lvm', 'list'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph-volume_lvm_list")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_ls_lanR_sys_block():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ls', '-lanR', '/sys/block/'])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/block/ls_-lanR_.sys.block")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_udevadm_info_dev(dev):
    if DATA_ROOT == '/':
        output = subprocess.check_output(['udevadm', 'info',
                                          '/dev/{}'.format(dev)])
        return output.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/block/udevadm_info_.dev.{}".
                        format(dev))
    if os.path.exists(path):
        return open(path, 'r').readlines()
