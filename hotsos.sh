#!/bin/bash -eu
#
# Generate a high-level summary of a sosreport.
#
declare -a roots=()
ctg_selected=true
ctg_brief=true
ctg_versions=false
ctg_openstack=false
ctg_storage=false
ctg_juju=false
ctg_kernel=false
ctg_system=false
write_to_file=false

usage ()
{
cat << EOF
USAGE: xseg OPTIONS

OPTIONS
    -h|--help
        This message
    --juju
        Include Juju info
    --openstack
        Include Openstack services info
    --kernel
        Include Kernel info
    --storage
        Include storage info including Ceph
    --system
        Include system info
    --versions
        Include software version info
    -s|--save
    -a|--all
EOF
}

while (($#)); do 
    case $1 in
          -h|--help)
              usage
              exit 0
              ;;
          --versions)
              ctg_selected=true
              ctg_versions=true
              ;;
          --juju)
              ctg_selected=true
              ctg_juju=true
              ;;
          --openstack)
              ctg_selected=true
              ctg_openstack=true
              ;;
          --storage)
              ctg_selected=true
              ctg_storage=true
              ;;
          --kernel)
              ctg_selected=true
              ctg_kernel=true
              ;;
          --system)
              ctg_selected=true
              ctg_system=true
              ;;
          -s|--save)
              write_to_file=true
              ;;
          -a|--all)
            ctg_selected=false
              ;;
          *)
              roots+=( $1 )
              ;;
    esac
    shift
done

if ! $ctg_selected; then
    ctg_versions=true
    ctg_openstack=true
    ctg_storage=true
    ctg_juju=true
    ctg_kernel=true
    ctg_system=true
fi

f_output=`mktemp`

