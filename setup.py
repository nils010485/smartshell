import yaml
from setuptools import setup
import os

# requirements from requirements.txt
with open("requirements.txt") as f:
    install_requires = [r.strip() for r in f if r.strip()]

# version from smartshell.yaml
# choose config or sample if missing
config_file = "smartshell.yaml" if os.path.exists("smartshell.yaml") else "smartshell.yaml.example"
with open(config_file) as f:
    cfg = yaml.safe_load(f)
version = cfg.get("raw_version", "0.0.1")

setup(
    name="smartshell",
    version=version,
    description="SmartShell : le shell augmenté par l’IA",
    author="Nils",
    author_email="nils@begou.dev",
    url="https://smartshell.fieryaura.eu/",
    py_modules=[
        "client",
        "config",
        "executor",
        "parser",
        "shell",
        "smartshell",
        "utils",
        "wizard"
    ],
    install_requires=install_requires,
    include_package_data=True,
    data_files=[("", ["smartshell.yaml.example"])],
    entry_points={
        "console_scripts": [
            "smartshell=smartshell:main"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License"
    ]
)
