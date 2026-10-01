# VektorFlow #6 — Control, Safety, Isolation & Observability

VektorFlow borrows architectural patterns from the referenced projects rather than
copying their implementations.

## 1. Policy-as-code — OPA

Use Open Policy Agent as an optional external policy decision point. OPA separates
policy decisions from enforcement and evaluates structured request input against
Rego policies. citeturn0search6turn0search0

VektorFlow integration point: `security_control_plane.opa_decide()`.

Recommended policy inputs include:

- agent identity
- mission/task identity
- requested tool
- target resource
- risk level
- approval state
- tenant/store
- budget state
- sandbox requirement

Default behavior remains the native VektorFlow policy engine. For deployments that
require external policy enforcement, configure `VF_OPA_URL`; high-risk policy can
be configured fail-closed.

## 2. Fine-grained authorization — OpenFGA

OpenFGA provides relationship-based authorization and can model permissions over
users, agents, organizations, stores, missions, tools and resources. citeturn0search4turn0search7

VektorFlow integration point: `security_control_plane.openfga_check()`.

Example conceptual relationships:

```
user:wallace -> owner -> store:vektorflow
agent:Rook -> operator -> store:vektorflow
agent:DaVinci -> editor -> product:123
agent:Aegis -> security_admin -> credentials:store-1
agent:Scout -> viewer -> research:trend-report
```

OpenFGA should answer "is this principal allowed to access this object?" while OPA
answers broader contextual policy questions such as "is this action allowed right
now under this mission/risk/budget policy?"

## 3. Guardrail boundary — OpenGuardrails / Llama Guard

OpenGuardrails defines a vendor-neutral safety/security protocol with events,
verdicts, provenance, correlation and composition. citeturn0search9turn0search15

VektorFlow integration point: `security_control_plane.guardrail_verdict()`.

The guardrail layer belongs before tool execution and before sensitive model output
is committed to an external system.

Llama Guard 3 8B should be treated as an optional detector/model behind this
boundary, not as a mandatory dependency of the core API. This keeps the production
runtime from requiring an 8B safety model on every deployment.

## 4. Durable execution — Temporal

Temporal's durable-execution model is the pattern to borrow for long-running
missions: workflow state survives worker/process failures, and activities can be
retried without rebuilding the entire application workflow. citeturn0search1turn0search2

VektorFlow already has:

- workflow state machines
- dependency DAGs
- retries
- checkpoints
- pause/resume/cancel
- human signals
- mission approval states

`durable_workflow.py` is the provider-neutral compatibility layer. Temporal can
be introduced as the external durable execution provider when mission volume or
failure requirements justify it; it does not replace Mission Control.

## 5. Execution isolation — OpenSandbox / gVisor / Firecracker

The security boundary for untrusted agent code must be separate from the main
VektorFlow process.

gVisor provides an application-kernel isolation layer and OCI runtime through
`runsc`. citeturn1search3turn1search7

Firecracker provides lightweight microVM isolation; its security depends on a
properly configured Linux host. citeturn0search20

VektorFlow's existing `execution_sandbox.py` already uses disposable containers,
no network, read-only filesystem, resource limits and no host filesystem mounts.
The new control-plane adapter exposes a future backend selection:

`docker | gvisor | firecracker | opensandbox`

Only the existing Docker path is enabled by the current implementation. The other
values are architecture targets, not falsely claimed integrations.

## 6. Observability — OpenTelemetry + Grafana Loki

OpenTelemetry is the instrumentation boundary for correlated traces, metrics and
logs. Grafana Loki is the log aggregation/query layer; Loki indexes stream labels
rather than the full log contents and integrates with Grafana for exploration and
alerting. citeturn1search0turn1search1

VektorFlow now has a common correlation context containing:

- trace ID
- mission ID
- task ID
- workflow ID
- agent
- timestamp

This is exposed through `security_control_plane.telemetry_context()`.

## Control-plane decision order

The intended execution path is:

```
Mission
  ↓
Workflow / Task
  ↓
OpenFGA relationship check
  ↓
OPA contextual policy
  ↓
Native VektorFlow risk + approval policy
  ↓
Guardrail verdict
  ↓
Sandbox requirement / isolated execution
  ↓
Tool execution
  ↓
OpenTelemetry correlation
  ↓
Loki / audit trail
  ↓
Postgres authoritative memory
```

This keeps the responsibilities separated:

- Mission Control decides what VektorFlow is trying to accomplish.
- Workflow execution determines what is ready and how it resumes.
- OpenFGA determines relationship/resource authorization.
- OPA determines contextual policy.
- Human approval remains authoritative where required.
- Guardrails inspect safety/security conditions.
- Sandbox isolation contains untrusted execution.
- OpenTelemetry/Loki provide operational evidence.
- Postgres remains the authoritative runtime memory path.

## 7. AI observability — Langfuse + Arize Phoenix

Langfuse and Arize Phoenix sit behind the OpenTelemetry boundary rather than inside
the agents themselves. Langfuse accepts OTLP traces and provides LLM/agent-oriented
observability; Phoenix accepts OTLP traces for AI tracing, debugging and evaluation.
This lets VektorFlow emit one trace graph and optionally send it to either or both
backends. citeturn0search2turn1search0

VektorFlow integration points:

- `ai_observability.py` — provider-neutral OpenTelemetry setup.
- `vektorflow.llm` — one span around each LLM request.
- `vektorflow.agent.run` — one span around each agent execution.
- `vektorflow.tool` — one span around each agent tool execution.
- `vektorflow.mission` — one span around mission execution.
- `GET /api/observability` — reports configured backends without exposing credentials.

Configuration is intentionally opt-in:

```
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com

PHOENIX_COLLECTOR_ENDPOINT=
PHOENIX_API_KEY=
PHOENIX_PROJECT_NAME=vektorflow-15xr

VF_OTEL_SERVICE_NAME=vektorflow-15xr
VF_OTEL_SAMPLE_RATIO=1.0
```

No credentials are stored in source control. If neither provider is configured,
VektorFlow continues to run with a no-op telemetry path. If both are configured,
the same OpenTelemetry spans are exported to both.

Trace correlation uses the control-plane fields already established in this
architecture: mission ID, task ID, workflow ID, agent, and trace ID. This keeps
Langfuse/Phoenix traces aligned with Mission Control, tool execution, security
decisions, and Postgres runtime memory.

Langfuse's current documentation recommends its OpenTelemetry-native SDKs for
Python/JS and also supports direct OTLP ingestion; Phoenix similarly exposes an
OTLP trace collector. citeturn0search4turn0search2turn1search6

## Important boundary

These components are complementary, not interchangeable.

OPA is not the workflow engine.
OpenFGA is not the mission planner.
Temporal is not the policy engine.
Guardrails are not authorization.
gVisor/Firecracker are not approval systems.
Loki is not the source of truth for application state.

That separation is intentional.
