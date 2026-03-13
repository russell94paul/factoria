
## Overview: agent collaboration philosophy

This platform implements “autonomous data engineering” as a **controlled, artefact-driven workflow** rather than an unconstrained AI assistant. The operating model is designed to be predictable under live demo pressure and defensible under production security review.

### Specialist agents, strict tool allowlists, and deterministic execution

We use a small set of specialist agents (Intake, Design, Profiler, Builder, QA, PR) that each have narrow responsibilities and **strictly limited tool permissions**. Tool exposure is configured per agent, and allow/deny policy is enforced by the runtime (not just prompts). citeturn0search0

Agents must **not invent tools, execution methods, or ad-hoc shell workarounds**. Tool calls must be limited to the platform’s declared JSON-schema tool interfaces. OpenClaw’s agent tool model is explicit: tools can be defined globally or per agent under `agents.list[].tools`, and allowlist/denylist policy controls what a given agent can call. citeturn0search0

### Runner-split security model is non-negotiable

The architecture constraints are enforced as operating rules:

- Agents **never** run shell commands.
- Only the runner executes dbt / Snowflake CLI / git / GitHub CLI.
- Execution chain is always: **Agent → gateway → API Tool → runner Job API → execution**.
- Runner exposes a strict **allowlisted job API** (no arbitrary command execution).
- Snowflake/GitHub secrets live only in runner.

This aligns with OpenClaw’s security guidance: keep access as small as possible, be deliberate about what the agent can touch, and avoid unsafe exposure patterns. citeturn0search1

### Artefact-driven handoffs improve reliability and debugging

The real “collaboration surface” between agents is a set of **well-defined artefacts** (design documents, profiling reports, dbt artefacts, QA summaries). This reduces ambiguity, makes each step replayable, and provides a stable audit trail.

For QA gating specifically, dbt’s `run_results.json` is a canonical execution artefact containing timing and status for each executed node, making it an ideal contract for determining pass/fail and for PR evidence. citeturn0search3

### Human approval checkpoints are explicit control points

Two human gates remain core to the operating model:

- **Design Review gate**: approve the modelling plan before the workflow proceeds into profiling/build actions.
- **Ready for Review gate**: approve PR creation before any external code-write side effect occurs.

## Agent roster

The initial roster retains the baseline agents exactly and includes the tenant provisioning agent required to cover tenant lifecycle states. This does not change architecture; it assigns ownership and permissions clearly.

### Tenant Provisioning Agent

**Purpose**  
Provision tenant environment and bootstrap a minimal “ready to model” workspace.

**Inputs**  
Tenant provisioning ticket; tenant preset; Snowflake tenant identifier; dbt repo location metadata (stored by orchestrator).

**Outputs**  
Tenant provisioning artefacts; tenant state transition to `TENANT_READY`.

**Allowed tools**  
- `snowflake_sql`
- `workspace_write_files` (restricted; see dedicated guardrails section)
- `dbt_build` (smoke scope only; orchestrator-defined selection)
- `publish_artifact`

**Forbidden tools**  
- `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Create tenant schemas/roles/warehouse (idempotent DDL via runner job).
- Write tenant config artefacts into the workspace.
- Run a smoke build that verifies connectivity and basic dbt execution.

### Intake Agent

**Purpose**  
Normalise and validate the data engineering ticket; identify missing requirements; produce clarifying questions.

**Inputs**  
Raw ticket form data; tenant context; optional prior artefacts for the same tenant.

**Outputs**  
`docs/intake_summary.md`; structured “ticket brief”; transition to `NEEDS_INFO` or `DESIGN_REVIEW`.

**Allowed tools**  
- `publish_artifact`

**Forbidden tools**  
- `snowflake_sql`, `dbt_compile`, `dbt_build`, `workspace_write_files`, `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Confirm grain, keys, required outputs, acceptance criteria.
- Ask for missing join keys, incremental strategy, or column definitions.

### Design Agent

**Purpose**  
Create a concrete modelling plan (grain, keys, model list, tests strategy, incremental strategy assumptions).

**Inputs**  
Ticket brief; tenant conventions; prior design patterns.

