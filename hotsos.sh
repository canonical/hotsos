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

#================================= ENV =========================================
# The following are made available to all plugins

export DEBUG_MODE=false
# Root of all data which will be either host / or sosreport root.
export DATA_ROOT
# Plugin args - prefix must be plugin name
export AGENT_ERROR_KEY_BY_TIME=false
# Output format - default is yaml
export OUTPUT_FORMAT='yaml'
# Path to the end product that plugins can see along the way.
export MASTER_YAML_OUT=`mktemp`
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
export HOTSOS_ROOT
export MINIMAL_MODE=
#===============================================================================

PROGRESS_PID=
FULL_MODE_EXPLICIT=false
USER_PROVIDED_SUMMARY=
MASTER_YAML_OUT_ORIG=`mktemp`
SAVE_OUTPUT=false
VERSION="${SNAP_REVISION:-development}"
declare -a SOS_PATHS=()
override_all_default=false
# Ordering is not important here since associative arrays do not respect order.
declare -A PLUGINS=(
    [openstack]=false
    [openvswitch]=false
    [kubernetes]=false
    [storage]=false
    [juju]=false
    [kernel]=false
    [maas]=false
    [rabbitmq]=false
    [sosreport]=false
    [system]=true  # always do system by default
    [vault]=false
    [all]=false
)
# The order of the following list determines the order in which the plugins
# output is presented in the summary.
declare -a PLUGIN_NAMES=(
    system
    sosreport
    openstack
    openvswitch
    rabbitmq
    kubernetes
    storage
    vault
    juju
    maas
    kernel
)

cleanup ()
{
    if [[ -n $MASTER_YAML_OUT_ORIG ]] && [[ -r $MASTER_YAML_OUT_ORIG ]]; then
        rm $MASTER_YAML_OUT_ORIG
    fi
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
hotsos (version: ${VERSION})

USAGE: hotsos [OPTIONS] [SOSPATH]

Run this tool on a host or against a sosreport to perform analysis of specific
applications. A summary of information about those applications is generated
along with any issues or known bugs detected. Applications are defined as
plugins and support currently includes Openstack, Kubernetes, Ceph and more
(see --list-plugins). The standard output is yaml format to allow easy visual
inspection and post-processing by other tools.

OPTIONS
    --all-logs
        Some plugins may choose to only analyse the most recent version of a
        log file by default since parsing the full history could take a lot
        longer. Setting this to true tells plugins that we wish to analyse
        all available log history (see --max-logrotate-depth for limits).
    --debug
        Provide some debug output such as plugin execution times. For python
        plugins this will print debug logs to stderr.
    --full
        This is the default and tells hotsos to generate a full summary. If you
        want to save both a short and full summary you can specifiy this option
        when doing --short.
    -h|--help
        This message.
    --json
        Output in json format.
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
        for a given log. Only applies when --all-logs is provided.
    --short
        Filters the full summary so that it only includes plugin known-bugs
        and potential-issues sections.
    --very-short
        Minimal version of --short where only issue types or bug ids are
        displayed with count of each (issues only).
    -s|--save
        Save yaml output to a file.
    --user-summary
        Provide an existing summary so that it can be post-procesed e.g.
        --json or --short. An alternative is to simply pipe the summary
	contents to stdin.
    --version
        Show the version.

PLUGIN OPTIONS
  These options only apply to specific plugins.

  openstack:
    --agent-error-key-by-time
        When displaying agent error counts, they will be grouped by date. This
        option will result in grouping by date and time which may be more useful
        for cross-referencing with other logs.

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
        -v|--version)
            echo "${VERSION}"
            exit 0
            ;;
