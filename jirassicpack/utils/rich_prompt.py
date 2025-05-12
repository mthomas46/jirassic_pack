from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.theme import Theme
from rich import box

console = Console()

# Jurassic Park–themed color palette
JURASSIC_THEME = Theme({
    "info": "bold yellow3",
    "warning": "bold magenta",
    "error": "bold red",
    "success": "bold green3",
    "prompt": "bold cyan",
    "banner": "bold green_yellow",
    "dino": "bold green_yellow",
    "danger": "bold red",
    "raptor": "bold magenta",
    "butts": "bold orange3",
    "mirror": "bold blue",
    "clever": "bold magenta",
    "congrats": "bold green3",
    "nobody": "bold grey50",
})

console = Console(theme=JURASSIC_THEME)

JURASSIC_ICON = "🦖"


def rich_info(message):
    console.print(f"{JURASSIC_ICON} [info]{message}[/info]")

def rich_warning(message):
    console.print(f"{JURASSIC_ICON} [warning]{message}[/warning]")

def rich_error(message, suggestion=None):
    """
    Print a Jurassic Park–themed error message with optional suggestion/example.
    """
    error_text = f"🦖 {message}"
    if suggestion:
        error_text += f"\n[bold yellow]Hint:[/] {suggestion}"
    console.print(Panel(Text(error_text, style="bold red"), title="[bold red]Error![/]", border_style="red"))

def rich_success(message):
    console.print(f"{JURASSIC_ICON} [success]{message}[/success]")

def rich_prompt_text(message, default=None):
    prompt_msg = f"{JURASSIC_ICON} [prompt]{message}[/prompt]"
    return Prompt.ask(prompt_msg, default=default)

def rich_prompt_confirm(message, default=False):
    prompt_msg = f"{JURASSIC_ICON} [prompt]{message}[/prompt]"
    return Confirm.ask(prompt_msg, default=default)

def rich_panel(message, title=None, style="banner"):
    console.print(Panel(message, title=title, style=style, box=box.ROUNDED))

# Jurassic Park–themed panels and Easter eggs

def panel_life_finds_a_way():
    # Only show on first launch/onboarding
    rich_panel(
        "“Life finds a way.”\n\n– Dr. Ian Malcolm",
        title="🦖 Welcome to Jirassic Pack",
        style="banner"
    )

def panel_spared_no_expense():
    # Use for major success only
    rich_panel(
        "🦖 Spared no expense! Your operation was a success.",
        title="Success!",
        style="success"
    )

def panel_objects_in_mirror():
    # Only show for long result lists
    rich_panel(
        "Objects in mirror are closer than they appear.",
        title=None,
        style="mirror"
    )

def panel_clever_girl():
    # Use for clever/fuzzy search results
    rich_panel(
        "Clever girl... You found what you were looking for!",
        title=None,
        style="clever"
    )

def panel_hold_onto_your_butts():
    # Use for long-running operations
    rich_panel(
        "Hold onto your butts... This might take a moment.",
        title=None,
        style="butts"
    )

def panel_big_pile_of_errors():
    rich_panel(
        "💩 That is one big pile of errors.",
        title="🦖 Uh-oh!",
        style="poop"
    )

def panel_jurassic_ascii():
    # Only show on first launch
    JURASSIC_ASCII = r'''
      __
     / _)_ 
.-^^^-/ /  
__/       /   
<__.|_|-|_|   🦖
'''
    rich_panel(
        f"{JURASSIC_ASCII}\nWelcome to Jurassic Park!",
        title="🦖",
        style="dino"
    )

def panel_nobody_cares():
    # Only show on abort/exit
    rich_panel(
        "🦖 See, nobody cares.",
        title=None,
        style="nobody"
    )

def panel_crazy_son_of_a():
    # Use for rare/major achievement
    rich_panel(
        "You did it. You crazy son of a... you did it!",
        title=None,
        style="congrats"
    )

def panel_welcome_dr(user):
    # Only show on first login
    rich_panel(
        f"Welcome, Dr. {user}!",
        title="🦖",
        style="banner"
    )

def panel_combined_welcome(user):
    JIRASSIC_ASCII = r'''
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||           JIRASSIC PACK       __ ||           JIRASSIC PACK       __ ||
||           / _)               / _)||           / _)               / _)||
||    .-^^^-/ /----------.-^^^-/ /  ||    .-^^^-/ /----------.-^^^-/ /  ||
|| __/       /        __/       /   || __/       /        __/       /   ||
||<__.|_|-|_|       <__.|_|-|_|     ||<__.|_|-|_|       <__.|_|-|_|     ||
||      |  |   ________   |  |      ||      |  |   ________   |  |      ||
||      |  |  |  __  __|  |  |      ||      |  |  |  __  __|  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
'''
    message = f"""Welcome to Jurassic Park!

“Life finds a way.”
– Dr. Ian Malcolm

Welcome, Dr. {user}!"""
    rich_panel(message, title=JIRASSIC_ASCII, style="banner") 