**Outputs**  
`docs/design.md` (and optionally `outputs/design_spec.json`).

**Allowed tools**  
- `publish_artifact`

**Forbidden tools**  
- `snowflake_sql`, `dbt_compile`, `dbt_build`, `workspace_write_files`, `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Propose staging → intermediate → fact model decomposition.
- Specify required tests and documentation expectations.

### Profiler Agent

**Purpose**  
Profile source schemas and validate assumptions (key candidates, nullability, join integrity, distributions).

**Inputs**  
Approved design artefacts; tenant connection alias; source table references.

**Outputs**  
`outputs/profile_report.json`, `docs/profiling.md`.

**Allowed tools**  
- `snowflake_sql`
- `publish_artifact`

**Forbidden tools**  
- `workspace_write_files`, `dbt_compile`, `dbt_build`, `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Null-rate and distinct-count checks for keys.
- Relationship checks for join assumptions.

### Builder Agent

**Purpose**  
Generate dbt model and test files in the workspace; perform compile-only validation.

**Inputs**  
Design artefacts; profiling artefacts; workspace paths; orchestrator-provided file layout conventions.

**Outputs**  
dbt change files under `dbt_changes/`; `outputs/compile_summary.json`; `docs/build_plan.md` (optional).

**Allowed tools**  
- `workspace_write_files` (restricted; see guardrails section)
- `dbt_compile` (scoped; orchestrator-defined selection)
- `publish_artifact`

