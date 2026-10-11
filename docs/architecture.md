# Buildra architecture

What this is: the design for Buildra, a terminal coding agent built on
LangGraph and DeepSeek. Read `opencode-analysis.md` and
`langgraph-concepts.md` first. This document maps the first onto the
second.

Status: **approved 2026-10-11.** Items marked **[decision]** are choices
that are hard to undo later. Section 5 records what was decided.

---

## 1. Goals and non-goals

Goals: a readable, well-tested ReAct coding agent that is safe by default
(permissions, sandbox, timeouts), persistent (resume sessions) and
extensible (AGENTS.md, subagents, MCP). Each LangGraph concept should be
visible in the code.

Non-goals (for v0.3): client/server split, multiple LLM providers, plugins,
LSP, git snapshots/revert, web tools, image input, cross-session memory.

---

## 2. opencode concept -> LangGraph implementation

| # | Concept | opencode | Buildra (LangGraph) | Version |
|---|---|---|---|---|
| 1 | Agent loop | `while(true)` in `session/prompt.ts:1081` | cyclic `StateGraph`: `agent -> authorize -> tools -> agent` | v0.1 |
| 2 | Loop exit | "finished without tool calls" (`prompt.ts:1111`) | conditional edge on `AIMessage.tool_calls` / `invalid_tool_calls` | v0.1 |
| 3 | History | message + part tables | `messages` with the `add_messages` reducer | v0.1 |
| 4 | Streaming | processor + event bus | `graph.stream(stream_mode=["messages","updates","custom"], version="v2")` | v0.1 |
| 5 | Tool definition | `Tool.define` + `.txt` description (`tool/tool.ts`) | `BuildraTool` = Pydantic args model + description + `permission(args)` + `run(args, ctx)`, exported as LangChain `StructuredTool` for `bind_tools` | v0.1 |
| 6 | Invalid args -> retry | `InvalidArgumentsError` (`tool.ts:24`) | tool node returns a ToolMessage "invalid arguments: ... rewrite the input", and the model retries on the next loop | v0.1 |
| 7 | Output truncation | `truncate.ts` 2000 lines / 50 KB | `tools/output.py` head and tail truncation, same limits | v0.1 |
| 8 | Provider retries | `retry.ts` | `llm/` adapter: retry with backoff on 429/5xx/timeouts | v0.1 |
| 9 | System prompt | rebuilt each turn (`system.ts`) | `agent/system_prompt.py` builds it in the `agent` node, never stored in state | v0.1 |
| 10 | Permission rules | `evaluate()` last-match-wins (`permission/index.ts:28`) | `permissions/rules.py`, ported with the same semantics | v0.2 |
| 11 | Permission ask | Deferred inside tool (`ctx.ask`) | `authorize` node + `interrupt()`; resume with `Command(resume=decision)` | v0.2 |
| 12 | Always-allow | session `approved` rules | `session_rules` state key (persisted in the checkpoint) | v0.2 |
| 13 | Hide denied tools | `Permission.disabled` | the `agent` node binds only visible tools | v0.2 |
| 14 | Path sandbox | `external_directory` ask | `permissions/sandbox.py` resolves paths; outside workdir = `external_directory` permission, **ask** by default (always-allow is per directory) | v0.1 (deny until asks exist), v0.2 (ask) |
| 15 | Doom loop | 3 identical calls -> ask (`processor.ts:356`) | the `authorize` node detects it and asks | v0.2 |
| 16 | Sessions | SQLite sessions | `SqliteSaver` checkpointer + `sessions` index table | v0.2 |
| 17 | Prune old tool output | `compaction.prune` | `memory/context_window.py`: replace old ToolMessage content with a placeholder (projection at model-call time) | v0.2 |
| 18 | Compaction | `compaction` agent + summary message | `compact` node: LLM summary into the `summary` key, `RemoveMessage` for old messages | v0.2 |
| 19 | Todo list | `todowrite` (full list each time) | `todo_write` tool returns `Command(update={"todos": ...})` | v0.2 |
| 20 | Plan vs build | `plan` agent + injected reminder | `mode` state key -> `AgentProfile` (rules + reminder); `/plan`, `/build` | v0.2 |
| 21 | AGENTS.md | walk up cwd to the root, first match wins | `memory/instructions.py`, same rule plus a global file | v0.3 |
| 22 | Subagents | `task` tool -> child session, final text only, depth 1 | `task` tool invokes a compiled subgraph with the `explore` profile and a fresh `messages`; returns the final text | v0.3 |
| 23 | MCP | MCP SDK, `server_tool` names | `langchain-mcp-adapters`, sanitised `server_tool` names, permission key `mcp` | v0.3 |
| 24 | Slash commands | TUI commands + prompt templates | `cli/slash.py`: `/help /clear /model /sessions /plan /build /compact` | v0.3 |
| 25 | Step limit | `agent.steps` + MAX_STEPS note | `max_steps` config + `RemainingSteps` + final-step nudge | v0.1 |

