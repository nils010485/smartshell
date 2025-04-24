# 🚀 SmartShell - Le Terminal Augmenté par l'IA

**Un assistant terminal intelligent pour automatiser les tâches d'administration système**  
*Développé par [Nils](https://nils.begou.dev) - Licence MIT*

<img src="https://cdn.angelkarlsson.eu/persist/img/smartshell/demo.png">

<div align="center">
  <a href="https://smartshell.fieryaura.eu">Site Officiel</a> | 
  <a href="https://github.com/nils010485/smartshell">GitHub</a>
</div>

---

## ✨ Qu'est-ce que SmartShell?

SmartShell transforme votre terminal en partenaire intelligent qui:
- 💬 Comprend vos questions en langage naturel
- 🛠️ Propose et exécute les commandes bash optimales
- 📜 Génère des scripts personnalisés pour vos besoins
- 🤖 Résout des problèmes complexes en mode autonome
- 📚 Crée de la documentation en Markdown à la volée

## 📋 Fonctionnalités principales

### Mode Interactif
```bash
smartshell
```
- Interface colorée et intuitive
- Historique persistant des commandes
- Contexte conversationnel intelligent

### Commandes rapides
```bash
# Poser une question directe
smartshell ask "Comment trouver les fichiers les plus volumineux?"

# Générer un script spécifique
smartshell script "Créer une sauvegarde des fichiers modifiés cette semaine"

# Lancer le mode agentique pour résoudre un problème complexe
smartshell agentique "Optimiser les performances du serveur"
```

### Mode Bash avancé
```bash
# Shell interactif
smartshell
# Puis on active le mode bash
bash
$ find / -type f -size +100M -exec ls -lh {} \;
$ exit
# Extraire les commandes dans le contexte
extract 0
```

## ⚙️ Installation

```bash
# Cloner le dépôt
git clone https://github.com/nils010485/smartshell.git

# Installer l'application
cd smartshell
pip install .

# Lancer l'assistant de configuration (automatique au premier démarrage)
smartshell
```

## 🔧 Configuration

Le fichier `smartshell.yaml` permet de personnaliser:

```yaml
api:
  openai_api_key: "votre-clé-api"
  openai_base_url: null  # Entrez ici l'URL de l'api
  openai_force_model: "le-nom-du-modele"  # Modèle à utiliser

paths:
  scripts_dir: "~/.sshell/scripts"  # Emplacement des scripts générés
  docs_dir: "~/.sshell/docs"        # Documentation générée
  
token_limit: 0  # Limite de tokens (0 = aucune limite)
```

## 💡 Commandes utiles

| Commande | Description |
|----------|-------------|
| `help` | Affiche l'aide des commandes |
| `ask` | Interroge l'IA sur un sujet |
| `script` | Génère un script bash |
| `int` | Mode interactif avec l'IA |
| `agentique` | Mode autonome pour résolution de problèmes |
| `doc` | Génère de la documentation |
| `bash` | Mode bash interactif |
| `context` | Gère le contexte conversationnel |
| `save/load` | Sauvegarde/charge le contexte |
| `update` | Vérifie les mises à jour |

## 🌟 Compatibilité

Attention, les modèles doivent supporter les sorties structurés !

- **APIs supportées**: OpenAI officielle ou toute API compatible (OpenAI-compatible)
- **Modèles locaux**: Compatible avec LMStudio, Ollama, Deepseek, etc. 
- **OS testés**: Fedora

## 📁 Architecture du projet

Le code est organisé en modules spécialisés:
- `executor.py`: Exécution sécurisée des commandes et scripts
- `parser.py`: Traitement des réponses JSON
- `client.py`: Communication avec l'API IA
- `shell.py`: Gestion de l'interface interactive
- `smartshell.py`: Point d'entrée principal et coordinateur
- `utils.py`: Fonctions utilitaires
- `config.py`: Gestion de la configuration
- `wizard.py`: Assistant de configuration initiale

## 🤝 Contribution

Les contributions sont bienvenues! N'hésitez pas à:
- Signaler des bugs (Issues)
- Proposer des améliorations
- Soumettre des pull requests

---

*SmartShell: Votre terminal, boosté par l'IA* 🚀