**Forbidden tools**  
- `snowflake_sql`, `dbt_build`, `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Create staging models and downstream fact model SQL.
- Create `schema.yml` tests (not_null/unique/relationships/etc).

### QA Agent

**Purpose**  
Run dbt build/test in a constrained scope and produce a QA report rooted in dbt artefacts.

**Inputs**  
Changed files list; compile summary; orchestrator-defined selection set; tenant target.

**Outputs**  
`outputs/run_results.json`, `docs/qa_report.md`.

**Allowed tools**  
- `dbt_build` (scoped selection only)
- `publish_artifact`

**Forbidden tools**  
- `snowflake_sql`, `dbt_compile` (optional), `workspace_write_files`, `git_commit_push`, `gh_create_pr`

**Example tasks**  
- Run build for the impacted models and required tests only.
- Summarise pass/fail from `run_results.json`. citeturn0search3

### PR Agent

**Purpose**  
Create branch, commit, push and open a PR after explicit human approval.

**Inputs**  
QA artefacts; changed files list; approval record; ticket metadata.

**Outputs**  
PR URL + `docs/pr_summary.md`.

**Allowed tools**  
- `git_commit_push`
- `gh_create_pr`
- `publish_artifact`

**Forbidden tools**  
- `snowflake_sql`, `dbt_compile`, `dbt_build`, `workspace_write_files`

**Example tasks**  
- Create branch `autode/<ticket_id>-<slug>`, commit changes, open PR with QA evidence.

## Tooling model, permissions, and control-plane separation

### Agent tool permissions matrix

All tools shown below are **API tool endpoints** that delegate work to runner jobs. Agents never call runner directly.

| Agent | snowflake_sql | dbt_compile | dbt_build | workspace_write_files | git_commit_push | gh_create_pr | publish_artifact |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tenant Provisioning | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Intake | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Design | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Profiler | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Builder | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| QA | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ |
| PR | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |

Security rationale:

- OpenClaw’s tool configuration model supports per-agent tool configuration and allow/deny policies, enabling least-privilege boundaries that are enforced at runtime. citeturn0search0
- These boundaries prevent cross-role escalation (eg Builder cannot push; PR cannot query warehouse).

### Orchestrator-only tools (not agent-callable)

The system requires internal control-plane operations that must **never** be exposed as agent tools. They should be implemented as internal FastAPI functions or private endpoints inaccessible to OpenClaw tool policy.

Examples:

- `transition_state(ticket_id, from_state, to_state, reason, evidence_refs)`
- `approve_gate(ticket_id, gate_name, actor, timestamp, comment)`
- `register_job_result(ticket_id, job_id, result_ref, status)`
- `set_ticket_failed(ticket_id, reason, error_ref, recoverability)`
- `compute_selection_set(ticket_id, design_spec, changed_files, policy)`

Why this matters:

- These operations define the platform’s **determinism and safety**: tickets must not change state because an agent “decided to,” but because the orchestrator verified evidence and applied policy.
- Keeping these out of agent tool control reduces the blast radius of prompt injection and prevents “agent self-approval” of gates and state transitions. This aligns with the “be deliberate about what the bot can touch” guidance in OpenClaw security documentation. citeturn0search1

### Guardrails for workspace_write_files

`workspace_write_files` is a **high-risk tool** because it can materially change code and artefacts and, in a runner environment, could be abused to attempt to write into sensitive paths if not strictly constrained.

The following rules must be enforced by **both**:
1) API tool endpoint validation (defence-in-depth), and  
2) runner job implementation (authoritative enforcement).

#### Path allowlist (base directories)

All file writes must be confined to the ticket workspace root and only under these allowed subpaths:

- `.../docs/`
- `.../outputs/`
- `.../logs/`
- `.../dbt_changes/`

The workspace root is derived from `(tenant_id, ticket_id)` and resolved in runner under `WORKSPACES_ROOT`. The tool must reject any path outside that resolved root.

#### Explicit denials

The tool must deny:

- Any `..` traversal or path normalisation that escapes the workspace root.
- Any attempt to write into `.git/` (or create/modify git internals).
- Any attempt to write into `/run/secrets/` or any other runtime secret mount path.
- Any absolute path write (must be relative to workspace root).
- Symlink escape: resolve symlinks and re-check that the final path remains under workspace root.

#### File type allowlist

Only allow these extensions (case-insensitive):

- `.sql`
- `.yml`, `.yaml`
- `.md`
- `.json`

Optionally allow `.csv` only for explicitly approved demo data export jobs, never for model generation by default.

#### Size and count limits

Recommended safe defaults (tune per demo needs):

- Max files per request: **50**
- Max size per file: **256 KB**
- Max total payload per request: **2 MB**

Any larger artefacts (eg dbt docs site) should be produced by dedicated runner jobs (eg `dbt_docs_generate`) rather than being pushed through `workspace_write_files`.

#### Checksums (recommended)

Require each file payload to include a checksum and return an authoritative checksum after write:

- Request: `{ path, content, sha256 }`
- Response: `{ path, bytes_written, sha256, last_modified }`

This enables:
- Integrity verification (no silent truncation),
- Better audit logs,
- Easier UI diff previews.

#### Why these guardrails preserve the runner-split model

The runner-split architecture intentionally centralises execution and secrets in runner; that makes **filesystem write controls** a primary security boundary. Tight path and extension allowlists prevent an agent-driven write from becoming a general-purpose mechanism to tamper with git internals, overwrite secrets, or escape the workspace boundary.

### Deterministic dbt selection sets (Orchestrator-owned)

The orchestrator must compute and enforce the final dbt selection scope for `dbt_compile` and `dbt_build`.

#### Ownership rule

- Agents may **recommend** selection scopes in artefacts (eg Design or QA notes).
- The orchestrator computes the definitive `--select` argument based on:
  - approved design spec,
  - changed file detection,
  - dependency expansion policy.

This is essential because dbt’s node selection syntax and graph operators can significantly broaden scope (eg `+` expands to ancestors/descendants). citeturn0search2turn0search22

#### QA must never run unconstrained builds

QA must not run `dbt build` without `--select` constraints. Unconstrained builds are:

- slow and noisy (demo risk),
- excessive (production risk),
- reduce signal when diagnosing failures.

dbt explicitly supports selecting only specific resources for an invocation using node selection syntax, and supports combining selector methods. citeturn0search2turn0search10

#### Example selection strategies (policy-driven)

Pick one policy and implement it consistently:

- **Changed model + downstream**: select changed models plus their immediate or full downstream dependencies using graph operators (eg `model+` for descendants, or `+model` for ancestors depending on what you need). citeturn0search22  
- **Tag-based**: enforce tags like `tag:ticket_0001` or `tag:autode` and select `tag:ticket_0001`. Node selection methods support tag selectors and combining selectors. citeturn0search10  
- **Path-based**: select file subpaths such as `models/gold/*` combined with tags for tighter scoping. citeturn0search10  

Operational guidance:

- Orchestrator stores the computed selection string as an artefact (eg `outputs/selection_set.json`) so runs are reproducible.
- QA’s tool call includes the orchestrator-supplied selection string; if an agent attempts to override it, the API tool endpoint ignores it and applies policy.

## Artefact contracts and workspace layout

Artefact-driven handoffs are mandatory: each state’s exit conditions are defined in terms of artefact presence and validation.

### Workspace layout

```text
workspaces/
  tenants/
    <tenant_id>/
      tickets/
        <ticket_id>/
          docs/
          outputs/
          logs/
          dbt_changes/
```

### Required artefact contracts

| Artefact name | Produced by | Consumed by | Format | Location |
|---|---|---|---|---|
| `docs/intake_summary.md` | Intake | Design, Human | Markdown | `.../docs/intake_summary.md` |
| `docs/design.md` | Design | Profiler, Builder, Human | Markdown | `.../docs/design.md` |
| `outputs/profile_report.json` | Profiler | Builder, QA | JSON | `.../outputs/profile_report.json` |
| `docs/profiling.md` | Profiler | Builder, Human | Markdown | `.../docs/profiling.md` |
| `dbt_changes/models/**` | Builder | QA, PR | SQL | `.../dbt_changes/models/` |
| `dbt_changes/tests/schema.yml` | Builder | QA, PR | YAML | `.../dbt_changes/tests/schema.yml` |
| `outputs/compile_summary.json` | Builder | QA | JSON | `.../outputs/compile_summary.json` |
| `outputs/run_results.json` | QA | PR, Human, Orchestrator | JSON | `.../outputs/run_results.json` |
| `docs/qa_report.md` | QA | PR, Human | Markdown | `.../docs/qa_report.md` |
| `docs/pr_summary.md` | PR | Human | Markdown | `.../docs/pr_summary.md` |

Why this is robust:

- dbt documents `run_results.json` as containing timing and status for each executed node in a completed invocation. citeturn0search3  
- Artefacts allow replay and inspection without relying on agent conversational memory, making agent termination and retries safer.

## Collaboration model and diagrams

### Collaboration model clarifications

- The collaboration diagram below is a **system-level view** showing the end-to-end toolchain and execution boundaries.
- **Gateway tool calls are invoked only by the currently active agent session** in that workflow step.
- **Per-agent allowlists are enforced**; the presence of a tool in the system diagram does not imply any agent can call it. Tool configuration supports per-agent tool lists with allow/deny policy. citeturn0search0
- The orchestrator is the sole component allowed to:
  - trigger state transitions,
  - enforce gate approvals,
  - compute selection sets,
  - invoke runner jobs.

OpenClaw’s security guidance reinforces the need to be deliberate about what an agent can touch and to start with the smallest access that still works, widening only with experience. citeturn0search1

### High-level agent collaboration diagram

```mermaid
flowchart TD
  U[User] -->|Ticket created| API[api orchestrator]
  API -->|spawn active agent| GW[gateway OpenClaw]
  GW -->|tool call (allowed for that agent only)| API

  API -->|POST /run (allowlisted jobs)| RUN[runner job API]
  RUN -->|exec Only here: dbt/snow/git/gh| EXT[(Snowflake / Git provider)]
  RUN -->|write logs + artefacts| WS[(workspaces)]
  API -->|read artefacts (ro) + stream events| WEB[web UI]

  subgraph Agents["Agents (specialists; per-agent allowlists enforced)"]
    IA[Intake] --> DA[Design]
    DA -->|Human gate: approve design| PA[Profiler]
    PA --> BA[Builder]
    BA --> QA[QA]
    QA -->|Human gate: approve PR creation| PRA[PR Agent]
  end
```

ASCII fallback:

```text
Intake -> Design -> (Human approves) -> Profiler -> Builder -> QA -> (Human approves) -> PR Agent
   Active agent (via gateway) -> calls only its allowlisted tools -> api -> runner jobs -> workspaces -> api -> web UI
```

## Workflow state mappings

This table fixes the PR approval gate ownership and makes PR execution explicit and implementable.

### State ownership and exit conditions

| Workflow state | Owned by | Exit condition | Human approval required |
|---|---|---|---|
| `TENANT_CREATION_REQUESTED` | Orchestrator | Provisioning workflow run created | No |
| `TENANT_PROVISIONING_RUNNING` | Tenant Provisioning Agent | Tenant provision artefacts created + runner jobs succeeded | No |
| `TENANT_READY` | Orchestrator | Tenant marked ready in state store | No |
| `TICKET_INTAKE` | Intake Agent | `docs/intake_summary.md` published + ticket brief validated | No |
| `NEEDS_INFO` | Orchestrator / Human | Missing fields supplied and validated | Yes (user input) |
| `DESIGN_REVIEW` | Orchestrator / Human | `docs/design.md` published and reviewed | Yes (Approve design) |
| `PROFILING` | Profiler Agent | `outputs/profile_report.json` + `docs/profiling.md` published | No |
| `BUILD` | Builder Agent | dbt files written + `outputs/compile_summary.json` published | No |
| `QA` | QA Agent | `outputs/run_results.json` + `docs/qa_report.md` published | No |
| `READY_FOR_REVIEW` | Orchestrator / Human | QA passed + review gate approved or rejected | Yes (Approve PR creation) |
| `PR_CREATION` | PR Agent | Branch pushed + PR URL stored + `docs/pr_summary.md` published | No |
| `DONE` | Orchestrator | Final state recorded with PR URL | No |
| `FAILED` | Orchestrator | Failure recorded + recovery action chosen | Yes (operator decision) |

Practical notes:

- `READY_FOR_REVIEW` is a **gate state**: no agent should perform PR side-effects until the gate is approved.
- `PR_CREATION` is the explicit post-approval execution state owned by PR Agent.

## Agent spawn/termination and retry policy

### Spawn rules

Agents are spawned deterministically on state entry:

- Enter `TICKET_INTAKE` → spawn Intake session.
- On successful Intake → enter `DESIGN_REVIEW` → spawn Design session (or reuse prior Design session if re-entering).
- After Design artefact published, orchestrator waits for human approval; once approved, transition to `PROFILING` and spawn Profiler.
- `READY_FOR_REVIEW` is owned by orchestrator/human; **no PR agent spawn occurs here**.
- On approval of PR creation gate, orchestrator transitions to `PR_CREATION` and spawns PR Agent.

### Termination rules

An agent run terminates when:

- The required artefact(s) for its state have been published and validated by orchestrator.
- The state exit condition is satisfied and recorded.
- A time/token budget is exceeded (agent run fails with partial artefacts preserved).

### Retry rules

Keep retries conservative and side-effect-safe:

- `dbt_compile` failure:
  - retry once if transient;
  - if deterministic compile errors persist, return to `BUILD` with error excerpt artefact and request updated SQL.
- `dbt_build` failure:
  - retry once (transient); then return to `BUILD` with failing nodes list and logs.
- `git_commit_push` / `gh_create_pr` failures during `PR_CREATION`:
  - retry once;
  - if still failing, remain in `PR_CREATION` with a failure artefact and require operator decision (do not regress state automatically if partial external side effects already occurred).

## Security guardrails, privilege separation, and scope notes

### Runner-only execution and secret locality

- Runner is the only execution boundary for dbt / Snowflake CLI / git / GitHub CLI.
- Snowflake/GitHub secrets are present only in runner.
- API must authenticate to runner job API (bearer token), and runner must reject unknown job types (strict allowlist).

This aligns with the “smallest access that still works” guidance for agent/tool systems and avoids expanding the action surface of agents or gateway. citeturn0search1

### Per-agent tool allowlists are required

Per-agent allow/deny is not optional: OpenClaw’s tool configuration model supports scoping tools per agent and enforcing allow/deny policy. citeturn0search0

### No Docker socket mounting

No service mounts `/var/run/docker.sock`. This prevents container-to-host privilege escalation and keeps runner jobs as the sole privileged mechanism.

### Tenant provisioning privilege separation note

Tenant provisioning often requires elevated warehouse permissions (creating databases/schemas/roles/warehouses) compared with normal modelling tickets (reading sources and building models). Recommended approach:

- Use separate Snowflake credentials/roles for:
  - provisioning (`PROVISIONER_ROLE`), and
  - modelling/QA (`MODELLER_ROLE`).
- Store both sets only in runner.
- Ensure provisioning credentials are used only for provisioning job types, not for normal tickets.

Even if local dev uses a single credential set, the operating model should retain the separation concept so production hardening is straightforward.

### External APIs (eg Windsor API) consistency note

External API integrations are **optional** for the baseline operating model. If enabled:

- Treat the API as an external dependency accessed only via runner allowlisted jobs (eg `windsor_fetch`) with secrets only in runner.
- Do not expose external API credentials to gateway or agents.
- Keep the core agent roster and tool matrix unchanged; add the new capability as a runner job plus a tightly scoped API tool if and only if needed.

## Example end-to-end agent collaboration

This walkthrough reflects the corrected `READY_FOR_REVIEW` ownership and the explicit `PR_CREATION` state.

### Ticket

User request:

> Create `fct_daily_orders` from `RAW.ORDERS` and `RAW.CUSTOMERS`, grain = day. Include `daily_revenue` and `order_count` by `customer_segment`. Add tests and open a PR.

Assume:

- `tenant_id = tenant_retail_001`
- `ticket_id = ticket_0001`

### Intake Agent (`TICKET_INTAKE`)

**Produces**
- `docs/intake_summary.md` with:
  - interpreted sources and outputs,
  - clarifying questions (if any),
  - acceptance criteria rewrite.

**Tool calls**
- `publish_artifact`

If join key or date field unclear → orchestrator transitions to `NEEDS_INFO` and waits for user input.

### Design Agent (`DESIGN_REVIEW`)

**Produces**
- `docs/design.md` that specifies:
  - grain and keys,
  - models to create,
  - test plan,
  - incremental strategy assumptions.

**Tool calls**
- `publish_artifact`

**Human gate**
- user approves design → orchestrator transitions to `PROFILING`.

### Profiler Agent (`PROFILING`)

**Tool calls**
- `snowflake_sql` (API delegates to runner)
- `publish_artifact`

**Produces**
- `outputs/profile_report.json` (null rates, distinct counts, join integrity stats)
- `docs/profiling.md` (human-readable summary)

### Builder Agent (`BUILD`)

**Tool calls**
- `workspace_write_files` (restricted: only within `dbt_changes/`, etc; extension allowlist; size limits)
- `dbt_compile` with orchestrator-computed selection set (scoped)
- `publish_artifact`

**Produces**
- `dbt_changes/models/...`
- `dbt_changes/tests/schema.yml`
- `outputs/compile_summary.json`

### QA Agent (`QA`)

**Tool calls**
- `dbt_build` with orchestrator-computed `--select` scope (never unconstrained)
- `publish_artifact`

**Produces**
- `outputs/run_results.json`
- `docs/qa_report.md`

dbt documents `run_results.json` as containing status and timing for each executed node, making it appropriate evidence and gating input. citeturn0search3

If QA fails → orchestrator transitions back to `BUILD` with failure artefacts.

### Ready for Review gate (`READY_FOR_REVIEW`)

Owned by orchestrator/human. The UI shows:

- QA summary (from `qa_report.md`)
- selection set used
- file list changed

User clicks “Approve PR creation”.

### PR Agent (`PR_CREATION`)

Spawned only after approval.

**Tool calls**
- `git_commit_push`
- `gh_create_pr`
- `publish_artifact`

**Produces**
- `docs/pr_summary.md` including:
  - branch name,
  - PR URL,
  - files changed,
  - QA evidence references.

### Done (`DONE`)

Orchestrator records terminal success state with PR URL and evidentiary artefacts preserved in the workspace.