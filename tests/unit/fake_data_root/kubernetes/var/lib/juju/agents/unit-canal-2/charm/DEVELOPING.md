# Developing layer-canal

## Installing build dependencies

To install build dependencies:

```
sudo snap install charm --classic
sudo apt install docker.io
sudo usermod -aG docker $USER
```

After running these commands, terminate your shell session and start a new one
to pick up the modified user groups.

## Building the charm

To build the charm:
```
charm build
```

By default, this will build the charm and place it in
`/tmp/charm-builds/canal`.

## Building resources

To build resources:
```
./build-canal-resources.sh
```

This will produce several .tar.gz files that you will need to attach to the
charm when you deploy it.

## Testing

You can test a locally built canal charm by deploying it with Charmed
Kubernetes.

Create a file named `local-canal.yaml` that contains the following (with paths
adjusted to fit your environment):
```
applications:
  canal:
    charm: /tmp/charm-builds/canal
    resources:
      calico: /path/to/layer-canal/calico-amd64.tar.gz
      calico-upgrade: /path/to/layer-canal/calico-upgrade-amd64.tar.gz
      flannel: /path/to/layer-canal/flannel-amd64.tar.gz
```

Then deploy Charmed Kubernetes with your locally built canal charm:

```
juju deploy cs:~containers/canonical-kubernetes-canal --overlay local-canal.yaml
```

## Helpful links

* [Getting Started with charm development](https://jaas.ai/docs/getting-started-with-charm-development)
* [Charm tools documentation](https://jaas.ai/docs/charm-tools)
* [Charmed Kubernetes Canal documentation](https://ubuntu.com/kubernetes/docs/cni-canal)
