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
)
result=true


test_plugin ()
{
    local plugin=$1
    local type=${2:-}
    local args=()
    local label=""

    data_root=${PLUGIN_ROOTS[$plugin]:-$default}
    echo -n "TEST: "
    echo -n "plugin=$plugin (${type:-full}) with DATA_ROOT=$data_root ..."
    if [[ $type == short ]]; then
        args+=( --short )
        label=".short"
    fi
    ${HOT_DIR}/hotsos.sh --${plugin} ${args[@]} $data_root 2>/dev/null| \
        grep -v repo-info > $dtmp/$plugin
    litmus=examples/hotsos-example-${plugin}${label}.summary.yaml
    grep -v repo-info $litmus > $dtmp/$plugin.litmus
    diff $dtmp/$plugin.litmus $dtmp/$plugin &> $dtmp/fail
    if (($?==0)); then
        echo -e " [${F_GRN}PASS${RES}]"
    else
        echo -e " [${F_RED}FAIL${RES}]"
        cat $dtmp/fail
        result=false
    fi
}


default=${PLUGIN_ROOTS[openstack]}
for plugin in ${PLUGINS[@]}; do
    test_plugin $plugin
    test_plugin $plugin short
done
rm -rf $dtmp
$result
