#!/bin/bash -u
# Text Format
CSI='\033['
RES="${CSI}0m"
F_RED="${CSI}31m"
F_GRN="${CSI}32m"

: ${HOTSOS:=./scripts/hotsos}

declare -A PLUGIN_ROOTS=(
    [kubernetes]=./tests/unit/fake_data_root/kubernetes
    [openstack]=./tests/unit/fake_data_root/openstack
    [rabbitmq]=./tests/unit/fake_data_root/rabbitmq
    [storage]=./tests/unit/fake_data_root/storage/ceph-mon
    [vault]=./tests/unit/fake_data_root/vault
    [pacemaker]=./tests/unit/fake_data_root/vault
    [mysql]=./tests/unit/fake_data_root/vault
)
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
    local args=()
    local label=""
    local test_command=

    data_root=${PLUGIN_ROOTS[$plugin]:-$default}
    if [[ $type == short ]]; then
        args+=( --short )
        args+=( --user-summary )
        data_root=$dtmp/$plugin
        label=".short"
    fi
    test_command="${HOTSOS} --${plugin} ${args[*]} $data_root"
    echo -n "TEST: "
    echo -n "plugin=$plugin (${type:-full}) with DATA_ROOT=$data_root (${test_command}) ..."
    PYTHONPATH=. ${test_command} 2>/dev/null | \
        egrep -v "repo-info:|date:|version:" > $dtmp/$plugin$label
    litmus=examples/hotsos-example-${plugin}${label}.summary.yaml
    egrep -v "repo-info:|date:|version:" $litmus > $dtmp/$plugin.litmus
    if diff -Naur $dtmp/$plugin.litmus $dtmp/$plugin$label &> $dtmp/fail; then
        echo -e " [${F_GRN}PASS${RES}]"
    else
        echo -e " [${F_RED}FAIL${RES}]"
        cat $dtmp/fail
        result=false
    fi
}

cleanup() {
    echo "removing temporary workspace"
    rm -rf $dtmp
}

dtmp=`mktemp -d`
trap cleanup exit

default=${PLUGIN_ROOTS[openstack]}
for plugin in ${PLUGINS[@]}; do
    test_plugin $plugin
    test_plugin $plugin short
done
$result