---

## 3. The graph

```
            START
              |
              v
      +---------------+   over budget    +-----------+
      | route_context |----------------->|  compact  |
      +---------------+                  +-----------+
              | within budget                  |
              v                                 |
      +---------------+ <----------------------+
 +--->|     agent     |  builds system prompt, calls DeepSeek (streams tokens)
 |    +---------------+
 |            | route_after_agent
 |            |-- no tool calls ---------------------------------> END
 |            v
 |    +---------------+  evaluates rules for every call, may interrupt()
 |    |   authorize   |  (no side effects, so safe to re-run on resume)
 |    +---------------+
 |            | writes `decisions` {call_id: allow | deny(+reason) | invalid(+error)}
 |            v
 |    +---------------+  runs allowed calls, writes ToolMessage per call id,
 |    |     tools     |  truncates output, emits progress via stream writer
 |    +---------------+
 |            |
 +--- route_context (loop)       (if every call was denied by "reject": END)
```

Nodes (each one file under `agent/nodes/`):

| Node | Reads | Writes | Notes |
|---|---|---|---|
| `compact` | messages, summary | summary, `RemoveMessage`s | v0.2. Keeps a recent tail and never splits a tool-call pair. |
| `agent` | messages, mode, summary, todos | messages (+1 AIMessage) | Builds the system prompt and binds visible tools. Adds the "final step" note when `remaining_steps` is low. |
| `authorize` | last AIMessage, session_rules, mode | decisions, session_rules | Pure evaluation, plus at most **one** `interrupt()` carrying *all* pending asks as a batch. One interrupt keeps resume deterministic. |
| `tools` | last AIMessage, decisions | messages (ToolMessages), todos | Every `tool_call` id **and** every `invalid_tool_call` id gets exactly one ToolMessage. Independent calls run concurrently. |

Routers (pure functions in `agent/routing.py`, unit-tested without an
LLM): `route_context`, `route_after_agent`, `route_after_tools`.

### Why `authorize` is separate from `tools` [decision]

opencode asks for permission inside each tool. In LangGraph, `interrupt()`
re-runs its **whole node** on resume. If the interrupt lived inside the
tool node, approving the 2nd call would re-execute the 1st (a duplicated
`bash` run, a double write). Splitting "decide" (pure, re-runnable) from
"do" (side effects, never interrupted) removes that hazard entirely. Tools
still own their permission *semantics*: each tool exposes
`permission(args) -> PermissionRequest(key, patterns, always, preview)`.
The edit tool, for example, provides the path and a diff preview. That
preserves opencode's "the tool knows the right pattern" insight.

### Malformed tool calls (validate, then retry)

1. **Unparseable JSON** (`AIMessage.invalid_tool_calls`): `authorize` marks
   it `invalid`. `tools` answers "Your call to X had malformed JSON
   arguments: <error>. Re-issue the call with valid JSON."
2. **Schema mismatch**: Pydantic validation in `authorize` (so we never ask
   the user to approve garbage). The answer quotes the validation errors in
   opencode's "rewrite the input" style.
3. **Unknown tool name**: "Unknown tool X. Available tools: ...".
4. The model sees the error on the next `agent` turn and retries. That is
   the retry loop, with no special machinery. A per-turn cap
   (`max_invalid_calls`, default 3 consecutive) stops endless garbage by
   ending the turn with a visible error.
5. **API-level failures** (HTTP 429/5xx/timeout) are retried inside the
   `llm/` adapter with exponential backoff (3 attempts), separate from the
   above.

### State

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    mode: Literal["build", "plan"]                 # v0.2
    todos: list[Todo]                              # v0.2
    summary: str | None                            # v0.2 compaction
    session_rules: list[Rule]                      # v0.2 "always" approvals
    decisions: dict[str, Decision]                 # authorize -> tools handoff
    remaining_steps: RemainingSteps                # managed by LangGraph
