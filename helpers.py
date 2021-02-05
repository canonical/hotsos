#!/usr/bin/python3
import os
import subprocess

# HOTSOS GLOBALS
DATA_ROOT = os.environ.get('DATA_ROOT', '/')


def get_ip_addr():
    if DATA_ROOT == '/':
        ip_addr_show = subprocess.check_output(['ip', '-d', 'address'])
        return ip_addr_show.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/networking/ip_-d_address")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_dpkg_l():
    if DATA_ROOT == '/':
        ps = subprocess.check_output(['dpkg', '-l'])
        return ps.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/dpkg/dpkg_-l")
    if os.path.exists(path):
        # I have observed UnicodeDecodeError with this file so switching to
        # surrogateescape.
        return open(path, 'r', errors="surrogateescape").readlines()


def get_ps():
    if DATA_ROOT == '/':
        ps = subprocess.check_output(['ps', 'auxwww'])
        return ps.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "ps")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_numactl():
    if DATA_ROOT == '/':
        numactl = subprocess.check_output(['numactl', '--hardware'])
        return numactl.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/numa/numactl_--hardware")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_lscpu():
    if DATA_ROOT == '/':
        numactl = subprocess.check_output(['lscpu'])
        return numactl.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/processor/lscpu")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_uptime():
    if DATA_ROOT == '/':
        numactl = subprocess.check_output(['uptime'])
        return numactl.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "uptime")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_df():
    if DATA_ROOT == '/':
        numactl = subprocess.check_output(['df'])
        return numactl.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "df")
    if os.path.exists(path):
        return open(path, 'r').readlines()


def get_apt_config_dump():
    if DATA_ROOT == '/':
        numactl = subprocess.check_output(['apt-config', 'dump'])
        return numactl.decode('UTF-8').splitlines()

    path = os.path.join(DATA_ROOT, "sos_commands/apt/apt-config_dump")
    if os.path.exists(path):
        return open(path, 'r').readlines()
