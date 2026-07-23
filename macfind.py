#!/usr/bin/env python3
"""macfind: find and track named devices on your LAN by MAC (survives DHCP IP changes)."""
import argparse
import ipaddress
import json
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
STATE_PATH = Path(__file__).parent / "last_seen.json"
FALLBACK_SUBNET = "192.168.20.0/24"
IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def ping(ip: str, timeout_ms: int) -> bool:
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""


def arp_table() -> dict:
    """IP -> MAC, read from the OS ARP cache (populated by the ping sweep)."""
    out = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count(".") == 3:
            ip, mac = parts[0], parts[1]
            if mac.count("-") == 5 or mac.count(":") == 5:
                table[ip] = mac.lower().replace("-", ":")
    return table


def local_subnets() -> list:
    """Subnets of this PC's currently-connected network adapters, via ipconfig."""
    # ponytail: Windows-only (ipconfig parsing); add `ip -4 addr` parsing if run on Linux
    if not IS_WINDOWS:
        return []
    out = subprocess.run(["ipconfig"], capture_output=True, text=True).stdout
    subnets, ip = [], None
    for line in out.splitlines():
        if "IPv4 Address" in line:
            m = IPV4_RE.search(line)
            ip = m.group() if m else None
        elif "Subnet Mask" in line and ip:
            m = IPV4_RE.search(line)
            if m:
                net = ipaddress.ip_network(f"{ip}/{m.group()}", strict=False)
                if not net.is_loopback and not net.is_link_local:
                    subnets.append(str(net))
            ip = None
    return subnets


def resolve_subnets(subnet_arg) -> list:
    if subnet_arg:
        return [s.strip() for s in subnet_arg.split(",") if s.strip()]
    return local_subnets() or [FALLBACK_SUBNET]


def touch_last_seen(known: dict, arp: dict, alive: set) -> dict:
    """Record 'now' for every known device found alive; return the full state."""
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    now = datetime.now().isoformat(timespec="seconds")
    for ip in alive:
        mac = arp.get(ip)
        if mac in known:
            state[mac] = now
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
    return state


def format_last_seen(ts: str) -> str:
    if not ts:
        return "never"
    seconds = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def sweep(args):
    known = {}
    known_path = Path(args.known)
    if known_path.exists():
        known = json.loads(known_path.read_text())

    subnets = resolve_subnets(args.subnet)
    hosts = {str(ip) for s in subnets for ip in ipaddress.ip_network(s, strict=False).hosts()}
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = {pool.submit(ping, ip, args.timeout): ip for ip in hosts}
        alive = {futures[f] for f in as_completed(futures) if f.result()}

    return alive, arp_table(), known, known_path, subnets


def cmd_scan(args):
    alive, arp, known, known_path, subnets = sweep(args)
    print(f"Scanned {', '.join(subnets)}")
    ordered = sorted(alive, key=lambda ip: tuple(int(p) for p in ip.split(".")))

    print(f"\n{'IP':<16}{'MAC':<20}{'Name':<20}{'Hostname'}")
    for ip in ordered:
        mac = arp.get(ip, "")
        name = known.get(ip) or known.get(mac) or ""
        print(f"{ip:<16}{mac:<20}{name:<20}{hostname(ip)}")

    unknown = [ip for ip in ordered if ip not in known and arp.get(ip, "") not in known]
    if unknown:
        print(f"\n{len(unknown)} live host(s) not in {known_path.name}: {', '.join(unknown)}")

    touch_last_seen(known, arp, alive)


def cmd_ls(args):
    alive, arp, known, _, subnets = sweep(args)
    print(f"Scanned {', '.join(subnets)}")
    ip_by_mac = {mac: ip for ip, mac in arp.items() if ip in alive}
    state = touch_last_seen(known, arp, alive)

    print(f"\n{'Name':<20}{'IP':<16}{'MAC':<20}{'Status':<10}{'Last seen'}")
    for mac, name in known.items():
        ip = ip_by_mac.get(mac, "")
        last_seen = "now" if ip else format_last_seen(state.get(mac))
        print(f"{name:<20}{ip:<16}{mac:<20}{'online' if ip else 'offline':<10}{last_seen}")


