import os
import yaml
from pathlib import Path


import os
import yaml
from pathlib import Path

class Config:
    def __init__(self, path=None):
        if path is None:
            path = Path(__file__).parent / "smartshell.yaml"
        self.path = Path(os.path.expanduser(str(path)))
        if not self.path.exists():
            # Config manquante : lancer automatiquement le wizard
            print("⚠️  Fichier de configuration introuvable, lancement du wizard...")
            try:
                import wizard
                wizard.main()
            except Exception as e:
                raise FileNotFoundError(f"Échec du wizard de configuration: {e}")
            if not self.path.exists():
                raise FileNotFoundError(f"Config file not found after wizard: {self.path}")
        with open(self.path, "r") as f:
            cfg = yaml.safe_load(f)
        self.api = cfg.get("api", {})
        self.paths = cfg.get("paths", {})
        self.updater = cfg.get("updater", {})
        self.raw_version = 16
        self.token_limit = cfg.get("token_limit", 0)
        if self.token_limit != 0 and self.token_limit < 1024:
            raise ValueError(f"token_limit must be 0 (no limit) or >=1024, got {self.token_limit}")
        # Expand user in paths
        for key, val in self.paths.items():
            if isinstance(val, str):
                self.paths[key] = os.path.expanduser(val)

config = Config()
# API settings
openai_api_key = config.api.get("openai_api_key")
openai_base_url = config.api.get("openai_base_url")
openai_force_model = config.api.get("openai_force_model")
# Paths
scripts_dir = config.paths.get("scripts_dir")
docs_dir = config.paths.get("docs_dir")
context_dir = config.paths.get("context_dir")
history_file = config.paths.get("history_file")
# Updater
updater_url = config.updater.get("url")
# Version
raw_version = config.raw_version
# Limite de tokens
token_limit = config.token_limit
