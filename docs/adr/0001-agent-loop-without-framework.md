\# ADR 0001 — Agent Loop Without a Framework



\- \*\*Status:\*\* Accepted

\- \*\*Date:\*\* 2026-10-04

\- \*\*Context phase:\*\* Phase 5–7

\- \*\*Deciders:\*\* project lead, lead engineer



\## Context



The platform runs an AI agent that decides irrigation, fertigation, and

spraying actions on plots. The agent loop currently:



1\. Builds a `SafetyContext` from the DB

2\. Fetches RAG history, trends, weather, agronomy (enriched context)

3\. Calls Qwen2.5-7B via Ollama

4\. Validates the proposal through `validate\_tool\_call()`

5\. Creates a `Task` row for dispatch



The loop has four tools available:

`control\_irrigation`, `schedule\_fertigation`, `spray\_chemical`, `noop`.



\## Problem



Should we adopt a framework like \*\*LangGraph\*\* (or CrewAI / AutoGen) to

orchestrate the agent, instead of maintaining our own loop?



\## Decision



\*\*No. Keep the plain Python loop.\*\* Revisit this decision when the agent

needs conditional branching, human-in-the-loop interrupts \*inside\*

reasoning, or multi-agent coordination.



\## Rationale



\### The loop is linear, not a graph



Four tools, one model call, no branches, no loops, no retries. A graph

framework's only advantage is expressing non-linear control flow. When

the control flow is a straight line, the graph is overhead.



\### LangGraph adds a "state tax"



Published benchmarks show 68% slower execution and reduced throughput

versus equivalent non-framework code, driven by per-node state

serialization. Our loop is stateless at each step — the DB is the

state store — so we'd pay the tax and gain nothing.



\### We already have the features LangGraph is known for



| LangGraph feature | Our equivalent |

|---|---|

| Checkpointing | Postgres `tasks` table |

| Human-in-the-loop | Task state machine + approval endpoint |

| Durable execution | Task persists across restarts; no in-memory state |

| Audit trail | Hash-chained `audit\_log` |



\### Safety frameworks don't enforce safety



Our `validate\_tool\_call()` is a hard-coded gate with hash-chained audit

and an import-graph CI check (Phase 12). No framework provides this.

Adopting LangGraph would layer another abstraction between our code and

the safety guarantee without adding enforcement capability.



\### Fewer dependencies, fewer CVEs



Recent CVEs against LangGraph's dependencies (SQLite injection,

msgpack deserialization RCE, Redis injection) don't apply to our

plain-Python stack. Fewer dependencies = smaller attack surface.



\### Framework-agnostic by design



`agent\_loop.py` calls our own `decide(ctx, enriched)` interface. The

implementation behind that interface is replaceable in one file. If we

ever need LangGraph, we adopt it \*behind\* that interface — one file

change, not a rewrite.



\## Alternatives considered



| Alternative | Verdict | Why |

|---|---|---|

| \*\*LangGraph\*\* | Rejected (deferred) | Adds state tax for features we don't need |

| \*\*CrewAI\*\* | Rejected | Multi-agent orchestration; overkill for one agent |

| \*\*AutoGen\*\* | Rejected | Conversation-based; our agent isn't conversational yet |

| \*\*Plain Python (current)\*\* | \*\*Accepted\*\* | Simplest thing that could work; nothing to un-learn later |



\## Consequences



\### Positive



\- \*\*Readability.\*\* `agent\_loop.py` is 150 lines; anyone can follow it.

\- \*\*Debuggability.\*\* Stack traces point at our code, not framework internals.

\- \*\*Performance.\*\* No per-step serialization overhead.

\- \*\*Testability.\*\* Every step is a pure function; unit tests are trivial.

\- \*\*No migration risk.\*\* We don't have to remove a framework later if it

&#x20; doesn't fit.



\### Negative



\- \*\*No built-in interrupts.\*\* If we need to pause mid-reasoning for a

&#x20; user response, we'll build it. Not required today.

\- \*\*No built-in graph visualization.\*\* We read the code. Fine for a

&#x20; 150-line function.

\- \*\*Manual retry logic.\*\* Handled per-tool; may grow complex if we add

&#x20; many tools.



\## Revisit triggers



Reopen this decision when any of the following becomes true:



1\. \*\*The agent needs conditional branches\*\* ("try irrigation, check

&#x20;  sensor, if no improvement then fertigate") as a single decision.

2\. \*\*Human-in-the-loop interrupts inside reasoning\*\* are required (chat

&#x20;  layer, Phase 9/10).

3\. \*\*Multi-agent coordination\*\* is needed (specialist agents per

&#x20;  domain).

4\. \*\*Long-running decision sessions\*\* span hours or days (multi-day

&#x20;  pest workflows).



At that point, evaluate LangGraph and alternatives \*against the actual

requirements we have then\*, not the ones we're speculating about now.



\## Notes



\- The chat layer (Phase 9/10) is the most likely first trigger. Chat

&#x20; naturally needs pause-and-resume.

\- Diagnosis (`diagnosis\_service.py`) and dispatch (`dispatch\_service.py`)

&#x20; follow the same pattern: our own service interface, model behind it.

\- This ADR should be revisited at the start of Phase 10.



\## References



\- Agent framework latency benchmark (2026): LangGraph 10,155 ms vs.

&#x20; LangChain 6,046 ms on equivalent agents

\- LangGraph production migration report (2026): Redis checkpoint

&#x20; dependency adds operational load

\- Framework safety analysis (2026): "frameworks delegate safety

&#x20; entirely to implementers"

