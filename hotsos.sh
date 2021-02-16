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
# Authors:
#  - edward.hope-morley@canonical.com
#  - opentastic@gmail.com


# These globals are made available to all plugins
export VERBOSITY_LEVEL=0
export DATA_ROOT
# plugin args - prefix must be plugin name
export OPENSTACK_SHOW_CPU_PINNING_RESULTS=false
# This is the path to the end product that plugins can see along the way.
export MASTER_YAML_OUT

# import helpers functions
. `dirname $0`/common/helpers.sh

SAVE_OUTPUT=false
declare -a SOS_PATHS=()
# unordered
declare -A PLUGINS=(
    [openstack]=false
    [kubernetes]=false
    [storage]=false
    [juju]=false
    [kernel]=false
    [system]=true  # always do system by default
    [all]=false
)
# output ordering
declare -a PLUGIN_NAMES=( system openstack kubernetes storage juju kernel )


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
            SOS_PATHS+=( $1 )
            ;;
    esac
    shift
done

((${#SOS_PATHS[@]})) || SOS_PATHS=( / )

if ${PLUGINS[all]}; then
    PLUGINS[openstack]=true
    PLUGINS[storage]=true
    PLUGINS[juju]=true
    PLUGINS[kernel]=true
    PLUGINS[kubernetes]=true
    PLUGINS[system]=true
fi

get_git_rev_info ()
{
    pushd `dirname $0` &>/dev/null
    git rev-parse --short HEAD 2>/dev/null
    popd &>/dev/null
}

MASTER_YAML_OUT=`mktemp`
CWD=$(dirname `realpath $0`)
for data_root in ${SOS_PATHS[@]}; do
    if [ "$data_root" = "/" ]; then
        echo -e "INFO: running against localhost since no sosreport path provided\n" 1>&2
        DATA_ROOT=/
    else
        DATA_ROOT=$data_root
    fi

    if ! [ "${DATA_ROOT:(-1)}" = "/" ]; then
        # Ensure trailing slash
        export DATA_ROOT="${DATA_ROOT}/"
    fi

    if [[ -n ${REPO_INFO_PATH:-""} ]] && [[ -r $REPO_INFO_PATH ]]; then
        repo_info=`cat $REPO_INFO_PATH`
    else
        repo_info=`get_git_rev_info` || repo_info="unknown" 
    fi
    echo -e "hotsos:\n  version: ${SNAP_REVISION:-"development"}\n  repo-info: $repo_info" > $MASTER_YAML_OUT

    for plugin in ${PLUGIN_NAMES[@]}; do
        # skip this since not a real plugin
        [ "$plugin" = "all" ] && continue
        # is plugin enabled?
        ${PLUGINS[$plugin]} || continue

        for priority in {00..99}; do
            for plug in `find $CWD/plugins/$plugin -name $priority\*| grep -v __pycache__`; do
                $plug >> $MASTER_YAML_OUT
            done
        done
    done

    if $SAVE_OUTPUT; then
        if [[ $data_root != "/" ]]; then
            archive_name=`basename $data_root`
        else
            archive_name="hotsos-`hostname`"
        fi
        out=${archive_name}.summary
        mv $MASTER_YAML_OUT $out
        echo "Summary written to $out"
    else
        cat $MASTER_YAML_OUT
        echo "" 1>&2
        rm $MASTER_YAML_OUT
    fi

    echo "INFO: see --help for more display options" 1>&2
done