def cmd_rename(args):
    known_path = Path(args.known)
    known = json.loads(known_path.read_text()) if known_path.exists() else {}

    matches = [mac for mac, name in known.items() if name == args.oldname]
    if not matches:
        print(f"No device named '{args.oldname}' in {known_path.name}. "
              f"Known: {', '.join(known.values())}")
        return

    known[matches[0]] = args.newname
    known_path.write_text(json.dumps(known, indent=2) + "\n")
    print(f"Renamed '{args.oldname}' -> '{args.newname}'")


def cmd_rm(args):
    known_path = Path(args.known)
    known = json.loads(known_path.read_text()) if known_path.exists() else {}

    matches = [mac for mac, name in known.items() if name == args.name]
    if not matches:
        print(f"No device named '{args.name}' in {known_path.name}. "
              f"Known: {', '.join(known.values())}")
        return

    del known[matches[0]]
    known_path.write_text(json.dumps(known, indent=2) + "\n")
    print(f"Removed '{args.name}'")


def cmd_add(args):
    known_path = Path(args.known)
    known = json.loads(known_path.read_text()) if known_path.exists() else {}

    if not ping(args.ip, args.timeout):
        print(f"{args.ip} did not respond to ping; can't resolve its MAC address right now.")
        return

    mac = arp_table().get(args.ip)
    if not mac:
        print(f"Pinged {args.ip} but couldn't find its MAC in the ARP cache. Try again.")
        return

    known[mac] = args.name
    known_path.write_text(json.dumps(known, indent=2) + "\n")
    print(f"Added '{args.name}' -> {mac} (resolved from {args.ip})")


def print_help():
    print("""macfind: find and track named devices on your LAN by MAC (survives DHCP IP changes)

  mf                          show saved devices, current IP, online/offline
  mf scan (s)                 sweep the whole subnet, show every live device
  mf add (a) <name> <ip>      save a device, MAC resolved from its current IP
  mf rename (rn) <old> <new>  rename a saved device
  mf rm (remove) <name>       remove a saved device
  mf ip <ip/subnet>           like "mf", but scan a different subnet just once
  mf help (h)                 show this help

flags (any command): --subnet, --known, --timeout, --threads""")


def main():
    known_default = str(Path(__file__).parent / "devices.json")

    known_only = argparse.ArgumentParser(add_help=False)
    known_only.add_argument("--known", default=known_default, help="path to MAC->name mapping json")

    perf = argparse.ArgumentParser(add_help=False, parents=[known_only])
    perf.add_argument("--timeout", type=int, default=300, help="ping timeout in ms")
    perf.add_argument("--threads", type=int, default=64)

    common = argparse.ArgumentParser(add_help=False, parents=[perf])
    common.add_argument(
        "--subnet", default=None,
        help="comma-separated ip/subnet list; auto-detects this PC's connected "
             f"subnets if omitted, falling back to {FALLBACK_SUBNET}"
    )

    parser = argparse.ArgumentParser(prog="mf", description=__doc__, parents=[common])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ls", parents=[common],
                    help="(default) show saved devices with current IP + online/offline")
    sub.add_parser("scan", aliases=["s"], parents=[common],
                    help="sweep the whole subnet, show every live device")
    rename_p = sub.add_parser("rename", aliases=["rn"], parents=[known_only],
                               help="rename a saved device")
    rename_p.add_argument("oldname")
    rename_p.add_argument("newname")
    rm_p = sub.add_parser("rm", aliases=["remove"], parents=[known_only],
                           help="remove a saved device")
    rm_p.add_argument("name")
    add_p = sub.add_parser("add", aliases=["a"], parents=[common],
                            help="save a device by name, resolving its MAC from its current IP")
    add_p.add_argument("name")
    add_p.add_argument("ip")
    ip_p = sub.add_parser("ip", parents=[perf],
                           help="ls, but scan a different ip/subnet just for this run")
    ip_p.add_argument("subnet", metavar="ip/subnet", help="e.g. 192.168.30.0/24")
    sub.add_parser("help", aliases=["h"], help="show this help")

    args = parser.parse_args()

    if args.command in ("help", "h"):
        print_help()
        return

    if args.command in ("scan", "s"):
        cmd_scan(args)
    elif args.command in ("rename", "rn"):
        cmd_rename(args)
    elif args.command in ("rm", "remove"):
        cmd_rm(args)
    elif args.command in ("add", "a"):
        cmd_add(args)
    else:
        cmd_ls(args)


if __name__ == "__main__":
    main()
