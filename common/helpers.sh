#!/bin/bash

get_ps ()
{
    local sos_path=${DATA_ROOT}ps
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        ps auxwww
    fi
}
export -f get_ps

get_ps_axo_flags ()
{
    # Older sosrepot uses 'wchan' option while newer ones use 'wchan:20' - thus the glob is to cover both
    local sos_path="${DATA_ROOT}/sos_commands/process/ps_axo_flags_state_uid_pid_ppid_pgid_sid_cls_pri_addr_sz_wchan*_lstart_tty_time_cmd"
    if [ -e $sos_path ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        ps axo flags,state,uid,pid,ppid,pgid,sid,cls,pri,addr,sz,wchan:20,lstart,tty,time,cmd
    fi
}
export -f get_ps_axo_flags

get_uptime ()
{
    local sos_path=${DATA_ROOT}uptime
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        cat /proc/uptime
    fi
}
export -f get_uptime

export bin_df=`which df`
df ()
{
    local sos_path=${DATA_ROOT}df
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        $bin_df
    fi
}
export -f df

export bin_lscpu=`which lscpu`
lscpu ()
{
    local sos_path=${DATA_ROOT}sos_commands/processor/lscpu
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        $bin_lscpu
    fi
}
export -f lscpu

get_ls_lanR_sys_block ()
{
    local sos_path=${DATA_ROOT}sos_commands/block/ls_-lanR_.sys.block
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        ls -lanR /sys/block/
    fi
}
export -f get_ls_lanR_sys_block

get_udevadm_info_dev ()
{
    local dev="$1"
    local sos_path=${DATA_ROOT}sos_commands/block/udevadm_info_.dev.$dev
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        udevadm info /dev/$dev
    fi
}
export -f get_udevadm_info_dev

# Converts the given seconds ($1) to DDd:HHh:MMh:SSs format
seconds_to_date ()
{
    local seconds="$1"
    local days=$((seconds/86400))
    local hours=$((seconds/3600%24))
    local mins=$((seconds/60%60))
    local secs=$((seconds%60))

    printf '%02dd:%02dh:%02dm:%02ds' $days $hours $mins $secs
}
export -f seconds_to_date

get_ceph_volume_lvm_list ()
{
    local sos_path="${DATA_ROOT}/sos_commands/ceph/ceph-volume_lvm_list"
    if [ -s "$sos_path" ]; then
        cat "$sos_path"
    elif ! [ -d "${DATA_ROOT}sos_commands" ] && which ceph-volume >/dev/null; then
        ceph-volume lvm list
    fi
}
export -f get_ceph_volume_lvm_list

get_lvm2_lvs ()
{
    local sos_path="${DATA_ROOT}/sos_commands/lvm2/lvs_-a_-o_lv_tags_devices*"
    if [ -e $sos_path ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ] && which lvs >/dev/null; then
        lvs -a -o lv_tags,devices
    fi
}
export -f get_lvm2_lvs

get_ceph_osd_tree ()
{
    local sos_path="${DATA_ROOT}/sos_commands/ceph/ceph_osd_tree"
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ] && which ceph >/dev/null; then
        ceph osd tree
    fi
}
export -f get_ceph_osd_tree

get_ceph_osd_df_tree ()
{
    local sos_path="${DATA_ROOT}/sos_commands/ceph/ceph_osd_df_tree"
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ] && which ceph >/dev/null; then
        ceph osd df tree
    fi
}
export -f get_ceph_osd_df_tree

get_ceph_versions ()
{
    local sos_path="${DATA_ROOT}/sos_commands/ceph/ceph_versions"
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ] && which ceph >/dev/null; then
        ceph versions
    fi
}
export -f get_ceph_versions

get_dpkg_l ()
{
    local sos_path=${DATA_ROOT}sos_commands/dpkg/dpkg_-l
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        dpkg -l
    fi
}
export -f get_dpkg_l

get_numactl_hardware ()
{
    local sos_path=${DATA_ROOT}sos_commands/numa/numactl_--hardware
    if [ -e "$sos_path" ]; then
        cat $sos_path
    elif ! [ -d "${DATA_ROOT}sos_commands" ]; then
        numactl --hardware
    fi
}
export -f get_numactl_hardware

