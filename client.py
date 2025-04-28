import os
from openai import OpenAI
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.spinner import Spinner
from rich import box
from rich.columns import Columns
import re
from contextlib import nullcontext
from config import openai_api_key, openai_base_url, openai_force_model, token_limit, config
from utils import get_os_info

console = Console()
if not openai_api_key:
    console.print("[red]Clé API OpenAI manquante dans smartshell.yaml[/red]")
    exit(1)

client = OpenAI(api_key=openai_api_key, base_url=openai_base_url) if openai_base_url else OpenAI(api_key=openai_api_key)

def send_to_openai(model, prompt, context=None, use_spinner=True) -> str:
    # Préparer prompt et messages
    os_info = get_os_info()
    user = os.environ.get("USER", "user")
    sys_prompt = f"""
You are an intelligent Bash wizard on {os_info['name']} {os_info['version']}.
User: {user}.
Answer in the language of the user's request.
Output only a JSON object with keys: explanation (string), commands (array of strings), script (string, optional).
If the user prompt explicitly requests a script (by mentioning 'script') or if the task cannot be accomplished by commands only, include the 'script' key containing a complete bash script fulfilling the request.
"""
    msgs = []
    if context:
        msgs.extend(context)
    msgs.append({"role": "user", "content": prompt})
    system_messages = [{"role": "system", "content": sys_prompt}]
    for instr in config.instructions:
        system_messages.append({"role": "system", "content": f"User special instruction: {instr}"})
    all_messages = system_messages + msgs
    if use_spinner:
        # Stream with spinner and live preview
        content = ""
        display_content = ""
        stream = client.chat.completions.create(
            model=openai_force_model if model is None else model,
            messages=all_messages,
            max_tokens=(token_limit or 4000),
            temperature=0.0,
            response_format={'type': 'json_object'},
            stream=True
        )
        spinner = Spinner("dots", text="[bold green]SmartShell pense…[/bold green]", style="green")
        snippet_renderable = Text("", style="green")
        with Live(Group(spinner, snippet_renderable), refresh_per_second=10, transient=True, console=console) as live:
            for chunk in stream:
                delta = getattr(chunk.choices[0].delta, "content", "") or ""
                if delta:
                    content += delta
                    # Remove JSON keys for display
                    disp = re.sub(r'\"[a-zA-Z_]+\":', '', delta)
                    disp = disp.replace('{','').replace('}','').replace('"','')
                    display_content += disp
                    snippet_text = display_content if len(display_content) <= 300 else display_content[-300:]
                    renderable = Group(spinner, Text(snippet_text, style="purple"))
                    live.update(renderable)
        return content
    # Mode bloquant sans animation
    r = client.chat.completions.create(
        model=openai_force_model if model is None else model,
        messages=all_messages,
        max_tokens=(token_limit or 4000),
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
