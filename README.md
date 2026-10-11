# Buildra

An open-source coding agent for your terminal, built with
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) and
[DeepSeek](https://api-docs.deepseek.com). Inspired by Claude Code, Codex CLI,
Cursor and [opencode](https://github.com/anomalyco/opencode).

> **Status: pre-release (Day 1).** Nothing runs end to end yet. The first
> usable version is v0.1. See the [roadmap](#roadmap).

Buildra is also a learning project: every design decision is written down.
Start with:

- [docs/architecture.md](docs/architecture.md): how Buildra is built and why
- [docs/langgraph-concepts.md](docs/langgraph-concepts.md): the LangGraph
  features it uses
- [docs/opencode-analysis.md](docs/opencode-analysis.md): what we learned from
  opencode

## Roadmap

| Version | Theme | Highlights |
|---|---|---|
| v0.1 | Core loop | streaming chat, ReAct graph, file / search / shell tools |
| v0.2 | Safe and stateful | allow / ask / deny permissions, resumable sessions, context compaction, todos, plan mode |
| v0.3 | Extensible | AGENTS.md, subagents, MCP tools, slash commands |

## License

[MIT](LICENSE)
