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

PROGRESS_PID=
DEBUG_MODE=false
MIMIMAL_MODE=false

#================================= ENV =========================================
# The following are made available to all plugins

# Root of all data which will be either host / or sosreport root.
export DATA_ROOT
# Plugin args - prefix must be plugin name
export OPENSTACK_SHOW_CPU_PINNING_RESULTS=false
export OPENSTACK_AGENT_ERROR_KEY_BY_TIME=false
# Path to the end product that plugins can see along the way.
export MASTER_YAML_OUT
export USE_ALL_LOGS=false
# Name of the current plugin being executed
export PLUGIN_NAME
# Name of the current plugin part being executed
export PART_NAME
# Scratch area for each plugin to use. A fresh one is created at start of
# each plugin execution then destroyed once all parts are executed.
export PLUGIN_TMP_DIR
# location if yaml defs of issues, bugs etc
export PLUGIN_YAML_DEFS
#===============================================================================

MASTER_YAML_OUT=`mktemp`
SAVE_OUTPUT=false
declare -a SOS_PATHS=()
# optional part name to run
declare -a RUN_PARTS=()
# unordered
declare -A PLUGINS=(
    [openstack]=false
    [openvswitch]=false
    [kubernetes]=false
    [storage]=false
    [juju]=false
    [kernel]=false
    [rabbitmq]=false
    [system]=true  # always do system by default
    [all]=false
)
override_all_default=false
# output ordering
declare -a PLUGIN_NAMES=(
    system
    openstack
    openvswitch
    rabbitmq
    kubernetes
    storage
    juju
    kernel
)

