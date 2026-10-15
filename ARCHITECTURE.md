# Architecture

Buildra is a LangGraph `StateGraph` running a ReAct loop:
`agent -> authorize -> tools -> agent`, ending when the model answers without
tool calls.

```
src/buildra/
├── cli/          terminal UI: input loop, rendering, approval prompts, turn driver
├── agent/        the graph: state, runtime context, nodes, routing, system prompt
├── tools/        built-in tools, their registry, output truncation, ignore rules
├── llm/          provider-agnostic model access ("provider/model" ids)
├── config/       settings schema and the TOML/env loader
└── permissions/  workspace sandbox (v0.2: allow/ask/deny rules)
```

Dependencies point downward only:
`cli -> agent -> {tools, llm, permissions, config}`.

The full design (opencode-to-LangGraph mapping, decisions and their reasons,
version plan) is in [docs/architecture.md](docs/architecture.md). The
LangGraph background is in [docs/langgraph-concepts.md](docs/langgraph-concepts.md).
