"""
CoWorkX Daemon — Machine Info Collector
Detects real hardware specs of the current machine.
Called once at startup to fill in the registration payload.
"""

import os
import platform
import random
import shutil
import socket

import psutil


def get_machine_specs() -> dict:
    """
    Returns a dict ready to POST to /machines/register.
    All values are detected from the real hardware.
    """
    return {
        "display_name":       get_display_name(),
        "os":                 get_os_type(),
        "cpu_model":          get_cpu_model(),
        "cpu_cores":          get_cpu_cores(),
        "ram_gb":             get_ram_gb(),
        "gpu_model":          get_gpu_model(),
        "gpu_vram_gb":        get_gpu_vram(),
        "storage_gb":         get_storage_gb(),
        "installed_software": detect_software(),
        "supported_tasks":    ["browsing", "coding", "file", "research"],
        "price_per_hour":     1.0,
        "latitude":           get_latitude(),
        "longitude":          get_longitude(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL DETECTORS
# ─────────────────────────────────────────────────────────────────────────────

def get_display_name() -> str:
    """Hostname + OS as the machine's display name"""
    hostname = socket.gethostname()
    os_short = get_os_type().capitalize()
    return f"{hostname} ({os_short})"


def get_os_type() -> str:
    """Returns 'windows', 'macos', or 'linux'"""
    s = platform.system()
    if s == "Windows": return "windows"
    if s == "Darwin":  return "macos"
    return "linux"


def get_cpu_model() -> str:
    """Read the actual CPU model string"""
    system = platform.system()

    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            )
            model = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            winreg.CloseKey(key)
            return model
        except Exception:
            return platform.processor() or "Unknown CPU"

    elif system == "Darwin":
        import subprocess
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                timeout=3
            )
            return out.decode().strip()
        except Exception:
            return platform.processor() or "Apple CPU"

    else:  # Linux
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.processor() or "Unknown CPU"


def get_cpu_cores() -> int:
    """Physical cores (not hyperthreaded)"""
    cores = psutil.cpu_count(logical=False)
    return cores if cores else psutil.cpu_count(logical=True) or 1


def get_ram_gb() -> int:
    """Total RAM rounded to nearest GB"""
    return round(psutil.virtual_memory().total / (1024 ** 3))


def get_storage_gb() -> int:
    """Free + used space on main drive"""
    try:
        path = "C:\\" if platform.system() == "Windows" else "/"
        return round(psutil.disk_usage(path).total / (1024 ** 3))
    except Exception:
        return 0


def get_gpu_model() -> str | None:
    """Try to detect GPU model (Windows: wmic, Linux: lspci)"""
    system = platform.system()

    if system == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name", "/format:value"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if line.startswith("Name=") and line.strip() != "Name=":
                    name = line.split("=", 1)[1].strip()
                    if name:
                        return name
        except Exception:
            pass

    elif system == "Linux":
        try:
            import subprocess
            result = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    # e.g. "01:00.0 VGA compatible controller: NVIDIA GeForce RTX 3080"
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        return parts[2].strip()
        except Exception:
            pass

    elif system == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "Chipset Model" in line:
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass

    return None


def get_gpu_vram() -> int | None:
    """Try to get GPU VRAM in GB — Windows only for now"""
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "AdapterRAM", "/format:value"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if line.startswith("AdapterRAM="):
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit():
                        vram = round(int(val) / (1024 ** 3))
                        return vram if vram > 0 else None
        except Exception:
            pass
    return None


def detect_software() -> list[str]:
    """
    Check which common developer tools are installed.
    Uses shutil.which() to check PATH, plus Windows-specific paths.
    """
    found = []
    system = platform.system()

    # Tools that can be found via PATH (cross-platform)
    path_checks = {
        "Python":  "python",
        "Node.js": "node",
        "Docker":  "docker",
        "Git":     "git",
        "Go":      "go",
        "Rust":    "cargo",
    }
    for name, cmd in path_checks.items():
        if shutil.which(cmd):
            found.append(name)

    # Windows-specific app paths
    if system == "Windows":
        win_paths = [
            (r"C:\Program Files\Google\Chrome\Application\chrome.exe",     "Chrome"),
            (r"C:\Program Files\Mozilla Firefox\firefox.exe",               "Firefox"),
            (r"C:\Program Files\Microsoft VS Code\Code.exe",                "VS Code"),
            (r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe","Blender"),
        ]
        for path, name in win_paths:
            if os.path.exists(path) and name not in found:
                found.append(name)

    # macOS-specific
    elif system == "Darwin":
        mac_paths = [
            ("/Applications/Google Chrome.app",  "Chrome"),
            ("/Applications/Firefox.app",         "Firefox"),
            ("/Applications/Visual Studio Code.app", "VS Code"),
            ("/Applications/Xcode.app",            "Xcode"),
            ("/Applications/Final Cut Pro.app",    "Final Cut Pro"),
            ("/Applications/Figma.app",            "Figma"),
        ]
        for path, name in mac_paths:
            if os.path.exists(path) and name not in found:
                found.append(name)

    # Linux-specific
    else:
        linux_cmds = {
            "Chrome":  "google-chrome",
            "Firefox": "firefox",
        }
        for name, cmd in linux_cmds.items():
            if shutil.which(cmd) and name not in found:
                found.append(name)

    return found


def get_latitude() -> float:
    """
    For demo: return a coordinate near Hyderabad with a small random offset.
    In production: call an IP geolocation API.
    """
    return round(17.4065 + random.uniform(-0.08, 0.08), 6)


def get_longitude() -> float:
    return round(78.4772 + random.uniform(-0.08, 0.08), 6)