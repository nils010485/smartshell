#!/usr/bin/env python3
"""
SmartShell Configuration Wizard
"""
import yaml
import os
from pathlib import Path


def main():
    config_path = Path(__file__).parent / "smartshell.yaml"
    example_path = Path(__file__).parent / "smartshell.yaml.example"
    if config_path.exists():
        cfg_example = yaml.safe_load(config_path.read_text())
    elif example_path.exists():
        cfg_example = yaml.safe_load(example_path.read_text())
    else:
        # Fallback to internal default template
        print("⚠️  smartshell.yaml.example introuvable, utilisation du template interne.")
        cfg_example = {
            "api": {
                "openai_api_key": "YOUR_OPENAI_API_KEY",
                "openai_base_url": None,
                "openai_force_model": "chatgpt-4o-latest",
            },
            "paths": {
                "scripts_dir": "~/.sshell/scripts",
                "docs_dir": "~/.sshell/docs",
                "context_dir": "~/.sshell/context",
                "history_file": "~/.smart_shell_history",
            },
            "updater": {"url": "https://api.angelkarlsson.eu/smartshellv2/updater"},
            "token_limit": 0,
        }
    config = {}
    print("✨ Bienvenue dans le wizard de configuration SmartShell ✨\n")

    # API
    print("Attention, le modèle choisi doit supporter le structured output, sinon le programme ne fonctionnera pas !")
    api = {}
    api_key = input(f"Clé API (OpenAI Like) [{cfg_example['api'].get('openai_api_key')}]: ") or cfg_example['api'].get('openai_api_key')
    api['openai_api_key'] = api_key
    base_url = input(f"Base URL OpenAI [{cfg_example['api'].get('openai_base_url')}]: ") or cfg_example['api'].get('openai_base_url')
    api['openai_base_url'] = base_url
    model = input(f"Modèle forcé OpenAI [{cfg_example['api'].get('openai_force_model')}]: ") or cfg_example['api'].get('openai_force_model')
    api['openai_force_model'] = model
    config['api'] = api

    # Paths
    paths = {}
    for key, default in cfg_example.get('paths', {}).items():
        val = default
        #val = input(f"{key} [{default}]: ") or default
        paths[key] = val
        # créer le dossier si c'est un répertoire
        if not key.endswith('file'):
            Path(os.path.expanduser(val)).mkdir(parents=True, exist_ok=True)
    config['paths'] = paths

    # Limite de tokens
    token_default = cfg_example.get('token_limit', 0)
    token_input = input(f"Limite de tokens (>=1024 ou 0 pour sans limite) [{token_default}]: ") or token_default
    try:
        token_limit = int(token_input)
    except ValueError:
        token_limit = token_default
    if token_limit != 0 and token_limit < 1024:
        print(f"token_limit doit être 0 ou >=1024. Utilisation de la valeur par défaut {token_default}.")
        token_limit = token_default

    # Sections non configurables: updater est pris du template
    # Fusionner la configuration example et user
    out_cfg = cfg_example
    out_cfg['api'] = config['api']
    out_cfg['paths'] = config['paths']
    out_cfg['token_limit'] = token_limit
    out_path = Path(__file__).parent / 'smartshell.yaml'
    with open(out_path, 'w') as f:
        yaml.safe_dump(out_cfg, f, default_flow_style=False, sort_keys=False)

    print(f"\n✅ Configuration enregistrée dans: {out_path}")

if __name__ == '__main__':
    main()
