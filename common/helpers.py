#!/usr/bin/python3
import glob
import io
import os
import re
import subprocess
import sys

# HOTSOS GLOBALS
DATA_ROOT = os.environ.get('DATA_ROOT', '/')


def safe_readlines(path):
    return open(path, 'r', errors="surrogateescape").readlines()


def bool_str(val):
    if val.lower() == "true":
        return True
    elif val.lower() == "false":
        return False

    return val


def catch_exceptions(*exc_types):
    def catch_exceptions_inner1(f):
        def catch_exceptions_inner2(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except exc_types:
                return []

        return catch_exceptions_inner2

    return catch_exceptions_inner1


def get_ip_addr():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ip', '-d', 'address'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/networking/ip_-d_address")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_ip_link_show():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ip', '-s', '-d', 'link'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/networking/ip_-s_-d_link")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_dpkg_l():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['dpkg', '-l'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/dpkg/dpkg_-l")
    if os.path.exists(path):
        # I have observed UnicodeDecodeError with this file so switching to
        # surrogateescape.
        return safe_readlines(path)

    return []


@catch_exceptions(OSError)
def get_ps():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ps', 'auxwww'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "ps")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


def get_ps_axo_flags_available():
    path = os.path.join(DATA_ROOT, "sos_commands/process/ps_axo_flags_state_"
                        "uid_pid_ppid_pgid_sid_cls_pri_addr_sz_wchan*_lstart_"
                        "tty_time_cmd")
    for path in glob.glob(path):
        return path


@catch_exceptions(OSError)
def get_ps_axo_flags():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ps', 'axo', 'flags,state,uid,pid,'
                                          'ppid,pgid,sid,cls,pri,addr,sz,'
                                          'wchan:20,lstart,tty,time,cmd'])
        return output.decode('UTF-8').splitlines(keepends=True)

    # Older sosrepot uses 'wchan' option while newer ones use 'wchan:20' -
    # thus the glob is to cover both
    path = get_ps_axo_flags_available()
    if path:
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_numactl():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['numactl', '--hardware'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/numa/numactl_--hardware")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_lscpu():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['lscpu'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/processor/lscpu")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_uptime():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['uptime'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "uptime")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_df():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['df'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "df")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_apt_config_dump():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['apt-config', 'dump'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/apt/apt-config_dump")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_snap_list_all():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['snap', 'list', '--all'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/snappy/snap_list_--all")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError, subprocess.CalledProcessError)
def get_ceph_osd_df_tree():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'osd', 'df', 'tree'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_osd_df_tree")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError, subprocess.CalledProcessError)
def get_ceph_osd_tree():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'osd', 'tree'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_osd_tree")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError, subprocess.CalledProcessError)
def get_ceph_versions():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph', 'versions'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph_versions")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_date(format=None):
    if format is None:
        format = '+%s'

    if DATA_ROOT == '/':
        output = subprocess.check_output(['date', '--utc', format])
        return output.decode('UTF-8')

    path = os.path.join(DATA_ROOT, "sos_commands/date/date")
    if os.path.exists(path):
        with open(path, 'r') as fd:
            date = fd.read()

            # if date string contains timezone we need to remove it
            ret = re.match(r"^(\S+ \S*\s*[0-9]+ [0-9:]+ )[A-Z]*\s*([0-9]+)$",
                           date)
            if ret is None:
                sys.stderr.write("ERROR: {} has invalid date string '{}'".
                                 format(path, date))
            else:
                date = "{}{}".format(ret[1], ret[2])
                output = subprocess.check_output(["date", "--utc",
                                                  "--date={}".
                                                  format(date), format])
                return output.decode('UTF-8').splitlines(keepends=True)[0]

    return ""


@catch_exceptions(OSError, subprocess.CalledProcessError)
def get_ceph_volume_lvm_list():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ceph-volume', 'lvm', 'list'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/ceph/ceph-volume_lvm_list")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_ls_lanR_sys_block():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ls', '-lanR', '/sys/block/'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/block/ls_-lanR_.sys.block")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_udevadm_info_dev(dev):
    if DATA_ROOT == '/':
        output = subprocess.check_output(['udevadm', 'info',
                                          '/dev/{}'.format(dev)])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/block/udevadm_info_.dev.{}".
                        format(dev))
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_ip_netns():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['ip', 'netns'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "sos_commands/networking/ip_netns")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_hostname():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['hostname'])
        return output.decode('UTF-8').splitlines(keepends=True)

    path = os.path.join(DATA_ROOT, "hostname")
    if os.path.exists(path):
        return open(path, 'r').readlines()

    return []


@catch_exceptions(OSError)
def get_uname():
    if DATA_ROOT == '/':
        output = subprocess.check_output(['uname', '-a'])
        return output.decode('UTF-8')

    path = os.path.join(DATA_ROOT, "sos_commands/kernel/uname_-a")
    if os.path.exists(path):
        return open(path, 'r').read()

    return ""


def grep(pattern, files):
    """Run grep passing *args as arguments

    :param pattern: regular expression to match
    :param files: files to match that will be expanded by glob.glob()
    :returns: text with the matching lines (FILENAME:MATCHING_LINE)
    :rtype: io.StringIO"""
    result = io.StringIO()
    regex = re.compile(pattern)
    for path in glob.glob(files):
        with open(path, 'r') as f:
            for line in f:
                m = regex.search(line)
                if m:
                    result.write(f"{path}:{line}")

    result.seek(0)
    return result
