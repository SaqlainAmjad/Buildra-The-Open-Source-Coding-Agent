"""The ``buildra`` command: wire settings, model, tools and graph, then chat."""

import uuid
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from rich.console import Console

from buildra import __version__
from buildra.agent import AgentContext, build_graph
from buildra.cli.approval import ConsoleApprover
from buildra.cli.render import ConsoleView
from buildra.cli.repl import run_repl
from buildra.cli.turn import TurnRunner
from buildra.config import ConfigError, load_settings
from buildra.llm import LLMConfigError, ModelRef, create_chat_model
from buildra.permissions.sandbox import Workspace
from buildra.tools import default_registry

app = typer.Typer(
    add_completion=False, help="Buildra: an open-source coding agent for your terminal."
)


@app.command()
def main(
    prompt: Annotated[
        str | None, typer.Argument(help="Run a single request and exit instead of chatting.")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", "-m", help='Model id, e.g. "deepseek/deepseek-v4-pro".')
    ] = None,
    workdir: Annotated[
        Path,
        typer.Option("--workdir", "-C", help="Project directory (default: current directory)."),
    ] = Path(),
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    """Start Buildra in the project directory."""
    console = Console()
    if version:
        console.print(f"buildra {__version__}")
        return

    root = workdir.resolve()
    load_dotenv(root / ".env")  # never overrides variables already set
    try:
        settings = load_settings(root)
        model_id = str(ModelRef.parse(model or settings.llm.model))
        llm = create_chat_model(settings.llm, model=model_id)
    except (ConfigError, LLMConfigError) as error:
        console.print(f"[bold red]Error:[/] {error}")
        raise typer.Exit(code=1) from error

    context = AgentContext(
        settings=settings,
        llm=llm,
        model_id=model_id,
        tools=default_registry(),
        workspace=Workspace(root),
    )
    view = ConsoleView(console)
    runner = TurnRunner(
        graph=build_graph(InMemorySaver()),
        context=context,
        view=view,
        approver=ConsoleApprover(console),
        thread_id=uuid.uuid4().hex,
    )
    console.print(f"[bold]buildra[/] {__version__}  [dim]{model_id} in {root}[/]")
    if prompt:
        runner.run(prompt)
        return
    run_repl(runner, view)
