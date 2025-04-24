import argparse
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import subprocess

from config import openai_api_key, openai_base_url, openai_force_model, raw_version, updater_url, token_limit
from utils import check_dir, check_update
from client import send_to_openai, openai2doc
from parser import parse_response
from executor import execute_command, generate_script
from shell import interactive_shell, estimate_tokens

console = Console()

def sanitize_context(raw_context):
    sanitized = []
    for m in raw_context:
        role = m.get('role')
        if role not in ('system','user','assistant','tool'):
            role = 'user'
        sanitized.append({'role': role, 'content': m.get('content', '')})
    return sanitized

# Agentique mode: autonomous planning and execution with user validation
def agentique_mode(model, objective, context=None):
    # Compression du contexte si seuil de tokens atteint (80%)
    if token_limit and context and estimate_tokens(context, model) >= token_limit * 0.8:
        console.print("[bold blue]SmartShell résume votre conversation...[/bold blue]")
        summary = send_to_openai(model, "Resume la conversation précédente en détails mais concis.", [])
        # conserver l'historique complet et ajouter le résumé comme message système
        context.append({'role':'system','content': summary})
    # Gestion du contexte existant
    if context:
        ans = console.input(f"[bold yellow]Le contexte contient {len(context)} messages. L'agentique doit-il y avoir accès ? (y/n) [/bold yellow]")
        if ans.lower() != 'y':
            context.clear()
    # Affichage de l'objectif
    console.print(Panel(objective, title="Mode Agentique Activé", style="bold green", expand=False))
    # Construction du prompt initial pour le plan
    prompt_plan = f"Objectif : {objective}. Planifie les étapes pour atteindre cet objectif. N'ouvre pas de terminal, tu es déjà dans une ! Répond uniquement en JSON avec clé 'plan': [étapes]."
    # Envoi du prompt pour génération du plan
    api_ctx = sanitize_context(context or [])
    response = send_to_openai(model, prompt_plan, api_ctx)
    # Initialisation du contexte avec le prompt et la réponse
    if context is None:
        context = []
    context.append({"role": "user", "content": prompt_plan})
    context.append({"role": "assistant", "content": response})
    out = parse_response(response)
    if not out or 'plan' not in out:
        console.print(Panel("Réponse LLM invalide (absence de 'plan').", style="bold red", expand=False))
        console.print(response)
        return
    plan = out['plan']
    # Affichage du plan
    table = Table(title="Plan d'action", box=box.SQUARE)
    table.add_column("N°", style="bold green")
    table.add_column("Étape", style="cyan")
    for i, s in enumerate(plan, start=1): table.add_row(str(i), s)
    console.print(table)
    # Exécution et adaptation
    auto = False
    while True:
        for idx, step in enumerate(plan, start=1):
            console.print(Panel(step, title=f"Étape {idx}/{len(plan)}", style="bold yellow", expand=False))
            choice = console.input("[bold yellow]Valider ? (y/n/a)[/bold yellow] ") if not auto else 'y'
            if choice.lower() == 'n':
                comment = console.input("[bold yellow]Commentaire (optionnel) :[/bold yellow] ")
                fb = f"Étape refusée: {step}." + (f" Commentaire: {comment}" if comment else "")
                context.append({"role":"user","content":fb})
                resp2 = send_to_openai(model, f"{fb} Révise le plan en JSON avec 'plan'.", sanitize_context(context))
                context.append({"role":"assistant","content":resp2})
                out2 = parse_response(resp2)
                if out2 and 'plan' in out2:
                    plan = out2['plan']
                    console.print(Panel("Plan révisé.", style="bold green", expand=False))
                    for i2, s2 in enumerate(plan, start=1): console.print(f"  {i2}. {s2}")
                    break
                console.print(Panel("Impossible de réviser le plan.", style="bold red", expand=False))
                return
            # Feedback libre: tout autre input que y/n/a
            if choice.lower() not in ('y','n','a'):
                fb = f"Feedback utilisateur: {choice}"
                context.append({"role":"user","content":fb})
                resp2 = send_to_openai(model, f"{fb} Révise le plan en JSON avec 'plan'.", sanitize_context(context))
                context.append({"role":"assistant","content":resp2})
                out2 = parse_response(resp2)
                if out2 and 'plan' in out2:
                    plan = out2['plan']
                    console.print(Panel("Plan révisé suite à feedback.", style="bold green", expand=False))
                    for i2, s2 in enumerate(plan, start=1): console.print(f"  {i2}. {s2}")
                    break
                console.print(Panel("Impossible de réviser le plan.", style="bold red", expand=False))
                return
            if choice.lower() == 'a': auto = True
            # Génération des commandes
            resp3 = send_to_openai(model, f"Pour l'étape: {step}, répond en JSON avec clé 'commands': [cmds].", sanitize_context(context))
            context.append({"role":"assistant","content":resp3})
            out3 = parse_response(resp3)
            cmds = out3.get('commands', []) if out3 else []
            last = ""
            for c in cmds:
                console.print(Panel(c, title="Commande", expand=False))
                res = execute_command(c)
                console.print(Panel(res, title="Résultat", expand=False))
                context.extend([{"role":"user","content":c},{"role":"assistant","content":res}])
                last = res
            # Décision suivante (replan / continue / complete)
            # Tronquer le contexte uniquement si on dépasse le seuil de tokens (80%) pour garder un historique gérable
            if token_limit and estimate_tokens(context, model) >= token_limit * 0.8:
                if len(context) > 20:
                    context = context[-20:]
            resp4 = send_to_openai(
                model,
                f"Résultats: {last}. Répond uniquement en JSON avec clé 'action': 'replan' ou 'continue' ou 'complete'. Si 'replan', ajoute 'plan' avec liste d'étapes.",
                sanitize_context(context)
            )
            context.append({"role":"assistant","content":resp4})
            out4 = parse_response(resp4)
            if out4 and out4.get('action') == 'replan' and 'plan' in out4:
                plan = out4['plan']
                console.print(Panel("Plan ajusté.", style="bold green", expand=False))
                break
            elif out4 and out4.get('action') == 'complete':
                console.print(Panel("Objectif atteint, fin du mode agentique.", style="bold green", expand=False))
                return
            # sinon continue boucle
        else:
            console.print(Panel("Mode agentique terminé.", style="bold green", expand=False))
            return