```

Runtime context (not persisted): `workdir`, `settings`, `llm`,
`tool_registry`, `instructions_loader`. Tests pass a fake LLM here.

---

## 4. Folder structure

```
Buildra/
├── pyproject.toml            # hatchling build, deps, ruff, mypy, pytest config
├── README.md  LICENSE (MIT)  CONTRIBUTING.md  ARCHITECTURE.md (-> docs/architecture.md)
├── .env.example              # DEEPSEEK_API_KEY=
├── .pre-commit-config.yaml   # ruff, ruff-format, mypy
├── .github/workflows/ci.yml  # lint + typecheck + tests on 3.11 / 3.12 / 3.13, ubuntu + windows
├── docs/                     # these research and design docs, demo scripts
├── src/buildra/
│   ├── __main__.py           # `python -m buildra`
│   ├── cli/                  # terminal UI only, no agent logic
│   │   ├── app.py            # typer entry point: `buildra [--resume ID] [--model M]`
│   │   ├── repl.py           # input loop (prompt_toolkit), drives graph.stream
│   │   ├── render.py         # rich rendering of tokens, tool calls, diffs
│   │   ├── approval.py       # permission prompt UI -> resume value      (v0.2)
│   │   └── slash.py          # slash command parsing and dispatch        (v0.3)
│   ├── agent/                # the LangGraph program
│   │   ├── state.py          # AgentState, Todo, Decision
│   │   ├── context.py        # AgentContext (runtime dependencies)
│   │   ├── graph.py          # build_graph(): nodes + edges, nothing else
│   │   ├── routing.py        # pure router functions
│   │   ├── nodes/            # agent.py, authorize.py, tools.py, compact.py
│   │   ├── profiles.py       # AgentProfile: build / plan / explore     (v0.2+)
│   │   ├── system_prompt.py  # assembles the prompt from prompts/ + env + AGENTS.md
│   │   └── prompts/          # system.md, plan_reminder.md, compaction.md, explore.md
│   ├── tools/
│   │   ├── base.py           # BuildraTool protocol, ToolContext, ToolResult
│   │   ├── output.py         # truncation (head + tail)
│   │   ├── registry.py       # name -> tool, LangChain StructuredTool export
│   │   ├── read_file.py  write_file.py  edit_file.py  list_dir.py
│   │   ├── glob.py  grep.py  bash.py
│   │   ├── todo.py           # (v0.2)
│   │   ├── task.py           # subagent tool (v0.3)
│   │   └── mcp.py            # MCP -> BuildraTool adapter (v0.3)
│   ├── llm/                  # provider-agnostic model access
│   │   ├── model_ref.py      # "provider/model" ids, e.g. deepseek/deepseek-flash
│   │   ├── registry.py       # provider name -> factory; create_chat_model(settings)
│   │   └── providers/        # one module per provider family
│   │       ├── base.py       # ChatProviderFactory protocol
│   │       └── deepseek.py   # ChatDeepSeek (others later: openai, anthropic, google)
│   ├── config/
│   │   ├── schema.py         # Pydantic Settings model
│   │   └── loader.py         # global + project TOML + env, deep merge
│   ├── permissions/
│   │   ├── rules.py          # Rule, evaluate() (last match wins), wildcard
│   │   ├── defaults.py       # default rulesets per profile
│   │   ├── sandbox.py        # path resolution + workdir containment
│   │   └── doom_loop.py      # repeated identical call detection
│   └── memory/
│       ├── checkpointer.py   # SqliteSaver factory, data dir
│       ├── sessions.py       # session index: list / title / resume
│       ├── context_window.py # token accounting, prune projection
│       └── instructions.py   # AGENTS.md discovery                (v0.3)
└── tests/                    # mirrors src/; LLM faked via GenericFakeChatModel
```

Responsibility rules: `cli/` never imports `langgraph` internals except to
call `graph.stream` and `get_state`. `agent/` never prints. `tools/` never
imports `agent/`. `permissions/` is pure (no I/O except `sandbox.resolve`).
There are no `utils.py` or `helpers.py` files.

---

## 5. Key technical decisions

| # | Decision | Choice | Why / alternative |
|---|---|---|---|
| D1 | Project location and name **[decision]** | `D:\OpenCode\Buildra`, package `buildra`, command `buildra` | The empty `Buildra/` folder suggests the name. |
| D2 | LLM client **[decision]** | Provider registry in `llm/`. Models are addressed as `provider/model` (opencode's `providerID/modelID`). Only `deepseek` (via `langchain-deepseek` `ChatDeepSeek`) ships now. OpenAI, Anthropic and Gemini are each one new module in `llm/providers/`. | Agent code depends only on LangChain's `BaseChatModel` interface (`bind_tools`, `stream`), which every LangChain provider implements. |
| D3 | Default model **[decision]** | `deepseek/deepseek-flash`; `deepseek/deepseek-v4-pro` selectable | Chosen by the user. Confirmed against `GET /models` on Day 1. |
| D4 | Thinking mode | Off by default in v0.1, configurable | Thinking mode plus tool calls may need `reasoning_content` passed back within a turn. This gets a Day 1 spike before we rely on it. |
| D5 | Streaming API | `stream_mode` v2 (not `stream_events` v3) | One mode per concept, so it is clearer to learn. The renderer is isolated if we switch. |
| D6 | Tool node | Custom, not prebuilt `ToolNode` | Needs decisions, validation, invalid-call handling and truncation. Also educational. |
| D7 | Permission check placement | Separate `authorize` node | Interrupt re-run safety (section 3). |
| D8 | Outside-workdir paths **[decision]** | **ask** (`external_directory` permission, pattern `<dir>/*`); "always" approves that directory for the session; configurable to `deny` | Chosen by the user, following opencode. The sandbox is the permission gate, not a hard wall. |
| D9 | Default rules | read/list/glob/grep: allow; write/edit: ask; bash: ask (allowlist of read-only prefixes such as `git status`, `ls`); `*.env` read: ask | Stricter than opencode. Users loosen it in config. |
| D10 | Shells **[decision]** | Two tools: `bash` (Git Bash on Windows, found via PATH or git's install dir) and `powershell` (registered on Windows only). Separate permission keys. | Chosen by the user. The model picks PowerShell for Windows-specific work. |
| D11 | Command limits | 120 s default timeout, 600 s max, kill the process tree, tail-truncate output | From opencode `shell.ts`. |
| D12 | bash sandboxing | Honest limits: cwd pinned to workdir, timeout, permission gate. **No OS-level sandbox.** | A real sandbox (containers, seccomp) is out of scope. The README will say so. |
| D13 | grep / glob | Pure Python (`pathlib`, `re`) honouring `.gitignore` via `pathspec`; use ripgrep if present (roadmap) | Portable and testable on Windows without extra binaries. |
| D14 | Config format | TOML: `~/.config/buildra/config.toml` (platformdirs), then `.buildra/config.toml` in the project, then env (`BUILDRA_*`, `DEEPSEEK_API_KEY`) | Stdlib `tomllib`, validated with Pydantic. |
| D15 | Session storage | `SqliteSaver` at `<user data dir>/buildra/sessions.db` + own `sessions` table | LangGraph has no "list threads with titles" API. |
| D16 | Context budget | Prune old tool outputs first, then LLM compaction at ~80% of `context_window` (config), using provider-reported `usage_metadata` | From opencode. DeepSeek's large context (1M advertised) means compaction rarely fires, so the threshold is configurable for testing. |
| D17 | Subagent permissions | Subagents cannot prompt: their `ask` becomes `deny` with a message. The `explore` profile is read-only, so this rarely matters. Depth 1. | Avoids nested interrupts through a tool call (re-run hazard). opencode also denies `question` in subagents. |
| D18 | CLI libraries | `typer` (entry), `prompt_toolkit` (input history, multiline), `rich` (markdown, diffs, spinners) | Standard and well-documented. |
| D19 | Packaging | `hatchling`, `src/` layout, console script `buildra`, `pipx install buildra` or `pipx install git+https://github.com/<you>/buildra` | One command to run. |
| D20 | Tests | `pytest`; fake LLM = `langchain_core` `GenericFakeChatModel` / scripted `AIMessage`s with `tool_calls`; `InMemorySaver`; temp-dir workdirs | Offline, deterministic. |

---

## 6. Version plan (from the spec, with cut lines)

- **Day 1 (after approval):** repo skeleton, tooling (ruff, mypy --strict,
  pytest, pre-commit, CI), config loader, `llm/` adapter + DeepSeek spike
  (model list, tool calling, streaming, thinking mode), `git init`.
- **v0.1 (Day 2):** graph (`agent` -> `tools`, no `authorize` yet; v0.1 has
  a static allow/deny check only, with no interactive asks), 7 tools,
  truncation, sandbox (deny outside workdir), streaming REPL, system prompt,
  step limit, invalid-call handling. Tag `v0.1.0`.
- **v0.2 (Days 3-4):** rules engine, `authorize` + interrupts + approval UI,
  doom loop, SQLite sessions + `--resume` + session list, pruning and
  compaction, todo tool, plan/build mode. Tag `v0.2.0`.
- **v0.3 (Days 4-5):** AGENTS.md, `task` subagent, MCP, slash commands,
  optional LangSmith (env vars only), docs polish, release. Tag `v0.3.0`.
  Definition of done: fix a real bug in a small repo through the CLI.

Roadmap candidates if time runs out (in the order they'd be cut): MCP
resources/prompts, `/model` hot-switch, LangSmith, nested AGENTS.md on
read, fuzzy edit fallbacks, ripgrep acceleration, Store-based long-term
memory, skills, git snapshots/undo.
