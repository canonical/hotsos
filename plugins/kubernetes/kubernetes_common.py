from common import checks

SERVICES = ["etcdctl",
            "calicoctl",
            "flanneld",
            "kubectl2",
            "kubelet",
            "containerd-shim",
            "containerd",
            "dockerd",
            "kubelet",
            "kube-proxy",
            "calico-node",
            ]

# Snaps that only exist in a K8s deployment
SNAPS_K8S = [r'charm[\S]+',
             r'conjure-up',
             r'cdk-addons',
             r'helm',
             r'kubernetes-[\S]+',
             r'kube-[\S]+',
             r'kubectl',
             r'kubelet',
             r'kubeadm',
             r'kubefed',
             ]
# Snaps that are used in a K8s deployment
SNAPS_DEPS = [r'core[0-9]*',
              r'docker',
              r'go',
              r'vault',
              r'etcd',
              ]


class KubernetesChecksBase(checks.ServiceChecksBase):

    def __init__(self):
        super().__init__(SERVICES, hint_range=(0, 3))
