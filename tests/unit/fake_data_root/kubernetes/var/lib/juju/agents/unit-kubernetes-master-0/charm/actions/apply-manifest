#!/usr/local/sbin/charm-env python3
import os
import json
import tempfile
import subprocess
from charmhelpers.core.hookenv import action_get, action_set, action_fail, action_name


def _kubectl(args):
    """
    Executes kubectl with args as arguments
    """
    snap_bin = os.path.join(os.sep, "snap", "bin")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([snap_bin, env["PATH"]])
    cmd = ["kubectl", "--kubeconfig=/home/ubuntu/config"]
    cmd.extend(args)
    return subprocess.check_output(
        cmd,
        env=env,
        stderr=subprocess.STDOUT,
    )


def get_kubeconfig():
    """
    Read the kubeconfig on the master and return it as JSON
    """
    try:
        result = _kubectl(["config", "view", "-o", "json", "--raw"])
        # JSON format verification
        kubeconfig = json.dumps(json.loads(result))
        action_set({"kubeconfig": kubeconfig})
    except json.JSONDecodeError as e:
        action_fail("Failed to parse kubeconfig: {}".format(str(e)))
    except Exception as e:
        action_fail("Failed to retrieve kubeconfig: {}".format(str(e)))


def apply_manifest():
    """
    Applies a user defined manifest with kubectl
    """
    _, apply_path = tempfile.mkstemp(suffix=".json")
    try:
        manifest = json.loads(action_get("json"))
        with open(apply_path, "w") as manifest_file:
            json.dump(manifest, manifest_file)
        output = _kubectl(["apply", "-f", apply_path])

        action_set(
            {
                "summary": "Manifest applied.",
                "output": output.decode("utf-8"),
            }
        )
    except subprocess.CalledProcessError as e:
        action_fail(
            "kubectl failed with exit code {} and message: {}".format(
                e.returncode, e.output
            )
        )
    except json.JSONDecodeError as e:
        action_fail("Failed to parse JSON manifest: {}".format(str(e)))
    except Exception as e:
        action_fail("Failed to apply manifest: {}".format(str(e)))
    finally:
        os.unlink(apply_path)


action = action_name()
if action == "get-kubeconfig":
    get_kubeconfig()
elif action == "apply-manifest":
    apply_manifest()
