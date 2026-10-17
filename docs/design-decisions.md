# Design Decisions & Architectural Trade-offs

This document details key architectural decisions, alternatives considered, and trade-offs made in the **Wealth Advisor Multi-Agent System**.

---

## 1. Modular Deterministic Agents vs. Heavy Orchestration Frameworks

### Decision
Implement specialized agents as lightweight, typed Python classes implementing explicit contracts with Pydantic v2 schemas, rather than adopting heavy frameworks like LangChain, CrewAI, or AutoGen.

### Rationale
- **Deterministic Explainability**: Financial advisory systems require rigorous, auditable explanations. Generative LLM agents often suffer from non-deterministic outputs, hallucinated calculations, and high latency.
- **Zero External API Cost & Cloud Independence**: The core engine runs completely offline without requiring paid OpenAI/Anthropic API keys.
- **Microsecond Latency**: The multi-agent pipeline completes in **< 100ms**, compared to 3–15 seconds for multi-turn LLM chains.
- **Testability**: Pure Python classes allow deterministic unit tests with 100% predictability across CI/CD pipelines.

### Trade-offs
- *Drawback*: Natural language free-form conversation requires an LLM interface layer.
- *Mitigation*: The `InsightAgent` generates structured facts, hypotheses, and actions that can easily be fed to a local LLM or client-facing template renderer if conversational chat is desired.

---

## 2. Tool Abstraction via Structural Typing (`typing.Protocol`)

### Decision
Define tools (`CRMToolInterface`, `StorageInterface`) using Python's `@runtime_checkable Protocol` rather than rigid abstract base classes or tightly coupled external SDKs.

### Rationale
- **Decoupling**: Agents depend strictly on protocol signatures, ensuring zero dependency on specific database drivers or network libraries.
- **Testability**: Tests can inject lightweight in-memory adapters, isolated SQLite stores, or mock failure harnesses without monkey-patching.
- **Extensibility**: Illustrated via `HttpCRMAdapter`, demonstrating how a production REST API with authentication and retries drops in with zero modifications to agent code.

---

## 3. Leave-One-Out Baseline for Anomaly Detection

### Decision
In `FinancialRulesEngine._check_category_outliers`, calculate category baseline means using a **leave-one-out** approach where the candidate transaction is excluded from its own baseline mean calculation.

### Rationale
- **Outlier Contamination Avoidance**: When sample sizes are small (e.g., $N = 3$ or $4$), including an extreme outlier in the mean drastically inflates the baseline:
  $$\text{Threshold} = 3 \times \frac{\sum_{i=1}^N x_i}{N}$$
  If $N = 3$, $3 \times \frac{x_1 + x_2 + x_3}{3} = x_1 + x_2 + x_3$. For non-negative values, $x_3 > x_1 + x_2 + x_3$ is mathematically impossible, causing severe false negatives.
- **Mathematical Soundness**: Leave-one-out baseline ($ \text{mean}(x_1, x_2) $) preserves sensitivity while enforcing a minimum sample requirement ($N \ge 3$) to prevent noise.

---

## 4. Partial-Result Fallback (Graceful Degradation) vs. Fail-Closed

### Decision
When noncritical dependencies fail (e.g. CRM timeout or network error), the system transitions to **Partial Result Mode** (`partial_result: true`) rather than returning an HTTP 500 error.

### Rationale
- A wealth advisor evaluating a client's monthly cash flow should not be blocked from viewing transactions simply because the CRM biographical service experienced a temporary network blip.
- The system flags `crm_status: "FAILED"`, records data quality warnings, reduces insight confidence scores, and delivers the transactional findings safely.

---

## 5. In-Memory Session Memory + SQLite Long-Term Persistence

### Decision
Use in-memory `SessionMemoryStore` for active workflow step tracing and a localized SQLite database (`SQLiteMemoryStore`) for long-term storage and human reviews.

### Rationale
- **Zero Infrastructure Overhead**: Eliminates the need for Postgres, Redis, or cloud clusters for local execution and assessment review.
- **ACID Transactions**: SQLite guarantees atomic writes for review audit logs and summary persistence.
- **Strict Client Scoping**: Every SQL query requires an explicit `client_id` parameter, guaranteeing data isolation between clients.
- **Retention Pruning**: Built-in automated pruning cleans records older than a configured threshold (default 90 days).

---

## 6. Observability and PII Sanitization

### Decision
Structured JSON logging with automated in-flight redaction of credit cards (PANs), SSNs, tokens, and credentials.

### Rationale
- Regulatory financial systems must guarantee that cardholder data and credentials never enter centralized log aggregators (Splunk, Datadog).
- Structured JSON output includes `correlation_id`, `agent`, `stage`, and `duration_ms` for end-to-end distributed tracing.
