# interface-untrusted-container-runtime

## Overview

This interface handles communication between subordinate container runtimes
and this subordinate untrusted container runtime, such as `containerd` and
`kata-containers`.

## Usage

### Provides

The providing side of the container interface provides a place for an
untrusted container runtime to connect to.

Your charm should respond to the `endpoint.{endpoint_name}.available` state,
which indicates that there is an untrusted container runtime connected.

A trivial example of handling this interface would be:

```python
@when('endpoint.containerd.joined')
def update_kubelet_config(containerd):
    endpoint = endpoint_from_flag('endpoint.containerd.joined')
    config = endpoint.get_config()

    render(
        'config.toml',
        {
            'runtime_name': config['name'],
            'runtime_binary': config['binary_path']
        }
    )
```

### Requires

The requiring side of the untrusted container interface requires a place for
an untrusted container runtime to connect to.

Your charm should set `{endpoint_name}.available` state,
which indicates that the container is runtime connected.

A trivial example of handling this interface would be:

```python
@when('endpoint.containerd.joined')
def pubish_config():
    endpoint = endpoint_from_flag('endpoint.containerd.joined')
    endpoint.set_config(
        'name': 'kata',
        'binary_path': '/usr/bin/kata-runtime'
    )
```
