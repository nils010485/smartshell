import os
import subprocess
import re
import json
import uuid
import traceback
from datetime import datetime
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.syntax import Syntax
from rich.progress import Progress, BarColumn, TimeElapsedColumn, SpinnerColumn
import yaml
import sys

from client import send_to_openai, openai2doc
from parser import parse_response
from executor import execute_command, generate_script
from utils import get_os_info, check_update
from config import docs_dir, context_dir, history_file, raw_version, token_limit
from pathlib import Path
import wizard

console = Console()

# Sanitize context roles for LLM API (convert non-standard roles like 'bash' to 'user')
def sanitize_context(raw_context):
    sanitized = []
    for m in raw_context:
        role = m.get('role')
        if role not in ('system','user','assistant','tool'):
            role = 'user'
        sanitized.append({'role': role, 'content': m.get('content', '')})
    return sanitized

def get_prompt(bash=False) -> FormattedText:
    user = os.environ.get("USER","user")
    cwd  = os.getcwd()
    style = [
        ("class:username", user),("", "@"),
        ("class:hostname", "smartshell"),("", ":"),
        ("class:cwd", cwd),("", "# ")
    ]
    if bash:
        return FormattedText([("class:type_b","(bash) ")]+style)
    return FormattedText(style)

def bash_int(context) -> tuple[list, bool]:  # returns (details, extracted_flag)
    details = []  # collect command details
    home_dir = os.path.expanduser("~")
    user = os.environ.get('USER', 'user')
    history_file_bash = os.path.join(home_dir, ".history_smartshell_bash")
    style = Style.from_dict({
        "type_b": "bold gray",
        "username": "bold ansibrightred",
        "hostname": "bold ansibrightgreen",
        "cwd": "bold yellow"
    })
    console.print("[bold green]Bienvenue dans le mode bash interactif.[/bold green]")
    console.print("[bold blue]Commandes bash: exit | list | help | extract <start:end|n|n,n>[/bold blue]")
    session = PromptSession(history=FileHistory(history_file_bash), style=style)
    while True:
        user_input = session.prompt(get_prompt(bash=True), style=style).strip()
        # exit, list, help, extract handling
        if user_input.lower() == "exit":
            return details, False
        elif user_input.lower() == "list":
            for i, d in enumerate(details):
                entry = f"$ {d['command']} → exit {d['exit_code']}\n{d['stdout']}" + (f"\nERR: {d['stderr']}" if d['stderr'] else "")
                console.print(Panel(entry, title=f"[bold]({i}) Bash[/bold]", expand=False))
            continue
        elif user_input.lower() == "help":
            help = """[bold blue]exit[/bold blue] : Quitter le bash interactif sans extractions.
[bold blue]extract[/bold blue] <plages> : Extraire dans le contexte et quitter.
[bold blue]list[/bold blue] : Afficher les sorties précédentes.
[bold blue]ctrl + c[/bold blue] : Quitter le bash interactif sans extractions."""
            console.print(Panel(help, title="Commandes bash", expand=False))
            continue
        elif user_input.startswith("extract"):
            # parse slices and append to context
            slice_str = user_input[len("extract"):].strip()
            if not slice_str or any(c not in "0123456789,: " for c in slice_str):
                console.print("[bold yellow]Usage: extract <start:end|num|num,num>[/bold yellow]")
                continue
            try:
                parts = slice_str.split()
                idxs = []
                for part in parts:
                    if ":" in part:
                        s,e = part.split(":")
                        start = int(s) if s else 0
                        end = int(e) if e else len(details)
                        if start >= end: raise ValueError
                        idxs.extend(range(start, end))
                    elif "," in part:
                        idxs.extend(int(x) for x in part.split(","))
                    else:
                        idxs.append(int(part))
                idxs = sorted(set(idxs))
                if any(i >= len(details) for i in idxs): raise ValueError
            except:
                console.print("[bold red]Mauvaise plage d'indices pour extract.[/bold red]")
                continue
            for i in idxs:
                d = details[i]
                entry = f"$ {d['command']}\n→ exit {d['exit_code']}\n{d['stdout']}" + (f"\nERR: {d['stderr']}" if d['stderr'] else "")
                context.append({"role": "bash", "content": entry})
            return details, True
        elif len(user_input) == 0:
            continue
        elif user_input.startswith("cd"):
            try:
                target = user_input[3:].strip() or home_dir
                os.chdir(target)
                code, out, err = 0, "", ""
            except Exception as e:
                code, out, err = 1, "", str(e)
            details.append({"command": user_input, "stdout": out, "stderr": err, "exit_code": code})
            continue
        try:
            result = subprocess.run(user_input, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            out = result.stdout.strip(); err = result.stderr.strip()
            if out: console.print(Panel(out, title="Sortie", expand=False))
            if err: console.print(Panel(err, title="Erreur", style="bold red", expand=False))
            details.append({"command": user_input, "stdout": out, "stderr": err, "exit_code": result.returncode})
        except Exception as e:
            console.print(Panel(str(e), title="Erreur interne", style="bold red", expand=False))
    return details, False

def process_user_input(user_input, model, context):
    # Check context fullness and summarize if above 80% of limit
    if token_limit and token_limit != 0:
        total_t = estimate_tokens(context, model)
        if total_t >= token_limit * 0.8:
            console.print("[bold blue]SmartShell résume votre conversation...[/bold blue]")
            # prompt for summary
            summary_prompt = (
                "Please provide a concise but detailed summary of the following conversation, "
                "preserving important details. Output only the summary text.\nConversation:\n" +
                "\n".join(f"{m['role']}: {m['content']}" for m in context)
            )
            summary = send_to_openai(model, summary_prompt, [])
            context.clear()
            context.append({'role':'system','content':summary})
            total_t = estimate_tokens(context, model)
    if len(user_input) == 0:
        return
    # Aliases for faster commands
    if user_input.startswith("ag "):
        user_input = "agentique" + user_input[2:]
    elif user_input == "ag":
        user_input = "agentique"
    elif user_input.startswith("i "):
        user_input = "int" + user_input[1:]
    elif user_input == "i":
        user_input = "int"
    if user_input == "update":
        try:
            check_update()
        except Exception as e:
            console.print(f"[bold red]Erreur lors de la vérification des mises à jour : {e}[/bold red]")
    elif user_input.startswith("save"):
        if len(context) == 0:
            console.print("[bold yellow]Veuillez exécuter au moins une commande avant de sauvegarder le contexte.[/bold yellow]")
            return
        context_path = os.path.join(context_dir, f"saved_context_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        try:
            with open(context_path, 'w') as f:
                f.write('\n'.join([json.dumps(message) for message in context]))
            console.print(f"[bold green]Contexte sauvegardé dans : {context_path}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Erreur lors de la sauvegarde du contexte : {e}[/bold red]")
    elif user_input.startswith("load"):
        context_file = user_input[5:]
        if len(context_file) == 0:
            console.print("[bold yellow]Veuillez spécifier un fichier de contexte à charger.[/bold yellow]")
            return
        context_file = os.path.join(context_dir, context_file)
        if not os.path.exists(context_file):
            console.print("[bold red]Fichier de contexte introuvable.[/bold red]")
            return
        try:
            l = len(context)
            with open(context_file, 'r') as f:
                data = f.read().splitlines()
                with Progress(
                        "[progress.description]{task.description}",
                        BarColumn(),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        TimeElapsedColumn(),
                        SpinnerColumn("dots"),
                ) as progress:
                    task = progress.add_task("[bold green]Chargement du contexte...[/bold green]", total=len(data))
                    for elm in data:
                        elm = json.loads(elm)
                        if elm.get("role") not in ["user", "assistant"] or not elm.get("content"):
                            console.print("[bold red]Fichier de contexte invalide.[/bold red]")
                            return
                        context.append({"role": elm["role"], "content": elm["content"]})
                        progress.update(task, advance=1)
                    progress.stop_task(task)
                console.print(f"[bold green]✅ {len(context) - l} messages ajoutés au contexte.[/bold green]")
            console.print(f"[bold green]Contexte chargé depuis : {context_file}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Erreur lors du chargement du contexte : {e}[/bold red]")
    elif user_input.startswith("doc"):
        if len(context) == 0:
            console.print("[bold yellow]Veuillez exécuter au moins une commande avant de générer une documentation.[/bold yellow]")
            return
        text = "SmartShell est entrain de penser"
        with console.status(status="[bold green]" + text + "[bold green]", spinner="dots", spinner_style="bold blue"):
            try:
                doc = openai2doc(model, context)
            except Exception as e:
                console.print(f"[bold red]Erreur lors de la génération de la documentation : {e}[/bold red]")
                return
        console.print(Panel(doc, title="Documentation", expand=False))
        save_doc = console.input("[bold yellow]Voulez-vous enregistrer cette documentation ? (y/n)[/bold yellow] ")
        if save_doc.lower() == "y":
            doc_path = os.path.join(docs_dir, f"generated_doc_{uuid.uuid4().hex}.md")
            with open(doc_path, 'w') as f:
                f.write(doc)
            console.print(f"[bold green]Documentation enregistrée dans : {doc_path}[/bold green]")
        # ajouter la documentation au contexte
        context.append({"role": "user", "content": user_input})
        context.append({"role": "assistant", "content": doc})
        return
    elif user_input == "clear":
        console.clear()
        return
    elif user_input == "context clear":
        context = []
        console.print("[bold green]Contexte effacé.[/bold green]")
        return
    elif user_input.startswith("clear") or user_input.startswith("context clear"):
        console.print("[bold yellow]Pour effacer l’écran, tapez 'clear'. Pour effacer le contexte, tapez 'context clear'.[/bold yellow]")
        return
    elif user_input.startswith("ask"):
        # compression avant un nouvel ask
        if token_limit and estimate_tokens(context, model) >= token_limit * 0.8:
            console.print("[bold blue]SmartShell résume votre conversation...[/bold blue]")
            summary = send_to_openai(model, "Resume la conversation précédente en détails mais concis.", [])
            context.clear()
            context.append({'role':'system','content':summary})
        prompt = user_input[4:]
        if len(prompt) == 0:
            console.print("[bold yellow]Veuillez entrer un prompt.[/bold yellow]")
            return
        response = send_to_openai(model, prompt, sanitize_context(context))
        parsed_response = parse_response(response)
        if parsed_response:
            if "explanation" in parsed_response:
                console.print(Panel(parsed_response["explanation"], title="Explications", expand=False))
            if "commands" in parsed_response:
                commands = parsed_response["commands"]
                console.print(Panel(f"[bold green]{'; '.join(commands)}[/bold green]", title="Commandes", expand=False))
                confirm = console.input(f"[bold yellow]Voulez-vous exécuter les commandes ci-dessus ? (y/n)[/bold yellow] ")
                if confirm.lower() == "y":
                    for command in commands:
                        result = execute_command(command)
                        console.print(Panel(result, title=f"Sortie de: {command.split()[0]}", expand=False))
                    context.append({"role": "user", "content": prompt})
                    context.append({"role": "assistant", "content": response})
                else:
                    context.append({"role": "user", "content": prompt})
                    context.append({"role": "assistant", "content": response})
            if "generate_script" in parsed_response:
                script_content = parsed_response.get("script", "")
                console.print(Panel(
                    Syntax(
                        script_content.strip(),
                        "bash", theme="monokai", line_numbers=True
                    ),
                    title="Generated Script", expand=False
                ))
                save = console.input("[bold yellow]Voulez-vous enregistrer ce script ? (y/n)[/bold yellow] ")
                if save.lower() == "y":
                    path = generate_script(script_content)
                    if path:
                        console.print(f"[bold green]Script enregistré dans : {path}[/bold green]")
                    else:
                        console.print("[bold red]Erreur lors de l'enregistrement du script.[/bold red]")
            else:
                context.append({"role": "user", "content": prompt})
                context.append({"role": "assistant", "content": response})
        else:
            console.print("[bold red]Erreur: Je ne suis pas bien sûr de ce que vous essayez de faire.[/bold red]")
    elif user_input.startswith("script"):
        # Forcer la génération de script si l'utilisateur tape 'script'
        prompt = user_input[6:].strip()
        if not prompt:
            console.print("[bold yellow]Veuillez entrer un prompt pour le script.[/bold yellow]")
            return
        # S'assurer que 'script' est mentionné pour l'IA
        script_prompt = prompt if "script" in prompt.lower() else f"{prompt} --script"
        context.append({"role":"user","content":script_prompt})
        response = send_to_openai(model, script_prompt, sanitize_context(context))
        parsed = parse_response(response)
        if parsed and "script" in parsed:
            panels = []
            script_content = parsed["script"]
            panels.append(Panel(Syntax(script_content.strip(), "bash", theme="monokai", line_numbers=True), title="Script", expand=False))
            console.print(Columns(panels))
            save = console.input("[bold yellow]Voulez-vous enregistrer ce script ? (y/n)[/bold yellow] ")
            if save.lower() == "y":
                path = generate_script(script_content)
                if path:
                    console.print(f"[bold green]Script enregistré dans : {path}[/bold green]")
                else:
                    console.print("[bold red]Erreur lors de l'enregistrement du script.[/bold red]")
        else:
            console.print("[bold yellow]Aucun script généré par l'IA.[/bold yellow]")
        # Ajouter au contexte et passer
        context.append({"role":"assistant","content":response})
        return
    elif user_input.startswith("§ update"):
        console.print("[bold yellow] Vous devez exécuter cette commande dans votre terminal, et non ici.[/bold yellow]")
        return
    elif user_input.startswith("int"):
        prompt = user_input[4:]
        if len(prompt) == 0:
            console.print("[bold yellow]Veuillez entrer un prompt.[/bold yellow]")
            return
        context.append({"role": "user", "content": prompt})
        while True:
            response = send_to_openai(model, prompt, sanitize_context(context))
            parsed_response = parse_response(response)
            if parsed_response:
                if "explanation" in parsed_response:
                    console.print(Panel(parsed_response["explanation"], title="Explications", expand=False))
                if "generate_script" in parsed_response:
                    script_content = parsed_response.get("script", "")
                    console.print(Panel(
                        Syntax(
                            script_content.strip(),
                            "bash", theme="monokai", line_numbers=True
                        ),
                        title="Generated Script", expand=False
                    ))
                    save = console.input("[bold yellow]Voulez-vous enregistrer ce script ? (y/n)[/bold yellow] ")
                    if save.lower() == "y":
                        path = generate_script(script_content)
                        if path:
                            console.print(f"[bold green]Script enregistré dans : {path}[/bold green]")
                        else:
                            console.print("[bold red]Erreur lors de l'enregistrement du script.[/bold red]")
                if "commands" in parsed_response:
                    commands = parsed_response["commands"]
                    console.print(Panel(f"[bold green]{'; '.join(commands)}[/bold green]", title="Commandes", expand=False))
                    confirm = console.input(f"[bold yellow]Voulez-vous exécuter les commandes ci-dessus ? (y/n)[/bold yellow] ")
                    if confirm.lower() == "y":
                        result = None
                        for command in commands:
                            result = execute_command(command)
                            if len(result) > 0:
                                console.print(Panel(result, title=f"Sortie de: {command.split()[0]}", expand=False))
                        if result:
                            send_output = console.input("[bold yellow]Voulez-vous envoyer la sortie de la commande au LLM ? (y/n)[/bold yellow] ")
                            if send_output.lower() == "y":
                                comment = console.input("[bold yellow]Ajoutez un commentaire (ou appuyez sur Entrée pour laisser vide) :[/bold yellow] ")
                                resultat_cmd = result.strip()
                                if comment:
                                    user_content = comment + " " + resultat_cmd
                                else:
                                    user_content = resultat_cmd
                                context.append({"role": "assistant", "content": response})
                                context.append({"role": "user", "content": user_content})
                            else:
                                context.append({"role": "assistant", "content": response})
                                break
                        else:
                            context.append({"role": "assistant", "content": response})
                            break
                    else:
                        context.append({"role": "assistant", "content": response})
                        return
                else:
                    context.append({"role": "assistant", "content": response})
                    break
            else:
                console.print("[bold red]Erreur: Je ne suis pas sûr de ce que vous essayez de faire.[/bold red]")
                context.pop()
                return
        return
    elif user_input.startswith("conf"):
        cfg_path = Path(__file__).parent / 'smartshell.yaml'
        if not cfg_path.exists():
            console.print(Panel("Configuration absente, lancement du wizard...", title="Conf", style="bold yellow"))
            wizard.main()
        else:
            data = yaml.safe_load(cfg_path.read_text())
            # Affichage structuré de la config
            from rich.table import Table
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Clé", style="cyan")
            table.add_column("Valeur", style="white")
            # API Settings
            for k, v in data.get('api', {}).items():
                table.add_row(f"api.{k}", str(v))
            # Paths
            for k, v in data.get('paths', {}).items():
                table.add_row(f"paths.{k}", str(v))
            # Other
            table.add_row("updater.url", data.get('updater', {}).get('url', ''))
            table.add_row("raw_version", str(data.get('raw_version', '')))
            table.add_row("token_limit", str(data.get('token_limit', '')))
            console.print(Panel(table, title="Configuration actuelle", expand=False))
            ans = console.input("[bold yellow]Modifier la config ? (y/n)[/bold yellow] ")
            if ans.lower() == 'y':
                wizard.main()
        return
    elif user_input.startswith("bash"):
        try:
            details, extracted = bash_int(context)
        except (KeyboardInterrupt, EOFError):
            console.print("[bold green]Fin du bash sans sauvegarder la sortie[/bold green]")
            return
        # after bash, offer to extract to context
        if details and not extracted:
            ans = console.input("[bold yellow]Extraire les commandes bash exécutées dans le contexte ? (y/n)[/bold yellow] ")
            if ans.lower() == 'y':
                for d in details:
                    # format entry
                    entry = (
                        f"$ {d['command']}\n"
                        f"→ exit {d['exit_code']}\n"
                        f"{d['stdout']}" + (f"\nERR: {d['stderr']}" if d['stderr'] else "")
                    )
                    context.append({"role": "bash", "content": entry})
        return
    elif user_input.startswith("agentique"):
        objective = user_input[len("agentique"):].strip()
        if not objective:
            console.print("[bold yellow]Veuillez entrer un objectif pour agentique.[/bold yellow]")
            return
        # Launch agent mode with existing context to persist messages
        import smartshell
        smartshell.agentique_mode(model, objective, context)
        return
    elif user_input.startswith("context stats"):
        # show context stats
        total_chars = sum(len(m.get('content','')) for m in context)
        total_msgs = len(context)
        total_t = estimate_tokens(context, model)
        from rich.table import Table
        table = Table(title="Contexte actuel")
        table.add_column("Messages", justify="right")
        table.add_column("Caractères", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Limite", justify="right")
        lim = str(token_limit) if token_limit else "∞"
        table.add_row(str(total_msgs), str(total_chars), str(total_t), lim)
        console.print(table)
        return
    elif user_input.startswith("context remove"):
        # supprimer un message du contexte par son ID
        parts = user_input.split()
        if len(parts) != 3 or not parts[2].isdigit():
            console.print("[bold yellow]Usage: context remove <id>[/bold yellow]")
            return
        idx = int(parts[2]) - 1
        if idx < 0 or idx >= len(context):
            console.print("[bold red]ID hors du contexte.[/bold red]")
            return
        removed = context.pop(idx)
        console.print(f"[bold green]Message {parts[2]} supprimé:[/bold green] {removed['content']}")
        return
    elif user_input.startswith("context"):
        # affichage détaillé du contexte
        if not context:
            console.print("[bold yellow]Le contexte est vide.[/bold yellow]")
            return
        total_max = len(context)
        for idx, message in enumerate(context, 1):
            console.print(f"[bold yellow]({idx}/{total_max})[/bold yellow]")
            if message["role"] == "user":
                console.print(Panel(message["content"], title="Utilisateur", expand=False, style="bold blue"))
            elif message["role"] == "system":
                # Try to parse JSON content and display panels by key
                parsed_sys = parse_response(message["content"], hide=True)
                if parsed_sys:
                    panels_sys = []
                    if "explanation" in parsed_sys:
                        panels_sys.append(Panel(parsed_sys["explanation"], title="Résumé", expand=False, style="bold green"))
                    if "commands" in parsed_sys:
                        panels_sys.append(Panel("; ".join(parsed_sys["commands"]), title="Commandes", expand=False, style="bold green"))
                    if "script" in parsed_sys:
                        panels_sys.append(Panel(parsed_sys["script"], title="Script", expand=False, style="bold green"))
                    console.print(Columns(panels_sys))
                else:
                    console.print(Panel(message["content"], title="Système", expand=False, style="bold magenta"))
            elif message["role"] == "assistant":
                parsed = parse_response(message["content"], hide=True)
                if not parsed:
                    console.print(Panel("Commande enregistrée.", title="Système", expand=False, style="bold purple"))
                    continue
                panels = []
                if "explanation" in parsed:
                    panels.append(Panel(parsed["explanation"], title="Assistant", expand=False, style="bold green"))
                if "commands" in parsed:
                    panels.append(Panel(f"[bold green]{'; '.join(parsed['commands'])}[/bold green]", title="Commandes", expand=False))
                if "script" in parsed:
                    import re, uuid
                    from rich.syntax import Syntax
                    title = re.search(r"# NAME=(.*?)\n", message["content"])
                    script_title = title.group(1) if title else f"script_{uuid.uuid4().hex}"
                    panels.append(Panel(Syntax(parsed["script"], "bash", theme="monokai", line_numbers=True), title=script_title, expand=False))
                console.print(Columns(panels))
            elif message["role"] == "bash":
                console.print(Panel(message["content"], title="Bash", expand=False, style="bold magenta"))
        return
    elif user_input.startswith("help"):
        help_text = """[bold blue]Commandes générales :[/bold blue]
[bold yellow]help[/bold yellow] : Afficher ce message.
[bold yellow]save[/bold yellow] : Sauvegarder le contexte actuel.
[bold yellow]load <file>[/bold yellow] : Charger un contexte sauvegardé.
[bold yellow]clear[/bold yellow] : Effacer l’écran.
[bold yellow]context clear[/bold yellow] : Effacer le contexte.
[bold yellow]update[/bold yellow] : Vérifier les mises à jour.

[bold blue]Contexte :[/bold blue]
[bold yellow]context[/bold yellow] : Affichage détaillé du contexte.
[bold yellow]context stats[/bold yellow] : Afficher les statistiques du contexte.
[bold yellow]context clear[/bold yellow] : Supprime l'entiéreté du contexte.
[bold yellow]context remove <id>[/bold yellow] : Supprimer le message d’indice <id> du contexte.

[bold blue]Mode bash :[/bold blue]
[bold yellow]bash[/bold yellow] : Entrer/sortir du mode bash interactif.
[bold yellow]extract[/bold yellow] : Extraire des sorties de bash par slices.
[bold yellow]list[/bold yellow] : Afficher les sorties de bash.

[bold blue]Configuration :[/bold blue]
[bold yellow]conf[/bold yellow] : Afficher/éditer la configuration.

[bold blue]Interaction IA :[/bold blue]
[bold yellow]ask <prompt>[/bold yellow] : Envoyer un prompt simple.
[bold yellow]script <prompt>[/bold yellow] : Générer un script.
[bold yellow]int <prompt>[/bold yellow] : Itérer sur un prompt jusqu’à completion.
[bold yellow]agentique <objectif>[/bold yellow] : Mode autonome avec validation.
[bold yellow]doc <description>[/bold yellow] : Générer de la documentation.
"""
        console.print(Panel(help_text, title="Aide", expand=False))
        return
    else:
        console.print(f"[bold red]Commande inconnue: {user_input}[/bold red]")

# Estimate tokens in context using tiktoken or fallback
def estimate_tokens(messages, model=None):
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model or openai_force_model)
        return sum(len(enc.encode(m.get('content',''))) for m in messages)
    except Exception:
        # Fallback: approximate as 1 token per 3 characters
        total_chars = sum(len(m.get('content','')) for m in messages)
        return total_chars // 3

def interactive_shell(model):
    # Vérification de mise à jour au lancement du shell interactif
    try:
        if check_update(mod="quick"):
            console.print("[yellow]Nouvelle version disponible ![/yellow]")
            ans = console.input("[bold yellow]Voulez-vous mettre à jour automatiquement ? (y/n) [/bold yellow]")
            if ans.lower() == 'y':
                console.print("[blue]Mise à jour en cours...[/blue]")
                try:
                    subprocess.run(["pip", "install", "--upgrade", "git+https://github.com/nils010485/smartshell.git"], check=True)
                    console.print("[green]Mise à jour terminée. Redémarrez SmartShell.[/green]")
                    sys.exit(0)
                except Exception:
                    console.print("[red]La mise à jour a échoué. Veuillez mettre à jour manuellement en faisant : git clone https://github.com/nils010485/smartshell.git && pip install .[/red]")
            else:
                console.print("[yellow]Pour mettre à jour manuellement, exécutez : git clone https://github.com/nils010485/smartshell.git && pip install .[/yellow]")
    except Exception as e:
        console.print(f"[red]Erreur vérification update: {e}[/red]")
    context = []
    session = PromptSession(history=FileHistory(history_file))
    style_prompt = Style.from_dict({
        "username": "bold ansibrightred",
        "hostname": "bold ansibrightgreen",
        "cwd": "bold yellow"
    })
    while True:
        try:
            user_input = session.prompt(get_prompt(), style=style_prompt)
            user_input = user_input.strip()
            if user_input.lower() in ["exit", "quit"]:
                console.print("[bold green]Au revoir ![/bold green]")
                break
            if user_input == "context clear":
                context = []
                console.print("[bold green]Contexte effacé.[/bold green]")
                continue
            process_user_input(user_input, model, context)
        except KeyboardInterrupt:
            console.print("[bold green]\nAu revoir ![/bold green]")
            break

def input_parser(user_input, output) -> list:
    if not user_input:
        return []
    ranges = user_input.split()
    selected_indices = []
    for range_str in ranges:
        if ":" in range_str:
            start, end = range_str.split(":")
            if not start:
                start = "0"
            if not end:
                end = str(len(output))
            if not start.isdigit() or not end.isdigit() or int(start) >= int(end):
                raise ValueError(f"Invalid range: {range_str}")
            selected_indices.extend(list(range(int(start), int(end))))
        elif "," in range_str:
            indices = range_str.split(",")
            if not all(index.isdigit() for index in indices):
                raise ValueError(f"Invalid indices: {range_str}")
            selected_indices.extend(int(index) for index in indices)
        else:
            if not range_str.isdigit():
                raise ValueError(f"Invalid index: {range_str}")
            selected_indices.append(int(range_str))
    selected_indices = sorted(set(selected_indices))
    if any(index >= len(output) for index in selected_indices):
        raise ValueError(f"Index out of range: {user_input}")
    return [output[i] for i in selected_indices]
