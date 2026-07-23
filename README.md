# macfind

Find and track named devices on your local network by MAC address — survives
DHCP reassigning their IP.

If you manage devices on a LAN where IPs move around (DHCP renewals, devices
roaming between access points, etc.), keeping track of "which IP is which
device" gets old fast. macfind pings your subnet, reads the OS ARP cache to
map IP → MAC, and matches that against a small local list of MAC → name you
maintain. The name always follows the device, even after its IP changes.

## Install

**Windows**, PowerShell:

```powershell
irm https://raw.githubusercontent.com/Nantaphat-Yoktaworn/macfind/main/install.ps1 | iex
```

Requires Python to already be on PATH. The installer checks for it and tells
you where to get it if it's missing. Downloads to `%LOCALAPPDATA%\macfind`
and adds that folder to your user PATH — close and reopen PowerShell
afterward for the `mf` command to be recognized.

**Linux**, any shell:

```sh
curl -fsSL https://raw.githubusercontent.com/Nantaphat-Yoktaworn/macfind/main/install.sh | bash
```

Requires `python3` on PATH. Installs to `~/.local/bin`; if that's not already
on your PATH the installer tells you the line to add to `~/.bashrc`/`~/.zshrc`.

## Usage

```
mf                          show saved devices, current IP, online/offline
mf scan (s)                 sweep the whole subnet, show every live device
mf add (a) <name> <ip>      save a device, MAC resolved from its current IP
mf rename (rn) <old> <new>  rename a saved device
mf rm (remove) <name>       remove a saved device
mf ip <ip/subnet>           like "mf", but scan a different subnet just once
mf help (h)                 show this help
```

Flags available on any command: `--subnet`, `--known`, `--timeout`, `--threads`.

By default macfind auto-detects every subnet your PC's network adapters are
currently connected to (`ipconfig` on Windows, `ip addr` on Linux) and sweeps
all of them — no config needed even if you're on multiple networks at once
(e.g. two adapters, or a VPN). `--subnet` overrides this, and accepts a
comma-separated list.

## How it works

1. Ping every host in the target subnet(s) concurrently.
2. Read the OS ARP cache (populated by the pings) to get each live IP's MAC address.
3. Look up each MAC in your saved list (`devices.json`) to attach a name.
4. Record when each saved device was last seen online, so `mf` can show
   "last seen 2h ago" for devices that are currently offline.

Devices are identified by MAC, not IP, because MAC addresses don't change
when DHCP hands out a new IP — so your saved names keep working indefinitely.

## Config

`devices.json` lives next to the script and maps MAC addresses to names:

```json
{
  "aa:bb:cc:dd:ee:ff": "example-device"
}
```

You normally don't hand-edit this — `mf add`/`rename`/`rm` manage it for you.
`last_seen.json`, in the same folder, is internal state; no need to touch it.

## Platform

Windows and Linux. On Linux, MAC lookups use `ip neighbor` (falling back to
`arp -a`) and subnet detection uses `ip addr` — both parts of `iproute2`,
present by default on virtually all modern distros. macOS isn't supported
yet (different `ifconfig`-based subnet detection would be needed), though
`arp -a` parsing happens to already work there.
