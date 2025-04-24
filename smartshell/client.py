import os
from openai import OpenAI
from rich.console import Console
from contextlib import nullcontext
from .config import openai_api_key, openai_base_url, openai_force_model, token_limit
from .utils import get_os_info

console = Console()
if not openai_api_key:
    console.print("[red]Clé API OpenAI manquante dans config.yaml[/red]")
    exit(1)

client = OpenAI(api_key=openai_api_key, base_url=openai_base_url) if openai_base_url else OpenAI(api_key=openai_api_key)

def send_to_openai(model, prompt, context=None, use_spinner=True) -> str:
    status_ctx = console.status("[bold green]SmartShell pense…[/bold green]", spinner="dots", spinner_style="green") if use_spinner else nullcontext()
    with status_ctx:
        os_info = get_os_info()
        user = os.environ.get("USER","user")
        sys_prompt = f"""
You are an intelligent Bash wizard on {os_info['name']} {os_info['version']}.
User: {user}.
Respond in French if the prompt is in French.
Output only a JSON object with keys: explanation (string), commands (array of strings), script (string, optional).
If the user prompt explicitly requests a script (by mentioning 'script') or if the task cannot be accomplished by commands only, include the 'script' key containing a complete bash script fulfilling the request.
"""
        # Construction simple des messages
        msgs = []
        if context:
            msgs.extend(context)
        # ajouter toujours le prompt comme dernier message user
        msgs.append({"role":"user","content":prompt})

        r = client.chat.completions.create(
            model=openai_force_model if model is None else model,
            messages=[{"role":"system","content":sys_prompt}]+msgs,
            max_tokens=(token_limit if token_limit else 4000),
            temperature=0.0,
            response_format={'type': 'json_object'}
        )
    return r.choices[0].message.content

def openai2doc(model, messages) -> str:
    messages.append({"role":"user","content":"Create me a documentation"})
    sys_prompt = "Based on messages, génère une doc Markdown (sans conclusion)."
    r = client.chat.completions.create(
        model=openai_force_model if model is None else model,
        messages=[{"role":"system","content":sys_prompt}]+messages,
        max_tokens=4000, temperature=0.0
    )
    res = r.choices[0].message.content
    messages.pop()
    return res
