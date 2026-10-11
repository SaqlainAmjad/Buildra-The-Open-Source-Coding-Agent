# LangGraph concepts for a coding agent

What this is: the LangGraph features Buildra uses, checked against the
current official docs (docs.langchain.com, October 2026), each mapped to the
coding-agent feature it powers.

Versions checked on PyPI (2026-10-10): `langgraph 1.2.14`,
`langgraph-prebuilt 1.1.0`, `langgraph-checkpoint-sqlite 3.1.1`,
`langchain-core 1.6.9`, `langchain-deepseek 1.1.1`,
`langchain-mcp-adapters 0.3.2`. Buildra pins `langgraph>=1.2,<2`.

> **To verify on Day 1 against the installed source:** the exact `ToolNode`
> constructor (`handle_tool_errors`, `wrap_tool_call`) and `trim_messages`
> arguments. The docs pages fetched did not show the full signatures.
> Anything marked *(verify)* below is in that category.

---

## 1. StateGraph: the program is a graph

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(AgentState, context_schema=AgentContext)
builder.add_node("agent", call_model)
builder.add_edge(START, "agent")
graph = builder.compile(checkpointer=saver)
```

- A graph is **state** (a typed dict), **nodes** (functions `state ->
  partial update`) and **edges** (which node runs next).
- Execution happens in **super-steps**: all nodes scheduled for a step run,
  their updates merge into state, and then edges pick the next nodes.
- You must `compile()` before running. Compile is where the checkpointer,
  store and interrupt settings attach.

**Coding agent:** the agent loop from opencode (`prompt.ts` `while(true)`)
becomes a cycle in the graph. Instead of `continue` and `break` we have
edges back to `agent` and to `END`.

## 2. State and reducers

```python
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]   # reducer
    mode: str                                             # plain overwrite
```

- Without a reducer, a node's returned value **replaces** the key.
- With `Annotated[T, reducer]`, LangGraph calls `reducer(old, new)`.
  `add_messages` **appends**, or **replaces by message id**, and turns dicts
  into message objects.
- `RemoveMessage(id=...)` in an update deletes that message.
  `RemoveMessage(id=REMOVE_ALL_MESSAGES)` clears everything
  (`from langgraph.graph.message import REMOVE_ALL_MESSAGES`).
- `Overwrite([...])` (`langgraph.types`) bypasses a reducer for one update.
- `MessagesState` is a prebuilt `TypedDict` with just `messages`.
- Nodes return **partial** updates: `return {"messages": [ai_msg]}`.

**Coding agent:** conversation history (`messages`), current mode
(`build`/`plan`), the todo list, session-scoped "always allow" rules, the
compaction summary. Reducers decide how concurrent or incremental writes
combine. This matters when tools run in parallel and each returns a
ToolMessage.

## 3. State vs runtime context

```python
from dataclasses import dataclass
from langgraph.runtime import Runtime

@dataclass
class AgentContext:
    workdir: Path
    llm: BaseChatModel
    tools: ToolRegistry

def call_model(state: AgentState, runtime: Runtime[AgentContext]):
    runtime.context.llm ...

graph.invoke(inputs, config, context=AgentContext(...))
```

- **State** is checkpointed and serialised. It holds data that belongs to
  the conversation.
- **Context** (`context_schema`) holds per-run *dependencies* that are not
  saved: the LLM client, config, working directory, tool registry.
  `runtime` also exposes `store` and `stream_writer`.

**Coding agent:** this split keeps checkpoints small and makes tests easy:
inject a fake LLM through context. Rule of thumb: if it should survive
`/resume`, put it in state. If it is a service, put it in context.

## 4. Edges, conditional routing, Command

```python
def route_after_agent(state) -> Literal["authorize", "__end__"]:
    return "authorize" if state["messages"][-1].tool_calls else END

builder.add_conditional_edges("agent", route_after_agent, ["authorize", END])
```

- Conditional edge = a pure function from state to the next node name(s).
  Keep routers **pure and cheap**. They are the easiest part of the agent to
  unit-test.
- A node may instead return `Command(update={...}, goto="node")`, which
  updates state and routes in one step. Annotate the return type with
  `Command[Literal[...]]` so the graph can be drawn. Don't mix static edges
  and `Command` routing on the same node.
- `Send("node", custom_state)` fans out dynamically (map-reduce).

**Coding agent:** "did the model ask for tools?", "is the context too
big?", "were all tool calls denied?". These are exactly opencode's
`"continue" | "stop" | "compact"` results, now made visible as edges.

## 5. The ReAct loop and tools

The official pattern (docs, "Workflows and agents"):

```python
llm_with_tools = llm.bind_tools(tools)

def llm_call(state):  return {"messages": [llm_with_tools.invoke(sys + state["messages"])]}
def tool_node(state):
    out = []
    for call in state["messages"][-1].tool_calls:
        result = tools_by_name[call["name"]].invoke(call["args"])
        out.append(ToolMessage(content=result, tool_call_id=call["id"]))
    return {"messages": out}

builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
builder.add_edge("tool_node", "llm_call")
```

- **ReAct** = Reason (the model decides) + Act (a tool runs) + Observe (the
  result goes back to the model), repeated until the model answers without
  a tool call.
- `bind_tools` sends JSON schemas of the tools to the model. The model
  replies with `AIMessage.tool_calls = [{"name", "args", "id"}]`.
- **Unparseable** tool calls (bad JSON) land in `AIMessage.invalid_tool_calls`,
  not in `tool_calls`. A robust agent must answer those too. Providers
  require every tool call id to get a ToolMessage.
- Prebuilt `ToolNode(tools)` (`from langgraph.prebuilt import ToolNode`)
  runs calls in parallel and can inject graph state via `ToolRuntime`.
  `tools_condition` is the prebuilt router.
- A tool can return `Command(update={...})` to write graph state directly
  (for example the todo list), not just a string.

**Buildra decision:** use a **custom tool-execution node**, not the prebuilt
`ToolNode`, because we need (a) permission decisions from the preceding
node, (b) Pydantic validation with model-readable errors, (c) truncation,
(d) handling of `invalid_tool_calls`, and (e) live progress events. Writing
it by hand is also the best way to learn what `ToolNode` does. We can still
use `langchain_core.tools.StructuredTool` for schemas and `bind_tools`.

## 6. Recursion limit and step budgets

- `config={"recursion_limit": N}` caps super-steps per run (default 1000
  since 1.0.6). Exceeding it raises `GraphRecursionError`
  (`langgraph.errors`).
- Proactive alternative: a `remaining_steps: RemainingSteps` state key
  (`langgraph.managed`) that routers can check before the hard limit.

**Coding agent:** opencode's `agent.steps` plus its "MAX STEPS" note. When
`remaining_steps` is low, the agent node tells the model "this is your last
step, summarise", so it doesn't get cut off mid-task.

## 7. Checkpointers (persistence)

```python
from langgraph.checkpoint.sqlite import SqliteSaver      # pip install langgraph-checkpoint-sqlite
saver = SqliteSaver(sqlite3.connect(db_path, check_same_thread=False))
graph = builder.compile(checkpointer=saver)
config = {"configurable": {"thread_id": session_id}}
```

- After **every super-step** the full state is saved as a checkpoint
  under a `thread_id`. Same thread id means the same conversation.
- `graph.get_state(config)` returns the latest snapshot (`.values`, `.next`,
  `.tasks`, `.interrupts`). `get_state_history(config)` returns all
  checkpoints, which enables time travel. `update_state(config, values)`
  edits state from outside.
- `checkpointer.list(config)` lists checkpoints and
  `checkpointer.delete_thread(thread_id)` deletes a thread.
- `InMemorySaver` (`langgraph.checkpoint.memory`) is for tests. `SqliteSaver`
  / `AsyncSqliteSaver` are for local apps. `PostgresSaver` is for production
  servers.
- Checkpointers are **required** for interrupts.

**Coding agent:** persistent sessions. `/sessions` lists threads and
`--resume <id>` continues one. Crash recovery comes for free: the last
completed step is on disk. LangGraph has no first-class "list all threads
with titles" API for SQLite, so Buildra keeps a tiny `sessions` table (id,
title, cwd, timestamps) next to the checkpoints.

## 8. Interrupts (human-in-the-loop)

```python
from langgraph.types import interrupt, Command

def authorize(state):
    decision = interrupt({"tool": "bash", "command": "rm -rf build"})  # pauses here
    ...

