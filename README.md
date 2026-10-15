# Buildra

An open-source coding agent for your terminal, built with
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) and
[DeepSeek](https://api-docs.deepseek.com). Inspired by Claude Code, Codex CLI,
Cursor and [opencode](https://github.com/anomalyco/opencode).

Ask it to explain code, fix a failing test or make a change. It reads and
searches your project, edits files and runs commands, and asks before
anything that changes your system.

> **Status: v0.1 (early alpha).** The core loop works end to end. Sessions are
> not saved yet, and the permission policy is fixed (see [Safety](#safety)).
> See the [roadmap](#roadmap).

Buildra is also a learning project: every design decision is written down in
[docs/](docs/).

## Install

You need Python 3.11+ and a [DeepSeek API key](https://platform.deepseek.com).

```bash
# with pipx (or: uv tool install ...)
pipx install git+https://github.com/SaqlainAmjad/Buildra-The-Open-Source-Coding-Agent.git
```

Or from a clone:

```bash
git clone https://github.com/SaqlainAmjad/Buildra-The-Open-Source-Coding-Agent.git buildra
cd buildra
uv sync          # or: python -m venv .venv && pip install -e .
uv run buildra --version
```

## Quickstart

Set your key (or put it in a `.env` file in the project you work on; see
[.env.example](.env.example)):

```bash
export DEEPSEEK_API_KEY=sk-...           # PowerShell: $env:DEEPSEEK_API_KEY="sk-..."
```

Then, inside any project:

```bash
buildra                                  # interactive chat
buildra "why does test_parse fail?"      # one request, then exit
buildra -m deepseek/deepseek-v4-pro      # pick a model
buildra -C path/to/project               # work in another directory
```

In the chat, type `exit` or press Ctrl+D to quit. Ctrl+C cancels a running
turn.

## Demo: fix a bug

The repo includes a tiny project with a planted bug:

```bash
cp -r examples/buggy-calc /tmp/buggy-calc        # work on a copy
buildra -C /tmp/buggy-calc "The tests are failing. Run them with 'python -m pytest -q', find the bug, fix it, and run the tests again."
```

A real run (abridged):

```
> bash  python -m pytest -q
  .F.  ...  assert average([2, 4, 6]) == 4
> read_file  calc.py
> read_file  test_calc.py
The bug is in `calc.py:12`: `average` subtracts an extra 1 from the mean.
? Allow edit_file  calc.py
  [y]es / [n]o / or type instructions: y
--- a/calc.py
+++ b/calc.py
-    return sum(values) / len(values) - 1
+    return sum(values) / len(values)
? Allow bash  python -m pytest -q
  [y]es / [n]o / or type instructions: y
  3 passed in 0.02s
Fixed. `average` subtracted an extra 1; removing it makes all 3 tests pass.
```

## How it works

Buildra is a LangGraph state graph implementing the ReAct loop
(reason -> act -> observe):

```
START -> agent --(answer)----------------------------------> END
           ^ |
           | +--(tool calls)--> authorize --> tools --(declined)--> END
           |                                    |
           +------------------------------------+
```

- **agent** calls the model with the conversation and the tool schemas, and
  streams its tokens to the terminal.
- **authorize** validates every tool call and pauses the graph
  (`interrupt()`) to ask you about calls that change things. It has no side
  effects, so LangGraph can safely re-run it when resuming.
- **tools** runs the approved calls and answers *every* call (including
  invalid ones) with a result the model can read and correct itself from.

Read [docs/architecture.md](docs/architecture.md) for the full design and
[docs/langgraph-concepts.md](docs/langgraph-concepts.md) for the LangGraph
features behind each part.

### Tools

| Tool | Does | Needs approval |
|---|---|---|
| `read_file` | read a file with line numbers, paged | no |
| `list_dir` | directory tree (skips `.git`, `node_modules`, `.gitignore`'d files) | no |
| `glob` | find files by pattern, newest first | no |
| `grep` | regex search in file contents | no |
| `edit_file` | exact, unique search-and-replace (shows a diff) | **yes** |
| `write_file` | create or overwrite a file (shows a diff) | **yes** |
| `bash` | run a command (Git Bash on Windows), 120 s default timeout | **yes** |
| `powershell` | run a PowerShell command (Windows only) | **yes** |

## Safety

- **Approval:** anything that writes files or runs commands asks first.
  Answer `y`, `n`, or type instructions to steer the agent instead.
- **Workspace sandbox:** file tools only accept paths inside the working
  directory (`..` and symlink escapes are resolved and rejected).
- **Commands** run with no input (prompts fail fast instead of hanging), with
  pagers disabled and a hard timeout that kills the whole process tree.
- **Limits:** tool output is capped (2000 lines / 50 KB, head and tail kept),
  and each turn has a step budget (default 50 model calls).
- **Honest limit:** shell commands are *not* OS-sandboxed. An approved
  command can do anything your user account can. Read what you approve.

## Configuration

Optional TOML files, merged in this order (later wins):

1. global: `~/.config/buildra/config.toml` on Linux,
   `~/Library/Application Support/buildra/config.toml` on macOS,
   `%LOCALAPPDATA%\buildra\config.toml` on Windows
2. `<project>/.buildra/config.toml`
3. environment: `BUILDRA_MODEL`, `BUILDRA_REASONING`

```toml
[llm]
model = "deepseek/deepseek-v4-pro"   # "provider/model"
reasoning = "high"                   # off | low | high | max (DeepSeek thinking mode)

[agent]
max_steps = 30

[tools]
shell_timeout_s = 300
```

All options and defaults are in
[src/buildra/config/schema.py](src/buildra/config/schema.py). The LLM layer is
provider-agnostic: DeepSeek ships today, and other providers are one adapter
module each ([src/buildra/llm/providers/](src/buildra/llm/providers/)).

## Roadmap

| Version | Theme | Highlights |
|---|---|---|
| **v0.1** (done) | Core loop | streaming chat, ReAct graph, file / search / shell tools, approvals |
| v0.2 | Safe and stateful | allow / ask / deny rules, "always allow", resumable sessions, context compaction, todos, plan mode |
| v0.3 | Extensible | AGENTS.md, subagents, MCP tools, slash commands |

Later: more providers (OpenAI, Anthropic, Gemini), fuzzy edit matching,
concurrent read-only tools, live markdown rendering, ripgrep acceleration.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests run offline with a scripted fake
model: `uv run pytest`.

## License

[MIT](LICENSE)
