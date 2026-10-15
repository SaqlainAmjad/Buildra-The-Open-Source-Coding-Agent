"""The interactive chat loop."""

from pathlib import Path

import platformdirs
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from buildra.cli.render import ConsoleView
from buildra.cli.turn import TurnRunner

EXIT_WORDS = frozenset({"exit", "quit", "/exit", "/quit"})


def run_repl(runner: TurnRunner, view: ConsoleView) -> None:
    """Read prompts until the user exits. Ctrl+C cancels a running turn, Ctrl+D quits."""
    session: PromptSession[str] = PromptSession(history=FileHistory(str(_history_file())))
    view.info("Type a request. 'exit' or Ctrl+D quits; Ctrl+C cancels a running turn.")
    while True:
        try:
            text = session.prompt("> ").strip()
        except KeyboardInterrupt:
            continue  # clear the current input line
        except EOFError:
            return
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            return
        try:
            runner.run(text)
        except KeyboardInterrupt:
            runner.cancel()
            view.error("Cancelled.")


def _history_file() -> Path:
    folder = Path(platformdirs.user_data_dir("buildra", appauthor=False))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "prompt_history"
