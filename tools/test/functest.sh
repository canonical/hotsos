#!/bin/bash -u
# Text Format
CSI='\033['
RES="${CSI}0m"
F_RED="${CSI}31m"
F_GRN="${CSI}32m"

dtmp=`mktemp -d`
declare -A PLUGIN_ROOTS=(
    [kubernetes]=./tests/unit/fake_data_root/kubernetes
    [openstack]=./tests/unit/fake_data_root/openstack
    [rabbitmq]=./tests/unit/fake_data_root/rabbitmq
    [storage]=./tests/unit/fake_data_root/storage/ceph-mon
    [vault]=./tests/unit/fake_data_root/vault
    [pacemaker]=./tests/unit/fake_data_root/vault
    [mysql]=./tests/unit/fake_data_root/vault
)
DEFAULT_DATA_ROOT=${PLUGIN_ROOTS[openstack]}
PLUGINS=(
    openstack
    openvswitch
    kubernetes
    storage
    juju
    kernel
    maas
    rabbitmq
    sosreport
    system
    vault
    pacemaker
    mysql
)
result=true


test_plugin ()
{
    local plugin=$1
    local type=${2:-}
    local data_root=$3
    local args=()
    local label=""
    local msg

    msg="TEST: "
    msg+="plugin=$plugin (${type:-full}) with DATA_ROOT=$data_root ..."
    if [[ $type == short ]]; then
        args+=( --short )
        label=".short"
    fi
    # NOTE: we remove repo-info, date and INFO from hotsos and system plugin
    #       output since they are liable to change.
    ./scripts/hotsos --${plugin} ${args[@]} $data_root 2>/dev/null| \
        egrep -v "^  repo-info:|date:|INFO:" > $dtmp/$plugin$label
    litmus=examples/hotsos-example-${plugin}${label}.summary.yaml
    egrep -v "^  repo-info:|date:|INFO:" $litmus > $dtmp/$plugin.litmus
    if diff $dtmp/$plugin.litmus $dtmp/$plugin$label &> $dtmp/fail; then
        echo -e "$msg [${F_GRN}PASS${RES}]"
    else
        echo -e "$msg [${F_RED}FAIL${RES}]"
        cat $dtmp/fail
        result=false
    fi
}

# this is needed for github workflows to work
export PYTHONPATH=.

echo "INFO: Starting functional tests for plugins: ${PLUGINS[@]}"
for plugin in ${PLUGINS[@]}; do
    test_plugin $plugin "" ${PLUGIN_ROOTS[$plugin]:-$DEFAULT_DATA_ROOT} &
    test_plugin $plugin short ${PLUGIN_ROOTS[$plugin]:-$DEFAULT_DATA_ROOT} &
done

# wait for all plugin tests
wait

echo "INFO: testing running hotsos with --save:"
# do a test run with --save to be sure we havent broken anything
./scripts/hotsos --kernel --save --output-path $dtmp

rm -rf $dtmp
$result