cleanup ()
{
    if [[ -n $MASTER_YAML_OUT ]] && [[ -r $MASTER_YAML_OUT ]]; then
        rm $MASTER_YAML_OUT
    fi
    if [[ -n ${PLUGIN_TMP_DIR:-""} ]] && [[ -d $PLUGIN_TMP_DIR ]]; then
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
    --<plugin name>
        Use the specified plugin.
    --list-plugins
        Show available plugins.
    --max-parallel-tasks [INT]
        The searchtools module will execute searches across files in parallel.
        By default the number of cores used is limited to a maximum of 8 and
        you can override that value with this option.
    --max-logrotate-depth [INT]
        Defaults to 7. This is maximum logrotate history that will be searched
        for a given log.
    --openstack-show-cpu-pinning-results
        The Openstack plugin will check for cpu pinning configurations and
        perform checks. By default only brief messgaes will be displayed when
        issues are found. Use this flag to get more detailed results.
    --openstack-agent-error-key-by-time
        When displaying agent error counts, they will be grouped by date. This
        option will result in grouping by date_time which may be more useful
        for cross-referencing with other logs.
    --part
        Name of plugin part to run. May be specified multiple times.
    --short
        If provided, the output will be filtered to only include known-bugs
        and potential-issues sections for plugins run.
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
            echo "${!PLUGINS[@]}"| tr ' ' '\n'| grep -v all| \
                xargs -l -I{} echo " - {}"
            exit
            ;;
        --max-parallel-tasks)
            export MAX_PARALLEL_TASKS=$2
            shift
            ;;
        --max-logrotate-depth)
            export MAX_LOGROTATE_DEPTH=$2
            shift
            ;;
        -s|--save)
            SAVE_OUTPUT=true
            ;;
        -a|--all)
            PLUGINS[all]=true
            ;;
        --part)
            RUN_PARTS+=( $2 )
            shift
            ;;
        --short)
            MIMIMAL_MODE=true
            ;;
        --all-logs)
            USE_ALL_LOGS=true
            ;;
        *)
            plugin_provided=false
            for p in ${!PLUGINS[@]}; do
                if [[ ${1#--} == $p ]]; then
                    override_all_default=true
                    PLUGINS[$p]=true
                    plugin_provided=true
                    break
                fi
            done
            if ! $plugin_provided; then
                if ! [[ -d $1 ]]; then
                    echo "ERROR: invalid path or option '$1'"
                    exit 1
                fi
                SOS_PATHS+=( "$1" )
            fi
            ;;
    esac
    shift
done

if ((${#SOS_PATHS[@]}==0)); then
    SOS_PATHS=( / )
fi

if ! $override_all_default && ! ${PLUGINS[all]}; then
    PLUGINS[all]=true
fi

if ${PLUGINS[all]}; then
    for plugin in ${!PLUGINS[@]}; do
        PLUGINS[$plugin]=true
    done
fi

show_progress ()
{
    local progress_chars='-\|/'

    _cleanup ()
    {
        echo -e "\b " 1>&2
        exit
    }
    trap _cleanup HUP

    i=0
    while true; do
        i=$(((i+1) % ${#progress_chars}))
        printf "\b${progress_chars:$i:1}" 1>&2
        sleep .1
    done
}

get_git_rev_info ()
{
    pushd `dirname $0` &>/dev/null
    git rev-parse --short HEAD 2>/dev/null
    popd &>/dev/null
}

run_part ()
{
    local plugin=$1
    local part=$2
    local t_start
    local t_end

    t_start=`date +%s%3N`

    $DEBUG_MODE && echo -n " $part" 1>&2
    PART_NAME=$part

    # Needed by python plugins
    export PYTHONPATH="$CWD/plugins/$plugin"
    export PLUGIN_YAML_DEFS="$CWD/plugins/$plugin/defs"

    $CWD/plugins/$plugin/parts/$part >> $MASTER_YAML_OUT

    t_end=`date +%s%3N`
    delta=`echo "scale=3;($t_end-$t_start)/1000"| bc`
    [[ ${delta::1} == '.' ]] && delta="0${delta}"
    $DEBUG_MODE && echo " (${delta}s)" 1>&2
}

CWD=$(dirname `realpath $0`)
for data_root in "${SOS_PATHS[@]}"; do
    if [ "$data_root" = "/" ]; then
        if [[ ${SNAP_NAME:-""} = hotsos ]]; then
            echo "ERROR: it is not currently possible to run hotsos against a host using the snap due to confinement issues - see https://forum.snapcraft.io/t/classic-confinement-request-for-hotsos-snap for more info"
            echo -e "\nAs a workaround you can try running the snap code directly i.e. ${SNAP}/`basename $0`"
            echo -e "\nNOTE: using the workaround may require you to install dependencies"
            exit 1
        fi
        msg="analysing localhost since no sosreport path provided"
        echo -ne "INFO: $msg  " 1>&2
        DATA_ROOT=/
    else
        echo -ne "INFO: analysing sosreport at $data_root  " 1>&2
        DATA_ROOT=$data_root
    fi

    if $DEBUG_MODE; then
        echo -e "Running plugins:\n" 1>&2
    else
        show_progress &
        PROGRESS_PID=$!
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
    echo "hotsos:" > $MASTER_YAML_OUT
    echo "  version: ${SNAP_REVISION:-"development"}" >> $MASTER_YAML_OUT
    echo "  repo-info: $repo_info" >> $MASTER_YAML_OUT

    for plugin in ${PLUGIN_NAMES[@]}; do
        # skip this since not a real plugin
        [ "$plugin" = "all" ] && continue
        # is plugin enabled?
        ${PLUGINS[$plugin]} || continue
        $DEBUG_MODE && echo -e "${plugin^^}:  " 1>&2

        PLUGIN_NAME=$plugin
        # setup plugin temp area
        PLUGIN_TMP_DIR=`mktemp -d`

        if ((${#RUN_PARTS[@]})); then
            for part in ${RUN_PARTS[@]}; do
                [[ -r $CWD/plugins/$plugin/parts/$part ]] || continue
                run_part $plugin $part
            done
        else
            for part in `find $CWD/plugins/$plugin/parts -executable -type f| \
                    grep -v __pycache__`; do
                run_part $plugin `basename $part`
            done
        fi
        # must be run last after all others
        run_part utils 99known_bugs_and_issues_base
        # teardown plugin temp area
        if [[ -n $PLUGIN_TMP_DIR ]] && [[ -d $PLUGIN_TMP_DIR ]]; then
            rm -rf $PLUGIN_TMP_DIR
        fi

        $DEBUG_MODE && echo "" 1>&2
    done

    if [[ -n $PROGRESS_PID ]]; then
        kill -s HUP $PROGRESS_PID &>/dev/null
        wait &>/dev/null
    fi

    if $MIMIMAL_MODE; then
        $CWD/tools/output_filter.py $MASTER_YAML_OUT
    fi

    if $SAVE_OUTPUT; then
        if [[ $data_root != "/" ]]; then
            archive_name=`basename $data_root`
        else
            archive_name="hotsos-`hostname`"
        fi
        out=${archive_name}.summary
        mv $MASTER_YAML_OUT $out
        echo "INFO: summary written to $out"
    else
        $DEBUG_MODE && echo "Results:" 1>&2
        cat $MASTER_YAML_OUT
        echo "" 1>&2
        rm $MASTER_YAML_OUT
    fi

    echo "INFO: see --help for more options" 1>&2
done
