const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface EnrichedTicket {
  ticket_id: string;
  title: string;
  description: string | null;
  ticket_kind: string;
  state: string;
  created_at: string;
  current_state: string;
  workflow_run_id: string | null;
  workflow_status: string | null;
}

export interface WorkflowEvent {
  event_id: string;
  workflow_run_id: string;
  seq: number;
  event_type: string;
  from_state: string | null;
  to_state: string | null;
  message: string | null;
  payload_json: string | null;
  created_at: string;
}

export interface WorkflowRun {
  workflow_run_id: string;
  ticket_id: string;
  status: string;
  current_state: string;
  started_at: string;
  finished_at: string | null;
  events: WorkflowEvent[];
}

export interface Artifact {
  artifact_id: string;
  workflow_run_id: string;
  ticket_id: string;
  artifact_role: string;
  artifact_type: string;
  file_path: string;
  created_at: string;
}

export interface AgentSession {
  agent_session_id: string;
  workflow_run_id: string;
  ticket_id: string | null;
  agent_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function listTickets(): Promise<EnrichedTicket[]> {
  return apiFetch("/tickets");
}

export function createTicket(body: {
  title: string;
  description: string;
  ticket_kind: string;
}): Promise<{ ticket_id: string; workflow_run_id: string; state: string }> {
  return apiFetch("/tickets", { method: "POST", body: JSON.stringify(body) });
}

export function getWorkflow(id: string): Promise<WorkflowRun> {
  return apiFetch(`/workflows/${id}`);
}

export function approveGate(
  workflowRunId: string,
  gate: string
): Promise<{ state: string }> {
  return apiFetch(`/workflows/${workflowRunId}/gates/${gate}/approve`, {
    method: "POST",
  });
}

export function listArtifacts(ticketId: string): Promise<Artifact[]> {
  return apiFetch(`/artifacts/tickets/${ticketId}`);
}

export async function getArtifactContent(artifactId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/content`);
  if (!res.ok) throw new Error(`Failed to load artifact content: ${res.status}`);
  return res.text();
}

export function listSessions(workflowRunId: string): Promise<AgentSession[]> {
  return apiFetch(`/workflows/${workflowRunId}/sessions`);
}