# caller
for chunk in graph.stream(inputs, config, ...): ...
snapshot = graph.get_state(config)          # snapshot.interrupts holds the payloads
graph.stream(Command(resume={"decision": "once"}), config)
```

- `interrupt(payload)` saves state and stops the run. The payload surfaces
  to the caller (`__interrupt__` in `invoke` output, `stream.interrupts` in
  v3 event streaming, `snapshot.interrupts` via `get_state`).
- Resume with `Command(resume=value)` on the same `thread_id`. That value
  becomes the return value of `interrupt()`.
- **Critical rule: on resume, the node re-runs from the top.** Anything
  before `interrupt()` runs again. So:
  - Side effects before an interrupt must be idempotent, or be moved after it.
  - Don't wrap `interrupt()` in a bare `try/except`. It works by raising.
  - Multiple interrupts in a node are matched **by order**, so the order and
    count must be deterministic.
  - Avoid `while True: interrupt()` validation loops. Loop with an edge
    instead.
- `interrupt()` can be called inside a tool, but the same re-run rule
  applies to the whole tool node.
- `response_schema=` (langgraph >= 1.2.12) declares and validates the
  resume value.

**Coding agent:** the permission prompt ("Allow `bash: npm test`? [y]es
once / [a]lways / [n]o"). This is the LangGraph-native replacement for
opencode's Deferred-based `ask()`.

**Buildra design consequence:** put all permission interrupts in a
dedicated **`authorize` node that has no side effects**. That node runs
before the tool node, so re-running it on resume is harmless. If we
interrupted inside the tool node, approving call #2 would re-execute call
#1 (for example, run a bash command twice). This is the most important
LangGraph gotcha for a coding agent.

## 9. Streaming

Two layers:

**(a) `graph.stream(..., stream_mode=..., version="v2")`**, the low-level
raw modes. With `version="v2"` every chunk is `{"type", "ns", "data"}`.

| mode | yields | Buildra use |
|---|---|---|
| `messages` | `(AIMessageChunk, metadata)` per token; `metadata["langgraph_node"]` | live token streaming of the answer |
| `updates` | `{node_name: update}` after each node | show completed tool calls and results |
| `custom` | anything sent with `get_stream_writer()` | tool progress ("running bash...", spinner text) |
| `values` | full state after each step | debugging |
| `checkpoints`, `tasks`, `debug` | internals | `--debug` flag |

Combine modes with a list: `stream_mode=["messages", "updates", "custom"]`.

**(b) `graph.stream_events(..., version="v3")` / `astream_events`**, the
newer high-level event streaming with typed projections: `stream.messages`
(with `message.text` token iterator), `stream.values`, `stream.subgraphs`,
`stream.output`, `stream.interrupted`, `stream.interrupts`. The docs
recommend it for application code. `stream_mode` is still supported, for
low-level access.

**Buildra decision:** start with **(a) `stream_mode` v2**. Each mode maps
to one concept, which is better for learning, and the renderer is a simple
`match chunk["type"]`. The CLI renderer sits behind a small interface, so
switching to v3 later touches one file. *(Revisit on Day 2 if v3's
`interrupts` projection makes the REPL much simpler.)*

## 10. Subgraphs

- A compiled graph can be **added as a node** (shared state keys) or
  **invoked inside a node or tool** (different schema; you map input and
  output yourself).
- Subgraph checkpointing: `compile(checkpointer=None)` (default) is
  per-invocation and inherits the parent's saver, so interrupts work within
  a call. `True` accumulates state per thread. `False` is stateless.
- Interrupts inside subgraphs propagate to the top-level caller.
- Streaming exposes subgraph events with a namespace (`ns`), so the UI can
  indent subagent output.

**Coding agent:** subagents. The `task` tool invokes a compiled subgraph
built from the same builder with the `explore` profile and a fresh
`messages` list, then returns only its final answer. This mirrors
opencode's child session.

## 11. Memory: Store vs checkpointer

- **Checkpointer** = short-term, per-thread (this conversation).
- **Store** (`InMemoryStore`, `langgraph.store.memory`; Postgres store in
  production) = long-term, **cross-thread** key-value data under
  namespaces. Nodes reach it via `runtime.store`.

**Coding agent:** cross-session memory, such as "user prefers pytest" or
learned project facts. **Not in Buildra v0.3.** AGENTS.md covers project
memory explicitly and transparently. The Store is a roadmap item.

## 12. Context-window tools from langchain-core

```python
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
trim_messages(msgs, strategy="last", token_counter=count_tokens_approximately,
              max_tokens=N, start_on="human", end_on=("human", "tool"))
```

- Trimming changes **what is sent** to the model. `RemoveMessage` changes
  **what is stored**.
- The docs warn that history must stay valid for the provider: start on a
  user message, and every tool call must keep its ToolMessage. Never split
  an `AIMessage(tool_calls)` from its results.
- Summarisation pattern: a `summary` state key plus a node that summarises
  old messages and `RemoveMessage`s them.

**Coding agent:** Day 4 compaction (opencode's prune and summarise
strategy, see architecture.md).

## 13. Other features noted but not used yet

- `CachePolicy` / `InMemoryCache` for node result caching.
- `RetryPolicy` on nodes (fault-tolerance guide). We may use it for
  transient LLM errors, but the adapter retry is simpler to explain.
- Functional API (`@entrypoint`, `@task`). The Graph API is chosen because
  the diagram *is* the design.
- LangSmith tracing (env vars only), an optional v0.3 item.

---

## Concept -> feature cheat sheet

| LangGraph concept | Buildra feature |
|---|---|
| StateGraph + cycle | agent loop |
| `add_messages` reducer | conversation history |
| conditional edges | "tools or answer?", "compact?" |
| custom tool node | validation, truncation, permission-aware execution |
| `Command(update=)` from a tool | todo list writes into state |
| runtime context | LLM client, config, registry injection (testable) |
| checkpointer + thread_id | persistent sessions, `/sessions`, resume |
| `interrupt()` / `Command(resume=)` | allow / ask / deny prompts |
| `stream_mode` messages / updates / custom | token streaming, tool display, progress |
| `RemainingSteps` / `recursion_limit` | step budget and "final step" nudge |
| `RemoveMessage` + summary node | context compaction |
| subgraph | subagents (`task` tool) |
| Store | (roadmap) cross-session memory |
