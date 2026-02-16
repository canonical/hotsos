"""
CLI helper for smartctl commands.

This module provides classes to execute smartctl commands on both live systems
and sosreport data.
"""
from collections import UserList

from hotsos.core.host_helpers.cli.common import BinCmd, FileCmd


class SmartctlAllCommands(UserList):
    """
    Generate smartctl -a command variants for a specific device.
    This class creates command variants that work on both live systems
    (using BinCmd) and with sosreport data (using FileCmd).
    Args:
        device: Device name (e.g., 'sda', 'sdb', 'nvme0n1')
    """

    def __init__(self, device):
        """
        Initialize smartctl command variants for the given device.

        Args:
            device: Device name without /dev/ prefix (e.g., 'sda', 'sdb')
        """
        self.device = device

        cmds = []

        cmds.append(BinCmd(f'smartctl -a /dev/{device}'))
        # In sosreports, smartctl output is stored by the ata or nvme sos
        # plugin under sos_commands/ata/ and sos_commands/nvme/ respectively.
        cmds.append(FileCmd(f'sos_commands/ata/smartctl_-a_{device}'))
        cmds.append(FileCmd(f'sos_commands/nvme/smartctl_-a_{device}'))

        super().__init__(cmds)
