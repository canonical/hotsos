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


DEBUG_MODE=false
# These globals are made available to all plugins
export VERBOSITY_LEVEL=0
export DATA_ROOT
# plugin args - prefix must be plugin name
export OPENSTACK_SHOW_CPU_PINNING_RESULTS=false
export OPENSTACK_AGENT_ERROR_KEY_BY_TIME=false
# This is the path to the end product that plugins can see along the way.
export MASTER_YAML_OUT
export USE_ALL_LOGS=false
# this is set to the name of the current plugin being executed
export PLUGIN_NAME
# This is a scratch area for each plugin to use and a fresh one is created at
# the start of each plugin execution then destroyed once all parts are
# executed.
export PLUGIN_TMP_DIR

# import helpers functions
. `dirname $0`/common/helpers.sh

MASTER_YAML_OUT=`mktemp`
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
override_all_default=false
# output ordering
declare -a PLUGIN_NAMES=( system openstack kubernetes storage juju kernel )

cleanup ()
{
    if [[ -n $MASTER_YAML_OUT ]] && [[ -r $MASTER_YAML_OUT ]]; then
        rm $MASTER_YAML_OUT
    fi
    if [[ -n $PLUGIN_TMP_DIR ]] && [[ -d $PLUGIN_TMP_DIR ]]; then
        rm -rf $PLUGIN_TMP_DIR
    fi
    exit
}

trap cleanup KILL INT EXIT

usage ()
{
cat << EOF
USAGE: hotsos [OPTIONS] [SOSPATH]

Run this tool against a sosreport or live host to extract information that may
be helpful for analysing or debugging applications like Openstack, Kubernetes,
Ceph and more (see supported plugins). The standard output is yaml format to
allow easy visual inspection and post-processing by other tools.

OPTIONS
    --debug)
        Provide some debug output such as plugin execution times.
    -h|--help
        This message.
    --juju
        Use the Juju plugin.
    --kernel
        Use the Kernel plugin.
    --list-plugins
        Show available plugins.
    --max-parallel-tasks [INT]
        The searchtools module will execute searches across files in parallel.
        By default the number of cores used is limited to a maximum of 8 and
        you can override that value with this option.
    --openstack
        Use the Openstack plugin.
    --openstack-show-cpu-pinning-results
        The Openstack plugin will check for cpu pinning configurations and
        perform checks. By default only brief messgaes will be displayed when
        issues are found. Use this flag to get more detailed results.
    --openstack-agent-error-key-by-time
        When displaying agent error counts, they will be grouped by date. This
        option will result in grouping by date_time which may be more useful
        for cross-referencing with other logs.
    --kubernetes
        Use the Kubernetes plugin.
    --storage
        Use the Storage plugin.
    --system
        Use the System plugin.
    -s|--save
        Save yaml output to a file.
    --all-logs
        Some plugins may choose to only analyse the most recent version of a
        log file by default since parsing the full history could take a lot
        longer. Setting this to true tells plugins that we wish to analyse
        all available log history.
    -a|--all
        Enable all plugins. This is the default.
    -v
        Increase amount of information displayed.

SOSPATH
    Path to a sosreport. Can be provided multiple times. If none provided,
    will run against local host.

EOF
}

while (($#)); do
    case $1 in
        --debug)
            DEBUG_MODE=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
## PLUGINS ############
        --juju)
            override_all_default=true
            PLUGINS[juju]=true
            ;;
        --kernel)
            override_all_default=true
            PLUGINS[kernel]=true
            ;;
        --kubernetes)
            override_all_default=true
            PLUGINS[kubernetes]=true
            ;;
        --openstack)
            override_all_default=true
            PLUGINS[openstack]=true
            ;;
        --system)
            override_all_default=true
            PLUGINS[system]=true
            ;;
        --storage)
            override_all_default=true
            PLUGINS[storage]=true
            ;;
#######################
## PLUGIN OPTS ########
        --openstack-show-cpu-pinning-results)
            OPENSTACK_SHOW_CPU_PINNING_RESULTS=true
            ;;
        --openstack-agent-error-key-by-time)
            OPENSTACK_AGENT_ERROR_KEY_BY_TIME=true
            ;;
#######################
        --list-plugins)
            echo "Available plugins:"
            echo "${!PLUGINS[@]}"| tr ' ' '\n'| grep -v all| xargs -l -I{} echo " - {}"
            exit
            ;;
        --max-parallel-tasks)
            export USER_MAX_PARALLEL_TASKS=$2
            shift
            ;;
        -s|--save)
            SAVE_OUTPUT=true
            ;;
        -a|--all)
            PLUGINS[all]=true
            ;;
        --all-logs)
            USE_ALL_LOGS=true
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

if ! $override_all_default && ! ${PLUGINS[all]}; then
    PLUGINS[all]=true
fi

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

    $DEBUG_MODE && echo -e "Running plugins:\n" 1>&2
    for plugin in ${PLUGIN_NAMES[@]}; do
        # skip this since not a real plugin
        [ "$plugin" = "all" ] && continue
        # is plugin enabled?
        ${PLUGINS[$plugin]} || continue
        $DEBUG_MODE && echo -e "${plugin^^}:  " 1>&2

        PLUGIN_NAME=$plugin
        # setup plugin temp area
        PLUGIN_TMP_DIR=`mktemp -d`

        for priority in {00..99}; do
            for part in `find $CWD/plugins/$plugin -name $priority\*| grep -v __pycache__`; do
                t_start=`date +%s%3N`
                $DEBUG_MODE && echo -n " `basename $part`" 1>&2
                $part >> $MASTER_YAML_OUT
                t_end=`date +%s%3N`
                $DEBUG_MODE && echo " (`echo \"scale=3;($t_end-$t_start)/1000\"| bc`s)" 1>&2
            done
        done

        # teardown plugin temp area
        if [[ -n $PLUGIN_TMP_DIR ]] && [[ -d $PLUGIN_TMP_DIR ]]; then
            rm -rf $PLUGIN_TMP_DIR
        fi

        $DEBUG_MODE && echo "" 1>&2
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
        $DEBUG_MODE && echo "Results:" 1>&2
        cat $MASTER_YAML_OUT
        echo "" 1>&2
        rm $MASTER_YAML_OUT
    fi

    echo "INFO: see --help for more display options" 1>&2
done
