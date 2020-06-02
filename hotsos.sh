#!/bin/bash -eu
# Copyright 2020 opentastic@gmail.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Origin: https://github.com/dosaboy/hotsos
#
# Description:
#  Generate a high-level summary of a sosreport.
#
# Authors:
#${indent_str}edward.hope-morley@canonical.com
#${indent_str}opentastic@gmail.com

indent_str="  - "
declare -a sos_paths=()
write_to_file=false

declare -A PLUGINS=(
    [versions]=false
    [openstack]=false
    [storage]=false
    [juju]=false
    [kernel]=false
    [system]=false
    [all]=false
)

usage ()
{
cat << EOF
USAGE: hotsos [OPTIONS] SOSPATH

OPTIONS
    -h|--help
        This message.
    --juju
        Include Juju info.
    --openstack
        Include Openstack services info.
    --kernel
        Include Kernel info.
    --storage
        Include storage info including Ceph.
    --system
        Include system info.
    --versions
        Include software version info.
    -s|--save
        Save output to a file.
    -a|--all
        Enable all plugins.

SOSPATH
    Path to a sosreport. Can be provided multiple times.

EOF
}

while (($#)); do 
    case $1 in
          -h|--help)
              usage
              exit 0
              ;;
          --versions)
              PLUGINS[versions]=true
              ;;
          --juju)
              PLUGINS[juju]=true
              ;;
          --openstack)
              PLUGINS[openstack]=true
              ;;
          --storage)
              PLUGINS[storage]=true
              ;;
          --kernel)
              PLUGINS[kernel]=true
              ;;
          --system)
              PLUGINS[system]=true
              ;;
          -s|--save)
              write_to_file=true
              ;;
          -a|--all)
              PLUGINS[all]=true
              ;;
          *)
              sos_paths+=( $1 )
              ;;
    esac
    shift
done

unit_in_array ()
{
    unit="$1"
    shift
    echo $@| egrep -q "\s?${unit}\s?"
}

((${#sos_paths[@]})) || { usage; exit 1; }
((${#sos_paths[@]})) || sos_paths=( . )

if ${PLUGINS[all]}; then
    PLUGINS[versions]=true
    PLUGINS[openstack]=true
    PLUGINS[storage]=true
    PLUGINS[juju]=true
    PLUGINS[kernel]=true
    PLUGINS[system]=true
fi

f_output=`mktemp`
CWD=`dirname $0`
for root in ${sos_paths[@]}; do
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

echo -e "hostname:\n${indent_str}`cat hostname`" > $f_output
for plugin in ${!PLUGINS[@]}; do
    [ "$plugin" = "all" ] && continue
    ${PLUGINS[$plugin]} && . $CWD/plugins/$plugin
done
)

if $write_to_file; then
    sosreport_name=`basename $root`
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