((${#roots[@]})) || roots=( . )

for root in ${roots[@]}; do

sosreport_name=`basename $root`

(

# TODO
#if false && [ "`file -b $root`" = "XZ compressed data" ]; then
#    dtmp=`mktemp -d`
#    tar --exclude='*/*' -tf $root
#    sosroot=`tar --exclude='*/*' -tf $root| sed -r 's,([[:alnum:]\-]+)/*.*,\1,g'| sort -u`
#    tar -tf $root $sosroot/var/log/juju 2>/dev/null > $dtmp/juju
#    if (($?==0)); then
#        mkdir -p $dtmp/var/log/juju
#        mv $dtmp/juju $dtmp/var/log/
#    fi
#    tree $dtmp
#    root=$dtmp
#fi

[ -z "$root" ] || cd $root

echo -e "## sosreport-summary ##\n" > $f_output

echo -e "hostname:\n  - `cat hostname`" >> $f_output
if $ctg_versions; then
    echo -e "versions:" >> $f_output
    echo -n "  - ubuntu: " >> $f_output
    sed -r 's/DISTRIB_CODENAME=(.+)/\1/g;t;d' etc/lsb-release >> $f_output

    echo -n "  - openstack: " >> $f_output
    apts='etc/apt/sources.list.d/*.list'
    if [ -d "`dirname \"$apts\"`" ] && `grep -qr ubuntu-cloud.archive $apts 2>/dev/null`; then
        ost_rel="`grep -r ubuntu-cloud.archive $apts| grep -v deb-src |\
            sed -r 's/.+-updates\/(.+)\s+.+/\1/g;t;d'`"
        [ -n "$ost_rel" ] || ost_rel=unknown
        echo "$ost_rel" >> $f_output
    else
        echo "distro" >> $f_output
    fi
fi

if $ctg_openstack; then
    echo -e "openstack:" >> $f_output

    # TODO: keep this list up-to-date with services we care about in the context of openstack
    default_pfix_match='[[:alnum:]\-]+'
    declare -a services=(
    aodh$default_pfix_match
    apache$default_pfix_match
    barbican$default_pfix_match
    beam.smp
    ceilometer$default_pfix_match
    ceph-[[:alpha:]]+
    cinder$default_pfix_match
    designate$default_pfix_match
    glance$default_pfix_match
    gnocchi$default_pfix_match
    heat$default_pfix_match
    horizon
    keystone$default_pfix_match
    mysqld
    neutron$default_pfix_match
    nova$default_pfix_match
    octavia$default_pfix_match
    openstack-dashboard
    rabbitmq-server
    rados$default_pfix_match
    swift$default_pfix_match
    vault$default_pfix_match
    qemu-system-[[:alnum:]\\-\\_]+
    )
    if [ -r "ps" ]; then
        declare -A openstack_info=()
        for svc in ${services[@]}; do
            readarray -t out<<<"`sed -r -e \"s/.+($svc)\s+.+/\1/g;t;d\" ps`"
            ((${#out[@]}==0)) || [ -z "${out[0]}" ] && continue
            for e in ${out[@]}; do
                n=${openstack_info[$e]:-0}
                openstack_info[$e]=$((n+1))
            done
        done
        if ((${#openstack_info[@]})); then
            for e in ${!openstack_info[@]}; do
                echo "  - $e (${openstack_info[$e]})"
            done| sort -k 2 >> $f_output
        else
            echo "  - null" >> $f_output
        fi
    else
        echo "  ps not found - skipping openstack service detection" >> $f_output
    fi
fi

if $ctg_storage; then
    echo -e "ceph:" >> $f_output

    services=(
    ceph-osd
    ceph-mon
    ceph-mgr
    radosgw
    )
    if [ -r "ps" ]; then
        hash=`md5sum $f_output`
        ( for svc in ${services[@]}; do
            out="`sed -r \"s/.*(${svc}[[:alnum:]\-]*)\s+.+/\1/g;t;d\" ps| sort| uniq| sed -r 's/^\s+/  /g'`"
            id="`sed -r \"s/.*(${svc}[[:alnum:]\-]*)\s+.+--id\s+([[:digit:]]+)\s+.+/\2/g;t;d\" ps| tr -s '\n' ','| sort| sed -r -e 's/^\s+/  /g' -e 's/,$//g'`"
            [ -z "$out" ] && continue
            for osd_id in `echo $id| tr ',' ' '`;do
                offset=`egrep -n "osd id\s+$osd_id\$" sos_commands/ceph/ceph-volume_lvm_list| cut -f1 -d:`
                osd_fsid=`tail -n+$offset sos_commands/ceph/ceph-volume_lvm_list| grep "osd fsid"| head -n 1| sed -r 's/.+\s+([[:alnum:]]+)/\1/g'`
                osd_device=`tail -n+$offset sos_commands/ceph/ceph-volume_lvm_list| grep "devices"| head -n 1| sed -r 's/.+\s+([[:alnum:]\/]+)/\1/g'`
                echo "  - ceph-osd (id=$osd_id) (fsid=$osd_fsid) (device=$osd_device)"
            done
        done ) >> $f_output
        [ "$hash" = "`md5sum $f_output`" ] && echo "  - null" >> $f_output
    else
        echo "  ps not found - skipping ceph service detection" >> $f_output
    fi
    
    echo "bcache-info:" >> $f_output
    readarray -t bcacheinfo<<<"`grep . sos_commands/block/ls_-lanR_.sys.block| egrep 'bcache|nvme'| sed -r 's/.+[[:digit:]\:]+\s+([[:alnum:]]+)\s+.+/\1/g'`"
    ((${#bcacheinfo[@]})) && [ -n "${bcacheinfo[0]}" ] || bcacheinfo=( "null" )
    block_root=sos_commands/block/udevadm_info_.dev.
    for bcache_name in ${bcacheinfo[@]}; do
        backing_dev_fs_uuid=`sed -r 's,^S: bcache/by-uuid/([[:alnum:]\-]+).*,\1,g;t;d' sos_commands/block/udevadm_info_.dev.$bcache_name`
        f=`grep -l ID_FS_UUID=$backing_dev_fs_uuid ./sos_commands/block/udevadm_info_.dev.*`
        backing_dev=${f##*.}

        dname=`grep ' disk/by-dname' ${block_root}$bcache_name| sed -r 's,.+/(.+),\1,g'`
        entry=$bcache_name
        if [ -e "${block_root}$bcache_name" ]; then
            entry="/dev/$bcache_name"
        fi

        if [ -n "$dname" ]; then
            entry="$entry (dname=$dname)"
            if [ -n "$backing_dev" ]; then
                entry="$entry (backing=/dev/$backing_dev)"
            fi
        fi

        echo $entry
    done| xargs -l -I{} echo "  - {}" >> $f_output
fi

unit_in_array ()
{
    unit="$1"
    shift
    echo $@| egrep -q "\s?${unit}\s?"
}

if $ctg_juju; then
    if [ -d "var/log/juju" ]; then
        echo -e "juju:" >> $f_output

        readarray -t ps_units<<<"`egrep unit-\* ps| sed -r 's,.+unit-([[:alnum:]\-]+-[[:digit:]]+).*,\1,g;t;d'| sort -u`"
        readarray -t log_units<<<"`find var/log/juju -name unit-\*| sed -r 's,.+unit-([[:alnum:]\-]+-[[:digit:]]+).*.log.*,\1,g;t;d'| sort -u`"
        combined_units=( `echo ${ps_units[@]} ${log_units[@]}| tr -s ' ' '\n'| sort -u` )

        readarray -t ps_machines<<<"`egrep machine-\* ps| sed -r 's,.+machine-([[:digit:]]+).*,\1,g;t;d'| sort -u`"
        readarray -t log_machines<<<"`find var/log/juju -name machine-\*| sed -r 's,.+machine-([[:digit:]]+).*.log.*,\1,g;t;d'| sort -u`"

        declare -a juju_machine_running=()
        declare -a juju_machine_stopped=()
        
        for machine in ${log_machines[@]}; do
            agent_conf=var/lib/juju/agents/machine-${machine}/agent.conf
            version=unknown
            if [ -r "$agent_conf" ]; then
                version=`sed -r 's/upgradedToVersion:\s+(.+)/\1/g;t;d' $agent_conf`
            fi
            if unit_in_array $machine ${ps_machines[@]}; then
                juju_machine_running+=( "${machine} (version=$version)\n" )
            else
                juju_machine_stopped+=( "${machine}\n" )
            fi
        done

        declare -a juju_unit_local=()
        declare -a juju_unit_local_not_running=()
        declare -a juju_unit_nonlocal=()
        
        for unit in ${combined_units[@]}; do
            if unit_in_array $unit ${log_units[@]}; then
                if unit_in_array $unit ${ps_units[@]}; then
                    juju_unit_local+=( "${unit}\n" )
                else
                    juju_unit_local_not_running+=( "${unit}\n" )
                fi
            else
                juju_unit_nonlocal+=( "${unit}\n" )
            fi
        done

        (("${#ps_machines[@]}")) && [ -n "${ps_machines[0]}" ] || ps_machines+=( null )
        echo -e "  machines:" >> $f_output
        echo -e "    running:" >> $f_output
        echo -e ${juju_machine_running[@]}| sort -u| xargs -l -I{} echo "      - {}" >> $f_output
        if ((${#juju_machine_stopped[@]})) && [ -n "${juju_machine_stopped[0]}" ]; then
            echo -e "    stopped:" >> $f_output
            echo -e ${juju_machine_stopped[@]}| sort -u| xargs -l -I{} echo "      - {}" >> $f_output
        fi

        echo -e "  units:" >> $f_output
        if (("${#ps_units[@]}"==0)) || [ -z "${ps_units[0]}" ]; then
            echo -e "    any:" >> $f_output
            echo "        - null" >> $f_output
        else
            echo -e "    running:" >> $f_output
            echo -e ${juju_unit_local[@]}| sort -u| xargs -l -I{} echo "      - {}" >> $f_output
            echo -e "    stopped:" >> $f_output
            echo -e ${juju_unit_local_not_running[@]}| sort -u| xargs -l -I{} echo "      - {}" >> $f_output
            echo -e "    non-local (e.g. lxd):" >> $f_output
            if (("${#juju_unit_nonlocal[@]}"==0)) || [ -z "${juju_unit_nonlocal[0]}" ]; then
                juju_unit_nonlocal=( null )
            fi
            echo -e ${juju_unit_nonlocal[@]}| sort -u| xargs -l -I{} echo "      - {}" >> $f_output
        fi
    fi
fi

if $ctg_system; then
echo -e "system:" >> $f_output
sed -r 's/.+(load average:.+)/- \1/g' uptime|xargs -l -I{} echo "  {}" >> $f_output
echo "  - rootfs: `egrep ' /$' df`" >> $f_output
fi

if $ctg_kernel; then
    echo -e "kernel:" >> $f_output
    path=proc/cmdline
    if [ -e "$path" ]; then
        cat $path|xargs -l -I{} echo "  - {}" >> $f_output
    else
        echo "  - $path not found" >> $f_output
    fi

    echo -e "systemd:" >> $f_output
    path=sos_commands/systemd/systemctl_show_service_--all
    if [ -e "$path" ]; then
        if `egrep -q "CPUAffinity=.+" $path`; then
            egrep "CPUAffinity=.+" $path| sort -u|xargs -l -I{} echo "  - {}"  >> $f_output
        else
            echo "  - CPUAffinity not set"  >> $f_output
        fi
    else
        echo "  - null" >> $f_output
    fi
fi

)

if $write_to_file; then
    out=${sosreport_name}.summary
    mv $f_output $out
    echo "Summary written to $out"
else
    cat $f_output
    echo ""
    rm $f_output
fi

echo "INFO: see --help for more display options"

done
