# layer-canal devs: How to bump Calico release versions

TODO: fix this lousy process

1. Check the component versions: https://docs.projectcalico.org/v2.6/releases/
   (substitute v2.6 for latest version)
2. Update calicoctl and calico-cni versions in build-calico-resource.sh
3. Update calico-node image in config.yaml
   (used in templates/calico-node.service)
4. Update calico-policy-controller image in config.yaml
   (used in templates/calico-policy-controller.yaml)
5. Update calico_version in reactive/canal.py set_canal_version function
