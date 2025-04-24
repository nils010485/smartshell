import os
import sys
import requests
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from config import updater_url, raw_version, scripts_dir, docs_dir, context_dir

console = Console()

def check_dir():
    """Crée les dossiers nécessaires."""
    for d in (scripts_dir, docs_dir, context_dir):
        os.makedirs(d, exist_ok=True)

def get_os_info() -> dict:
    info = {}
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("NAME="):
                info["name"] = line.split("=",1)[1].strip().strip('"')
            elif line.startswith("VERSION="):
                info["version"] = line.split("=",1)[1].strip().strip('"')
    return info

def debug_info() -> dict:
    import openai as oo
    return {
        "python_version": sys.version,
        "os": os.uname(),
        "distro": "\n".join(f"{k}: {v}" for k,v in get_os_info().items()),
        "openai_version": oo.__version__,
        "smartshell_version": raw_version,
    }

def check_update(mod="full"):
    resp = requests.get(updater_url)
    data = resp.json()
    if mod == "quick":
        return int(data["raw"]) > raw_version

    panels = []
    if raw_version > int(data["raw"]):
        panels.append(Panel("Build interne", title="⚠️ Avertissement", style="red"))
    elif int(data["raw"]) > raw_version:
        panels.append(Panel(data["version"], title="✅ Nouvelle version", style="green"))
    else:
        panels.append(Panel(data["version"], title="📦 À jour", style="green"))

    panels.append(Panel(data["changelog"], title="Changelog", style="blue"))
    console.print(Columns(panels))
