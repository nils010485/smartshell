import subprocess, os, uuid, re
from config import scripts_dir
from rich.console import Console

console = Console()

def execute_command(command) -> str:
    # Exécute sans exception pour toujours récupérer returncode
    try:
        r = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        # Construire un message incluant le code de retour
        msg = f"Code: {r.returncode}\n{r.stdout}"
        if r.stderr:
            msg += f"\n{r.stderr}"
        return msg
    except Exception as e:
        # En cas d'erreur imprévue
        return f"[red]Erreur interne cmd `{command}`: {e}[/red]"

def generate_script(content) -> str or None:
    m = re.search(r"# NAME=(.*?)\n", content)
    if m:
        name = m.group(1)
        content = content.replace(m.group(0), "")
    else:
        name = f"script_{uuid.uuid4().hex}.sh"
    path = os.path.join(scripts_dir, name)
    try:
        with open(path, 'w') as f:
            f.write(content)
        os.chmod(path, 0o755)
        return path
    except Exception as e:
        console.print(f"[red]Erreur écriture script: {e}[/red]")
        return None
