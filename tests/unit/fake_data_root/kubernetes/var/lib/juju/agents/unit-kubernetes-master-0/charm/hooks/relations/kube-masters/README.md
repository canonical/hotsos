# kube-masters interface

This interface provides communication amongst kubernetes-masters in a cluster.

## States

* `kube-masters.connected`

  Enabled when any kubernetes-master unit has joined the relation.

* `kube-masters.cohorts.ready`

  Enabled when all peers have snap cohort data.

### Methods and Properties

* `kube-masters.set_cohort_keys(cohort_keys)`

  Set a dictionary of cohort keys created by the snap layer.

* `kube-masters.cohort_keys`

  Dictionary of all cohort keys sent by peers.

### Examples

```python

@when('kube-masters.connected')
def agree_on_cohorts():
    kube_masters = endpoint_from_flag('kube-masters.connected')
    cohort_keys = create_cohorts_for_my_snaps()
    kube_masters.set_cohort_keys(cohort_keys)

@when('kube-masters.cohorts.ready',
      'kube-control.connected')
def send_cohorts_to_workers():
    kube_masters = endpoint_from_flag('kube-masters.cohorts.ready')
    cohort_keys = kube_masters.cohort_keys

    kube_control = endpoint_from_flag('kube-control.connected')
    # The following set method is defined in interface-kube-control
    kube_control.set_cohort_keys(cohort_keys)

```
