#!/bin/bash -u
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
#  - edward.hope-morley@canonical.com
#  - opentastic@gmail.com

declare -a sos_paths=()
SAVE_OUTPUT=false
export VERBOSITY_LEVEL=0
# standard indentation to be used by all plugins
export INDENT_STR="  - "

# import helpers functions
. `dirname $0`/helpers

# ordered
declare -a PLUG_KEYS=( openstack kubernetes storage juju kernel system )
# unordered
declare -A PLUGINS=(
    [openstack]=false
    [kubernetes]=false
    [storage]=false
    [juju]=false
    [kernel]=false
    [system]=false
    [all]=false
)

# plugin args - prefix must be plugin name
export OPENSTACK_SHOW_CPU_PINNING_RESULTS=false

usage ()
{
cat << EOF
USAGE: hotsos [OPTIONS] SOSPATH

OPTIONS
    -h|--help
        This message.
    --juju
        Include Juju info.
    --kernel
        Include Kernel info.
    --list-plugins
        Show available plugins.
    --openstack
        Include Openstack services info.
    --openstack-show-cpu-pinning-results
        The Openstack plugin will check for cpu pinning configurations and
        perform checks. By default only brief messgaes will be displayed when
        issues are found. Use this flag to get more detailed results.
    --kubernetes
        Include info about Kubernetes
    --storage
        Include storage info including Ceph.
    --system
        Include system info.
    -s|--save
        Save output to a file.
    -a|--all
        Enable all plugins.
    -v
        Increase amount of information displayed.

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
        --juju)
            PLUGINS[juju]=true
            ;;
        --openstack)
            PLUGINS[openstack]=true
            ;;
        --openstack-show-cpu-pinning-results)
            OPENSTACK_SHOW_CPU_PINNING_RESULTS=true
            ;;
        --storage)
            PLUGINS[storage]=true
            ;;
        --kernel)
            PLUGINS[kernel]=true
            ;;
        --kubernetes)
            PLUGINS[kubernetes]=true
            ;;
        --list-plugins)
            echo "Available plugins:"
            echo "${!PLUGINS[@]}"| tr ' ' '\n'| grep -v all| xargs -l -I{} echo " - {}"
            exit
            ;;
        --system)
            PLUGINS[system]=true
            ;;
        -s|--save)
            SAVE_OUTPUT=true
            ;;
        -a|--all)
            PLUGINS[all]=true
            ;;
        -v)
            VERBOSITY_LEVEL=1
            ;;
        -vv)
            VERBOSITY_LEVEL=2
            ;;
        -vv*)
            VERBOSITY_LEVEL=3
            ;;
        *)
            [[ -d $1 ]] || { echo "ERROR: invalid path '$1'"; exit 1; }
            sos_paths+=( $1 )
            ;;
    esac
    shift
done

((${#sos_paths[@]})) || sos_paths=( / )

if ${PLUGINS[all]}; then
    PLUGINS[openstack]=true
    PLUGINS[storage]=true
    PLUGINS[juju]=true
    PLUGINS[kernel]=true
    PLUGINS[kubernetes]=true
    PLUGINS[system]=true
fi

F_OUT=`mktemp`
CWD=$(dirname `realpath $0`)
for data_root in ${sos_paths[@]}; do
    (
    if [ "$data_root" = "/" ]; then
        echo -e "INFO: running against localhost since no sosreport path provided\n" 1>&2
        export DATA_ROOT=/
    else
        cd $data_root
        export DATA_ROOT=./
    fi

    echo "general: " > $F_OUT
    _hostname=
    [ -r "$DATA_ROOT/hostname" ] && _hostname=`cat $DATA_ROOT/hostname` || _hostname=`hostname`
    echo -e "  hostname: $_hostname" >> $F_OUT
    data_source=$DATA_ROOT/etc/lsb-release
    if [ -s $data_source ]; then
       series=`sed -r 's/DISTRIB_CODENAME=(.+)/\1/g;t;d' $data_source`
        s_0=${series:0:1}  # capitalise first char
       echo -e "  os: Ubuntu ${s_0^^}${series:1}" >> $F_OUT
    fi

    for plugin in ${PLUG_KEYS[@]}; do
        [ "$plugin" = "all" ] && continue
        ${PLUGINS[$plugin]} || continue
        for plug in `find $CWD/plugins/$plugin/ -type f| sort -n`; do
            $plug >> $F_OUT
        done
    done
    )

    if $SAVE_OUTPUT; then
        if [[ $data_root != "/" ]]; then
            archive_name=`basename $data_root`
        else
            archive_name="hotsos-`hostname`"
        fi
        out=${archive_name}.summary
        mv $F_OUT $out
        echo "Summary written to $out"
    else
        cat $F_OUT
        echo "" 1>&2
        rm $F_OUT
    fi

    echo "INFO: see --help for more display options" 1>&2
done
