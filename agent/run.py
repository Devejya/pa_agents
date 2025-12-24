#!/usr/bin/env python3
"""
Gmail Agent CLI Runner

Interactive command-line interface for the Gmail agent.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# Load environment variables
load_dotenv()

console = Console()


def verify_setup():
    """Verify all required configuration is in place."""
    errors = []
    
    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY not set. Add it to .env file or environment.")
    
    # Check credentials file
    creds_path = Path(__file__).parent / "../SECRETS/google_oath_credentials.json"
    if not creds_path.exists():
        errors.append(f"Google credentials not found at {creds_path}")
    
    return errors


def print_welcome():
    """Print welcome message."""
    console.print(Panel.fit(
        "[bold blue]📧 Gmail Agent[/bold blue]\n\n"
        "Your AI-powered email assistant.\n\n"
        "[dim]Commands:[/dim]\n"
        "  • Type your request naturally\n"
        "  • 'quit' or 'exit' to leave\n"
        "  • 'clear' to reset conversation\n"
        "  • 'help' for examples",
        title="Welcome",
        border_style="blue",
    ))


def print_help():
    """Print help message."""
    console.print(Panel(
        "[bold]Example Commands:[/bold]\n\n"
        "📬 [cyan]Show me my unread emails[/cyan]\n"
        "📋 [cyan]Summarize my emails from today[/cyan]\n"
        "🔴 [cyan]What are my priority emails?[/cyan]\n"
        "✏️  [cyan]Draft a reply to email ID xxx saying I'll review it tomorrow[/cyan]\n"
        "🔍 [cyan]Find emails from my boss in the last week[/cyan]\n"
        "📖 [cyan]Show me the full content of email ID xxx[/cyan]",
        title="Help",
        border_style="green",
    ))


def main():
    """Main CLI loop."""
    # Verify setup
    errors = verify_setup()
    if errors:
        console.print("[bold red]Setup Error:[/bold red]")
        for err in errors:
            console.print(f"  ❌ {err}")
        console.print("\n[dim]Please fix the above issues and try again.[/dim]")
        sys.exit(1)
    
    # Import after verification (needs credentials)
    from src.auth import verify_connection
    from src.gmail_agent import GmailAssistant
    from src.tools.learn_style import auto_refresh_styles_if_needed, should_refresh_styles
    
    print_welcome()
    
    # Verify Gmail connection
    console.print("\n[dim]Connecting to Gmail...[/dim]")
    status = verify_connection()
    
    if status["status"] == "error":
        console.print(f"[red]Gmail connection failed: {status['error']}[/red]")
        console.print("[dim]This may open a browser for OAuth authentication.[/dim]")
    else:
        console.print(f"[green]✓ Connected to {status['email']}[/green]")
        console.print(f"[dim]  Total messages: {status['messages_total']}[/dim]")
    
    # Auto-refresh style profile if needed
    if should_refresh_styles():
        console.print("[dim]  Refreshing style profile...[/dim]")
        refresh_result = auto_refresh_styles_if_needed(silent=False)
        if refresh_result and refresh_result.get("status") == "success":
            console.print(f"[green]  ✓ Style profile updated[/green]")
        elif refresh_result and refresh_result.get("status") == "warning":
            console.print(f"[yellow]  ⚠ {refresh_result.get('message', 'Style profile needs more emails')}[/yellow]")
    else:
        console.print("[dim]  Style profile: up to date[/dim]")
    
    console.print()  # Empty line
    
    # Initialize assistant
    assistant = GmailAssistant()
    
    # Main loop
    while True:
        try:
            user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit", "q"]:
                console.print("[dim]Goodbye! 👋[/dim]")
                break
            
            if user_input.lower() == "clear":
                assistant.clear_history()
                console.print("[dim]Conversation cleared.[/dim]")
                continue
            
            if user_input.lower() == "help":
                print_help()
                continue
            
            # Process request
            console.print("[dim]Thinking...[/dim]")
            
            with console.status("[bold green]Processing..."):
                response = assistant.chat(user_input)
            
            console.print(f"\n[bold green]Assistant:[/bold green]\n{response}")
            
        except KeyboardInterrupt:
            console.print("\n[dim]Use 'quit' to exit.[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()

