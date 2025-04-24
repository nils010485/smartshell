import json, traceback
from rich.console import Console

console = Console()

def parse_response(response, hide=False) -> dict or None:
    try:
        return json.loads(response)
    except Exception as e:
        if not hide:
            console.print(f"[red]Erreur de parsing JSON LLM: {e}[/red]")
            console.print(response)
        return None