## PLUGIN OPTS ########
        --agent-error-key-by-time)
            AGENT_ERROR_KEY_BY_TIME=true
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
        --json)
            OUTPUT_FORMAT=json
            ;;
        -a|--all)
            PLUGINS[all]=true
            ;;
        --full)
            FULL_MODE_EXPLICIT=true
            ;;
        --short)
            MINIMAL_MODE='short'
            ;;
        --very-short)
            MINIMAL_MODE='very-short'
            ;;
        --user-summary)
            USER_PROVIDED_SUMMARY=$2
            shift
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
    export PYTHONPATH="${HOTSOS_ROOT}"
    export PLUGIN_YAML_DEFS="${HOTSOS_ROOT}/defs"

    ${HOTSOS_ROOT}/plugins/$plugin/$part

    t_end=`date +%s%3N`
    delta=`echo "scale=3;($t_end-$t_start)/1000"| bc`
    [[ ${delta::1} == '.' ]] && delta="0${delta}"
    $DEBUG_MODE && echo " (${delta}s)" 1>&2
}

generate_summary ()
{
    local data_root=$1
    local repo_info
    local plugin
    local part

    if [ "$data_root" = "/" ]; then
        echo -ne "INFO: analysing localhost  " 1>&2
        DATA_ROOT=/
    else
        echo -ne "INFO: analysing sosreport $data_root  " 1>&2
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

    cat <<EOF
hotsos:
  version: $VERSION
  repo-info: $repo_info
EOF

    for plugin in ${PLUGIN_NAMES[@]}; do
        # skip this since not a real plugin
        [ "$plugin" = "all" ] && continue
        # is plugin enabled?
        ${PLUGINS[$plugin]} || continue
        $DEBUG_MODE && echo -e "${plugin^^}:  " 1>&2

        PLUGIN_NAME=$plugin
        # setup plugin temp area
        PLUGIN_TMP_DIR=`mktemp -d`
        for part in $(find "${HOTSOS_ROOT}/plugins/$plugin" -maxdepth 1 \
                    -executable -type f,l| grep -v __pycache__); do
            run_part "$plugin" "$(basename "$part")"
        done
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
}

# Allow a summary to be piped in
if [[ -z $USER_PROVIDED_SUMMARY ]] && [[ ! -t 0 ]]; then
    USER_PROVIDED_SUMMARY=/dev/stdin
fi

HOTSOS_ROOT=$(dirname `realpath $0`)
for data_root in "${SOS_PATHS[@]}"; do
    if [[ -r $USER_PROVIDED_SUMMARY ]]; then
        cp $USER_PROVIDED_SUMMARY $MASTER_YAML_OUT
    else
        generate_summary "$data_root" > $MASTER_YAML_OUT
    fi

    # the following may overwrite the master copy so we need to make a
    # backup in case we intend to display short and full.
    cp $MASTER_YAML_OUT $MASTER_YAML_OUT_ORIG
    ${HOTSOS_ROOT}/tools/output_filter.py

    if $SAVE_OUTPUT; then
        if [[ -r $USER_PROVIDED_SUMMARY ]]; then
            output_name="`basename $USER_PROVIDED_SUMMARY`"
            output_name=${output_name%%.*}
        else
            if [[ $data_root != "/" ]]; then
                output_name=`basename $data_root`
            else
                output_name="hotsos-`hostname`"
            fi
        fi
        if [[ -n $MINIMAL_MODE ]]; then
            out=$output_name.short.summary
            mv $MASTER_YAML_OUT $out
            echo "INFO: short summary written to $out"
            if $FULL_MODE_EXPLICIT; then
                cp $MASTER_YAML_OUT_ORIG $MASTER_YAML_OUT
            fi
        fi
        if [[ -z $MINIMAL_MODE ]] || $FULL_MODE_EXPLICIT; then
            out=$output_name.summary
            mv $MASTER_YAML_OUT $out
            echo "INFO: full summary written to $out"
        fi
    else
        $DEBUG_MODE && echo "Results:" 1>&2
        cat $MASTER_YAML_OUT
        echo "" 1>&2
        rm $MASTER_YAML_OUT
    fi

    echo "INFO: see --help for more options" 1>&2
done