def main():
    parser = argparse.ArgumentParser(description="SmartShell")
    # Commande optionnelle : si absent, on lance le shell interactif par défaut
    parser.add_argument("command", choices=["ask", "shell", "agentique"], nargs="?", default="shell", help="ask, shell, ou agentique (par défaut 'shell')")
    parser.add_argument("prompt", nargs="?", help="Texte pour ask ou agentique")
    parser.add_argument("-m", "--model", default=openai_force_model, help="Modèle OpenAI à utiliser")
    args = parser.parse_args()

    if args.command == "ask":
        if not args.prompt:
            parser.error("ask requiert un prompt")
        response = send_to_openai(args.model, args.prompt)
        out = parse_response(response)
        if not out:
            console.print("[red]Erreur: réponse non comprise.[/red]")
            sys.exit(1)
        if "explanation" in out:
            console.print(Panel(out["explanation"], title="Explications"))
        if "commands" in out:
            console.print(Panel("; ".join(out["commands"]), title="Commandes"))
    elif args.command == "agentique":
        if not args.prompt:
            parser.error("agentique requiert un prompt")
        agentique_mode(args.model, args.prompt)
    else:
        console.print("""[yellow]
  _________                      __   _________.__           .__  .__   
 /   _____/ _____ _____ ________/  |_/   _____/|  |__   ____ |  | |  |  
 \_____  \ /     \\__  \\_  __ \   __\_____  \ |  |  \_/ __ \|  | |  |  
 /        \  Y Y  \/ __ \|  | \/|  | /        \|   Y  \  ___/|  |_|  |__
/_______  /__|_|  (____  /__|   |__|/_______  /|___|  /\___  >____/____/
        \/      \/     \/                   \/      \/     \/           
                                                        
                                                        """)
        console.print("[green]Bienvenue dans SmartShell ! | https://smartshell.fieryaura.eu/")
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
        interactive_shell(args.model)

if __name__ == "__main__":
    try:
        check_dir()
        main()
    except (KeyboardInterrupt, EOFError):
        console.print("[green]Au revoir ![/green]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Erreur inattendue: {e}[/red]")
        if console.input("[yellow]Générer rapport ? (y/n)[/yellow] ") == "y":
            import traceback, json
            with open("error_report", "w") as f:
                f.write(traceback.format_exc())
            console.print("[red]Rapport généré dans error_report[/red]")
        sys.exit(1)
