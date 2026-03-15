"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  EnrichedTicket,
  WorkflowRun,
  Artifact,
  AgentSession,
  listArtifacts,
  listSessions,
  getWorkflow,
} from "@/lib/api";
import TicketDrawer from "@/components/TicketDrawer";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchTicket(id: string): Promise<EnrichedTicket | null> {
  const res = await fetch(`${API_BASE}/tickets/${id}`);
  if (!res.ok) return null;
  const t = await res.json();
  if (t.error) return null;

  // enrich with live workflow state
  try {
    const wfRes = await fetch(`${API_BASE}/tickets/${id}/workflow`);
    if (wfRes.ok) {
      const wfRef = await wfRes.json();
      if (wfRef.workflow_run_id) {
        const runRes = await fetch(`${API_BASE}/workflows/${wfRef.workflow_run_id}`);
        if (runRes.ok) {
          const run = await runRes.json();
          return {
            ...t,
            current_state: run.current_state,
            workflow_run_id: run.workflow_run_id,
            workflow_status: run.status,
          } as EnrichedTicket;
        }
      }
    }
  } catch {
    // fall through to unenriched
  }

  return { ...t, current_state: t.state, workflow_run_id: null, workflow_status: null };
}

export default function TicketPage() {
  const params = useParams();
  const id = params.id as string;

  const [ticket, setTicket] = useState<EnrichedTicket | null | "loading">("loading");
  const [workflow, setWorkflow] = useState<WorkflowRun | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [sessions, setSessions] = useState<AgentSession[]>([]);

  useEffect(() => {
    if (!id) return;

    fetchTicket(id).then((t) => {
      setTicket(t);
      if (!t?.workflow_run_id) return;

      getWorkflow(t.workflow_run_id)
        .then(setWorkflow)
        .catch(() => {});

      listArtifacts(id)
        .then(setArtifacts)
        .catch(() => {});

      listSessions(t.workflow_run_id)
        .then(setSessions)
        .catch(() => {});
    });
  }, [id]);

  if (ticket === "loading") {
    return (
      <div className="flex items-center justify-center h-screen bg-[#1B1030]">
        <p className="text-purple-300 text-sm">Loading…</p>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#1B1030]">
        <p className="text-purple-300 text-sm">Ticket not found.</p>
      </div>
    );
  }

  return (
    <TicketDrawer
      ticket={ticket}
      workflow={workflow}
      artifacts={artifacts}
      sessions={sessions}
    />
  );
}
