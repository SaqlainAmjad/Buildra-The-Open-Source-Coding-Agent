# opencode: architecture analysis

What this is: a study of the `opencode` repository (`../opencode`), written to
decide what to re-implement in Buildra. Paths are relative to
`opencode/packages/opencode/src/` unless noted. Line numbers refer to the
snapshot in this workspace.

opencode has two runtimes in the repo:

- **V1 / `packages/opencode`**: the shipping agent. TypeScript on the
  [Effect](https://effect.website) library, Vercel AI SDK for model calls,
  SQLite (Drizzle) for storage. This is the one analysed here.
- **V2 / `packages/core`**: a rewrite in progress (durable "session inbox",
  "context epochs", typed context sources). Its design notes in
  `opencode/CONTEXT.md` are worth reading, and a few ideas are noted below.

Effect is a heavy abstraction (services, layers, fibers). Ignore it while
reading: `Effect.gen(function* () { ... yield* x ... })` is roughly
`async function () { ... await x ... }`.

---

## 1. High-level architecture

```
 TUI / desktop / web / IDE            (clients)
        |  HTTP + SSE events
 server/  (HttpApi)                   (one server per project directory)
        |
 session/prompt.ts   <- the agent loop
   |-- session/processor.ts   streams one model response, records parts
   |-- session/llm.ts         provider call (AI SDK)
   |-- session/tools.ts       builds the tool set for this turn
   |      |-- tool/registry.ts  built-in + plugin + MCP tools
   |      `-- permission/       allow / ask / deny rules
   |-- session/system.ts + instruction.ts   system prompt assembly
   `-- session/compaction.ts  context window management
 storage: SQLite (session, message, part tables) + event bus
```

Key decisions:

- **Client/server split.** The TUI is just one client of a local HTTP server.
  Everything (permission prompts, streaming text, tool progress) flows as
  events on a bus (`bus/`, `event-v2-bridge.ts`). This is why opencode can
  have a desktop app, web UI and IDE integrations over one core.
- **Messages are made of parts.** A message has typed *parts*: `text`,
  `reasoning`, `tool` (with a state machine `pending -> running ->
  completed | error`), `file`, `step-start`, `step-finish`, `compaction`,
  `subtask`. The UI renders parts. The model sees a projection of them
  (`MessageV2.toModelMessagesEffect`).
- **Everything persists immediately.** Every part update is written to SQLite
  as it streams, so a crash loses at most the in-flight token.

**Buildra takeaway:** we are terminal-only, so no client/server split. The
part idea maps onto LangChain message types: `AIMessage` (text plus
`tool_calls`) and `ToolMessage` (results). Persistence-on-every-step is
exactly what a LangGraph checkpointer gives us for free.

---

## 2. The agent loop

`session/prompt.ts:1081-1341` (`runLoop`). Simplified:

```text
while true:
    msgs = load history (minus compacted parts)          # :1092
    if last assistant finished with no tool calls: break # :1111-1130
    step++
    if pending subtask:     run it; continue              # :1144
    if pending compaction:  run it; continue              # :1149
    if last turn's tokens overflow the window:            # :1161-1168
        schedule compaction; continue
    agent  = selected agent (build / plan / ...)
    if step >= agent.steps: append "MAX STEPS" assistant note   # :1178, :1281
    msgs   = apply reminders (plan-mode text etc.)        # :1180
    tools  = resolve tools allowed for this agent         # :1226
    system = env + AGENTS.md + MCP instructions + skills  # :1257-1269
    result = processor.process(system, msgs, tools)       # :1272
    if result == "stop": break
    if result == "compact": schedule compaction
```

Observations:

1. **The loop state lives in the database, not in variables.** Each iteration
   reloads messages and decides what to do from the last user/assistant
   message. That makes the loop restartable. This is the same idea as a
   LangGraph checkpointer, where each super-step reads state and writes
   updates.
2. **Exit condition = "assistant finished without tool calls".** The comment
   at `:1103` notes some providers report `finish_reason: "stop"` even when
   they emitted tool calls, so opencode checks for tool parts too.
   *Buildra:* route on `AIMessage.tool_calls`, not on `finish_reason`.
3. **Tool execution happens inside the stream.** The AI SDK runs tools as the
   model streams (`processor.ts` handles `tool-call` / `tool-result` events).
   One `process()` call is one model request plus its tool executions.
4. **Step limit.** `agent.steps` caps iterations. On the last step a fixed
   assistant message tells the model to stop and summarise instead of being
   cut off silently. *Buildra:* LangGraph's `recursion_limit` /
   `RemainingSteps` plus the same "final step" nudge.
5. **Side tasks run in the background.** Title generation (`:1134`) and
   session summary (`:1253`) are forked fibers using hidden agents (`title`,
   `summary`). Nice but not needed for us.

### Stream processor (`session/processor.ts`)

- Converts provider stream events into persisted parts (text deltas,
  reasoning, tool-call lifecycle).
- **Doom-loop detection** (`:29`, `:356-380`): if the last 3 tool parts are
  the same tool with byte-identical input, it raises a `doom_loop`
  permission *ask*. The human decides whether the agent may keep going.
  Cheap and very effective. *Buildra will copy this.*
- **Retries** (`:674-688`, `retry.ts`): provider errors are classified
  (rate limit, overloaded, context overflow) and retried with backoff. A
  context-overflow error returns `"compact"` instead of failing.
- Returns `"continue" | "stop" | "compact"` (`:693-695`): a tiny routing
  result that the loop switches on. This is a conditional edge in LangGraph
  terms.

---

## 3. Tool system

### Definition (`tool/tool.ts`)

A tool is `{ id, description, parameters (schema), execute(args, ctx) }`.

- **Validation wrapper** (`:99-149`): every tool's `execute` is wrapped to
  (a) decode arguments against the schema and (b) truncate output. Invalid
  arguments raise `InvalidArgumentsError` (`:24-34`), whose message is
  written *for the model*: "The X tool was called with invalid arguments:
  ... Please rewrite the input so it satisfies the expected schema." That
  string goes back as the tool result, so the model self-corrects on the
  next step. **This is the "malformed tool call -> validate -> retry"
  pattern.** There is also an `invalid` tool (`tool/invalid.ts`) that
  unknown tool names get routed to.
- **Context** (`:36-46`): tools receive `sessionID`, `abort` signal,
  `messages`, `metadata()` (live progress updates to the UI) and **`ask()`**
  (request permission).
- **Descriptions live in `.txt` files** next to the tool (`edit.txt`,
  `shell/shell.txt`, ...). They are long and prescriptive, for example
  "you must Read before Edit". Tool descriptions are prompt engineering.

### Built-in tools (`tool/registry.ts:101-119`)

`read`, `write`, `edit`, `apply_patch`, `glob`, `grep`, `shell` (bash),
`task` (subagent), `todowrite`, `question`, `webfetch`, `websearch`, `skill`,
`lsp`, `plan_exit`, `invalid`, plus plugin tools and MCP tools.

Notable details per tool:

| Tool | Detail worth copying |
|---|---|
| `read` (`read.ts:13-17`) | Default 2000 lines, 2000 chars per line, 50 KB cap. Output has line numbers. Tells the model the `offset` to continue from. |
| `edit` (`edit.ts`) | Exact string replace. Errors if not found or not unique (`edit.txt`). Has a **chain of fallback matchers** (`:695-703`): simple, line-trimmed, whitespace-normalised, indentation-flexible, block-anchor and others, because models often get whitespace slightly wrong. Preserves line endings and BOM. Builds a unified diff and puts it in the permission request so the user approves the diff. |
| `write` | Full overwrite. Same permission key as `edit`. |
| `shell` (`shell.ts`) | Parses the command with tree-sitter to find the directories it touches and its "command prefix" (`permission/arity.ts`: `git commit -m x` -> `git commit`, `npm run dev` -> `npm run dev`). Permission patterns are those prefixes, so "always allow `npm test`" works. Hard timeout (`:540-565`) with a model-readable message. Keeps only the tail of huge output (`:225-255`). |
| `grep` / `glob` | Use ripgrep; sorted by mtime; capped results. |
| `todowrite` (`todo.ts`) | The model sends the **whole** todo list each time (not diffs). Stored per session and shown in the UI. |

### Output truncation (`tool/truncate.ts:14-15`)

Every tool output is capped at 2000 lines / 50 KB. If truncated, the full
output goes to a temp file and the model is told the path (it may `read` or
`grep` it). From `CONTEXT.md:189-198`: keep the beginning *and* the end.
**Buildra:** same limits, head and tail, v0.1.

---

## 4. Permission model

Files: `permission/index.ts`, `agent/agent.ts:119-136`,
`tool/external-directory.ts`.

### Rules

A rule is `{ permission, pattern, action }` with action `allow | ask |
deny`. For example `{ "bash", "git push*", "ask" }` or
`{ "edit", "*.env", "deny" }`.

```ts
// permission/index.ts:28-38
evaluate(permission, pattern, ...rulesets) =
  rulesets.flat().findLast(rule => match(permission, rule.permission)
                                && match(pattern, rule.pattern))
  ?? { action: "ask" }
```

- **Last matching rule wins.** Rulesets are concatenated as defaults, then
  agent rules, then user config, then session approvals. A later, more
  specific rule overrides an earlier general one. This is simple and
  predictable.
- **No match means `ask`.** Safe default.
- Config shorthand (`fromConfig`, `:186-198`): `"bash": "ask"` or
  `"bash": { "*": "ask", "git status": "allow" }`.

### Asking (`:67-107`) and replying (`:109-167`)

- A tool calls `ctx.ask({permission, patterns, always, metadata})`. If any
  pattern is `deny`, it fails immediately. If all are `allow`, it returns.
  Otherwise it **suspends on a Deferred** and publishes an `Asked` event. The
  UI shows a prompt.
- Replies: `once` (allow this call), `always` (allow, and add the `always`
  patterns to the session's approved rules), `reject` (fail this call, and
  also **reject every other pending request in the session**). A reject can
  carry a message (`CorrectedError`), which becomes feedback to the model:
  "the user said X instead".
- The `always` patterns are chosen by the tool and can be wider than the
  request. For example, `edit` asks for `src/foo.ts` but offers `always: ["*"]`
  ("allow all edits this session"). `shell` offers `git commit*`.

### Where permission checks happen

**Inside each tool**, before the side effect. Examples:
`edit.ts:145-153` (with the diff as metadata), `shell.ts:263-291`,
`task.ts:119-129`. The tool knows the right *pattern* (a file path, a
command prefix, a subagent name). A generic "before any tool" hook could
not.

Two cross-cutting permissions:

- `external_directory` (`external-directory.ts`): any path outside the
  project root triggers an extra ask for `<dir>/*`.
- `doom_loop`: the repeated-identical-call detector above.

Tools that are `deny` with pattern `*` are **removed from the tool list**
entirely (`disabled()`, `:204-214`), so the model never sees them. That is
cheaper and less confusing than letting it call a tool and get refused.

### Defaults (`agent/agent.ts:119-136`)

`"*": allow`, `doom_loop: ask`, `external_directory: ask`, reading `*.env`
asks. opencode is permissive by default and relies on the user's config.
**Buildra will be stricter:** writes and bash default to `ask`, which suits
a learning tool.

---

## 5. Agents, modes and subagents

### Agent = a configuration bundle (`agent/agent.ts:35-55`)

`{ name, description, mode: primary|subagent|all, prompt, permission
ruleset, model?, temperature?, steps? }`. There is no agent class. An agent
is data that the single loop reads.

Built-ins (`:140-265`):

| Agent | Mode | What makes it different |
|---|---|---|
| `build` | primary | Default, full tools. |
| `plan` | primary | `edit: { "*": deny, ".opencode/plans/*.md": allow }`. Read-only except its plan file. |
| `general` | subagent | Full tools minus `todowrite`. |
| `explore` | subagent | `"*": deny`, then allows only read/grep/glob/list/bash/web. Own prompt. |
| `compaction`, `title`, `summary` | hidden | `"*": deny`. Utility LLM calls with special prompts. |

Users add or override agents in config (`:267-294`) or as markdown files
in `.opencode/agent/*.md`.

### Plan vs build mode (`session/reminders.ts`)

Plan mode is the `plan` agent **plus a reminder injected into the latest
user message** (`prompt/plan.txt`: "CRITICAL: Plan mode ACTIVE ... READ-ONLY").
When switching back to build, `build-switch.txt` is injected. Enforcement
is in permissions, and the reminder is there so the model doesn't waste
calls trying. Two layers: the prompt tells the model, the permissions make
sure.

### Subagents (`tool/task.ts`)

The `task` tool (`description`, `prompt`, `subagent_type`, optional
`task_id` to resume):

1. **Depth limit** (`:104-117`): count parent sessions. Default max depth
   is 1, so subagents cannot spawn subagents.
2. Ask permission `task` / `<subagent_type>`.
3. **Create a child session** with `parentID` (`:156-172`). The child gets
   its *own* fresh history. That is the whole point: exploration noise
   stays out of the parent's context.
4. Child permissions (`agent/subagent-permissions.ts`) inherit only the
   parent session's **deny** and `external_directory` rules, plus deny
   `todowrite` and `task` unless the subagent explicitly allows them.
5. Run the same loop on the child session (`ops.prompt`) and return **only
   the final text part** (`:200-225`), wrapped in `<task id=...>` so the
   parent can resume it via `task_id`.

**Buildra mapping:** a subagent is a compiled LangGraph subgraph (the same
graph builder with a different agent profile) invoked from the `task` tool
with a fresh message list.

---

## 6. Session and context management

### Sessions (`session/session.ts`)

Session rows have id, title (LLM-generated after the first message),
parentID (for subagents), directory, per-session permission rules, and
timestamps. Messages and parts are in their own tables. Sessions can be
listed, resumed, forked, reverted (`revert.ts`, using git snapshots from
`snapshot/`) and shared.

### Context window: three layers

1. **Per-tool truncation** (section 3): no single result over 50 KB.
2. **Pruning** (`compaction.ts:273-317`): walk backwards through tool
   results, protect the most recent ~40k tokens (`PRUNE_PROTECT`), and mark
   older tool outputs as `compacted`. They are then replayed to the model as
   "[Old tool result content cleared]". This only happens if it frees more
   than 20k tokens (`PRUNE_MINIMUM`). Cheap, no LLM call, and it keeps the
   conversation *structure* (the model still sees it called `read` on
   `foo.py`).
3. **Compaction / summarisation** (`compaction.ts:319+`, `overflow.ts`):
   - Trigger: last response's real token usage
     >= `context_limit - reserved_output` (`overflow.ts:22-34`). opencode
     uses the **provider-reported usage**, not an estimate.
   - Also triggered reactively when the provider returns a context-overflow
     error.
   - It serialises old messages to plain text (`serialize`, `:54-85`, with
     tool outputs truncated to 2000 chars), sends them to the hidden
     `compaction` agent with a structured-summary prompt, and stores the
     summary as a special assistant message. History before it is filtered
     out of future model calls (`filterCompacted`), and a recent tail
     (2k-15k tokens) is kept verbatim.
   - If a previous summary exists, it is fed in so summaries chain.

### System prompt assembly (`session/system.ts`, `instruction.ts`)

Rebuilt **every turn** (`prompt.ts:1257-1269`), never stored in history:

1. **Model-family base prompt** (`system.ts:28-51`): different prompt files
   for Claude, GPT, Gemini, Kimi and others. `default.txt` is the fallback.
   Models respond differently to the same instructions, so the base prompt
   is tuned per model.
2. **Environment block** (`:69-105`): model id, working directory, git repo
   yes/no, platform, date, in `<env>` tags.
3. **Instructions** (`instruction.ts`): global `~/.config/opencode/AGENTS.md`
   (or `~/.claude/CLAUDE.md`), then the **first** project `AGENTS.md` /
   `CLAUDE.md` found walking up from cwd to the worktree root (`:110-153`),
   plus `instructions: [...]` globs or URLs from config. Each is prefixed
   `Instructions from: <path>`.
   - **Nested instructions** (`:179-221`): when the model *reads* a file in
     `pkg/sub/`, any `AGENTS.md` between that file and the root is attached
     to the read result once. Clever and lazy.
4. MCP server instructions and the skills list.

The base prompt (`prompt/default.txt`) is worth reading: be concise (<4
lines), follow existing conventions, never assume a library exists, run
lint/tests after changes, never commit unless asked, parallelise
independent tool calls, cite `file:line`.

V2 refinement (`CONTEXT.md`): keep the system prompt **byte-stable**
during a "context epoch" so provider prompt caching hits, and announce
changes (date, AGENTS.md edits) as chronological "mid-conversation system
messages" instead of rewriting the prefix. DeepSeek also bills cache hits
much lower than misses (about 50x on current pricing), so **keeping our
system prompt stable is worth real money.** Buildra rule: no timestamps
with seconds or volatile data in the system prompt.

---

## 7. MCP and plugins

### MCP (`mcp/index.ts`, `mcp/catalog.ts`)

- Transports: stdio (local command), Streamable HTTP, falling back to SSE.
  OAuth for remote servers.
- Configured under `mcp: { name: { type: "local", command: [...] } |
  { type: "remote", url } }`.
- Tool names are namespaced `sanitize(server) + "_" + sanitize(tool)`
  (`catalog.ts:117-119`) to avoid collisions and satisfy provider name rules
  (`[a-zA-Z0-9_-]`).
- MCP tools go through the same permission system (keyed by tool name).
- MCP *prompts* become slash commands, and MCP *resources* get three
  generic tools (`list_mcp_resources`, ...).
- Server-provided `instructions` are added to the system prompt.

### Plugins (`plugin/`)

JS modules with hooks: `tool.execute.before/after` (`session/tools.ts:106-125`),
`chat.system.transform`, `chat.messages.transform`, `session.compacting`,
`shell.env`, plus provider auth plugins. **Out of scope for Buildra.** MCP
covers extensibility for us.

### Skills (`skill/`) and commands (`command/index.ts`)

- **Commands** are prompt templates with `$1`, `$ARGUMENTS` and
  `` !`shell` `` interpolation. Sources: built-ins (`/init` writes AGENTS.md,
  `/review`), config, MCP prompts, skills. A command can run as a subtask.
  Note: opencode's slash commands are *prompts sent to the model*, while
  UI actions like `/sessions` are handled by the TUI.
- **Skills** are markdown instruction packs that the model loads on demand
  via the `skill` tool. Only names and descriptions are in the system prompt.
  This is a context-saving pattern (progressive disclosure). Roadmap item
  for Buildra.

---

## 8. Configuration (`config/config.ts`)

- JSON/JSONC. Precedence, low to high: remote org config, global
  `~/.config/opencode/opencode.json[c]` (`:140`, `:264-274`), `OPENCODE_CONFIG`
  file, project `opencode.json` files found walking up, `.opencode/` dirs
  (with `agent/*.md`, `command/*.md`), and `OPENCODE_CONFIG_CONTENT`. Merged
  with deep-merge (`mergeDeep`).
- `{env:VAR}` and `{file:path}` substitution (`config/variable.ts`).
- Keys: `model`, `agent`, `permission`, `mcp`, `instructions`, `command`,
  `compaction { auto, prune, reserved }`, `tool_output { max_lines,
  max_bytes }`, `default_agent`, `subagent_depth`, and others.

**Buildra:** TOML (stdlib `tomllib`), with global then project config files,
env vars on top, and a Pydantic schema for validation.

---

## 9. What Buildra takes, adapts, or drops

| opencode idea | Buildra decision |
|---|---|
| Loop driven by persisted state | **Take.** This is LangGraph's model. |
| Exit on "no tool calls" | **Take.** Conditional edge. |
| Agent = data (prompt + permission rules + steps) | **Take.** `AgentProfile` dataclass: build, plan, explore. |
| Last-match-wins rules, default ask | **Take.** Same semantics, ported. |
| `ask` inside each tool | **Adapt.** Tools declare their permission key and pattern. The check runs in a dedicated graph node using `interrupt()`, so it happens before any tool runs (see architecture.md for why). |
| once / always / reject + feedback | **Take.** |
| Hide fully-denied tools | **Take.** |
| `external_directory` ask | **Adapt.** Default is **deny** (the spec asks for a working-directory sandbox), configurable to `ask`. |
| Doom-loop detector | **Take.** |
| Invalid-args error written for the model | **Take.** Pydantic validation produces a "rewrite your input" ToolMessage. |
| Fuzzy edit matchers | **Partly.** Exact match first, then one line-trimmed fallback (v0.1). The full chain goes on the roadmap. |
| Tool output truncation (head and tail) | **Take**, v0.1. |
| Prune old tool outputs, then LLM compaction | **Take**, v0.2 (Day 4). |
| Rebuild system prompt each turn, byte-stable | **Take.** |
| AGENTS.md walk-up discovery | **Take**, v0.3. Nested-on-read is on the roadmap. |
| Subagent = child session, final text only, depth 1 | **Take**, as a subgraph. |
| MCP with namespaced tool names | **Take**, via `langchain-mcp-adapters`. |
| Plugins, skills, LSP, snapshots/revert, share, client/server | **Drop** or roadmap. |
| Per-model-family prompts | **Drop.** DeepSeek only, one prompt. |
