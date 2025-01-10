# flake8: noqa
# pylint: disable=C0301

# Including this as a dep of (at least) Neutron
# sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p' ovsdbapp/exceptions.py
OVSDBAPP_EXCEPTIONS = [
    "OvsdbAppException",
    "TimeoutException",
    "OvsdbConnectionUnavailable",
]
