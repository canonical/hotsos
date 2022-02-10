from __future__ import print_function, unicode_literals
import subprocess, re, argparse, os, time, shutil
from string import Formatter

INTERFACES_FILE="/etc/network/interfaces"
IP_LINE = re.compile(r"^\d+: (.*?):")
IP_HWADDR = re.compile(r".*link/ether ((\w{2}|:){11})")
COMMAND = "ip -oneline link"
RETRIES = 3
WAIT = 5

# Python3 vs Python2
try:
    strdecode = str.decode
except AttributeError:
    strdecode = str

def ip_parse(ip_output):
    """parses the output of the ip command
    and returns a hwaddr->nic-name dict"""
    devices = dict()
    print("Parsing ip command output %s" % ip_output)
    for ip_line in ip_output:
        ip_line_str = strdecode(ip_line, "utf-8")
        match = IP_LINE.match(ip_line_str)
        if match is None:
            continue
        nic_name = match.group(1).split('@')[0]
        match = IP_HWADDR.match(ip_line_str)
        if match is None:
            continue
        nic_hwaddr = match.group(1)
        devices[nic_hwaddr] = nic_name
    print("Found the following devices: %s" % str(devices))
    return devices

def replace_ethernets(interfaces_file, output_file, devices, fail_on_missing):
    """check if the contents of interfaces_file contain template
    keys corresponding to hwaddresses and replace them with
    the proper device name"""
    with open(interfaces_file + ".templ", "r") as templ_file:
        interfaces = templ_file.read()

    formatter = Formatter()
    hwaddrs = [v[1] for v in formatter.parse(interfaces) if v[1]]
    print("Found the following hwaddrs: %s" % str(hwaddrs))
    device_replacements = dict()
    for hwaddr in hwaddrs:
        hwaddr_clean = hwaddr[3:].replace("_", ":")
        if devices.get(hwaddr_clean, None):
            device_replacements[hwaddr] = devices[hwaddr_clean]
        else:
            if fail_on_missing:
                print("Can't find device with MAC %s, will retry" % hwaddr_clean)
                return False
            else:
                print("WARNING: Can't find device with MAC %s when expected" % hwaddr_clean)
                device_replacements[hwaddr] = hwaddr
    formatted = interfaces.format(**device_replacements)
    print("Used the values in: %s\nto fix the interfaces file:\n%s\ninto\n%s" %
           (str(device_replacements), str(interfaces), str(formatted)))

    with open(output_file, "w") as intf_out_file:
        intf_out_file.write(formatted)

    if not os.path.exists(interfaces_file + ".bak"):
        try:
            shutil.copyfile(interfaces_file, interfaces_file + ".bak")
        except OSError: #silently ignore if the file is missing
            pass
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interfaces-file", dest="intf_file", default=INTERFACES_FILE)
    parser.add_argument("--output-file", dest="out_file", default=INTERFACES_FILE+".out")
    parser.add_argument("--command", default=COMMAND)
    parser.add_argument("--retries", default=RETRIES)
    parser.add_argument("--wait", default=WAIT)
    args = parser.parse_args()
    retries = int(args.retries)
    for tries in range(retries):
        ip_output = ip_parse(subprocess.check_output(args.command.split()).splitlines())
        if replace_ethernets(args.intf_file, args.out_file, ip_output, (tries != retries - 1)):
             break
        else:
             time.sleep(float(args.wait))

if __name__ == "__main__":
    main()

