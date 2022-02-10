# interface-container-runtime

## Overview

This interface handles communication between subordinate charms, that provide a container runtime and charms requiring a container runtime.

## Usage

### Provides

The providing side of the container interface provides a place for a container runtime to connect to.

Your charm should respond to the `endpoint.{endpoint_name}.available` state,
which indicates that there is a container runtime connected.

A trivial example of handling this interface would be:

```python
@when('endpoint.containerd.joined')
def update_kubelet_config(containerd):
    endpoint = endpoint_from_flag('endpoint.containerd.joined')
    config = endpoint.get_config()
    kubelet.config['container-runtime'] = \
        config['runtime']
```

### Requires

The requiring side of the container interface requires a place for a container runtime to connect to.

Your charm should set `{endpoint_name}.available` state,
which indicates that the container is runtime connected.

A trivial example of handling this interface would be:

```python
@when('endpoint.containerd.joined')
def pubish_config():
    endpoint = endpoint_from_flag('endpoint.containerd.joined')
    endpoint.set_config(
        socket='unix:///var/run/containerd/containerd.sock',
        runtime='remote',
        nvidia_enabled=False
    )
```
