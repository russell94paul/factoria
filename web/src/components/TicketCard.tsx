"use client";

import { useRouter } from "next/navigation";
import { EnrichedTicket, approveGate } from "@/lib/api";

const GATE_STATES = new Set(["DESIGN_REVIEW", "READY_FOR_REVIEW"]);

const STATE_COLORS: Record<string, string> = {
  DATA_INGESTION: "bg-cyan-900/50 text-cyan-300",
  TICKET_INTAKE: "bg-slate-700/50 text-slate-300",
  DESIGN_REVIEW: "bg-yellow-900/50 text-yellow-300",
  PROFILING: "bg-blue-900/50 text-blue-300",
  BUILD: "bg-violet-900/50 text-violet-300",
  QA: "bg-orange-900/50 text-orange-300",
  READY_FOR_REVIEW: "bg-yellow-900/50 text-yellow-300",
  PR_CREATION: "bg-teal-900/50 text-teal-300",
  DONE: "bg-green-900/50 text-green-300",
};

function elapsed(createdAt: string): string {
  const diff = Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h`;
}

interface Props {
  ticket: EnrichedTicket;
  onApproved: () => void;
}

export default function TicketCard({ ticket, onApproved }: Props) {
  const router = useRouter();
  const state = ticket.current_state;
  const colorClass = STATE_COLORS[state] ?? "bg-slate-700/50 text-slate-300";
  const isGate = GATE_STATES.has(state) && ticket.workflow_run_id;

  async function handleApprove(e: React.MouseEvent) {
    e.stopPropagation();
    if (!ticket.workflow_run_id) return;
    try {
      await approveGate(ticket.workflow_run_id, state);
      onApproved();
    } catch {
      // ignore; next poll will refresh
    }
  }

  return (
    <div
      onClick={() => router.push(`/tickets/${ticket.ticket_id}`)}
      className="rounded-lg p-3 cursor-pointer transition-all"
      style={{
        backgroundColor: "#241740",
        border: "1px solid rgba(139,92,246,0.25)",
        boxShadow: "0 0 0 0 rgba(139,92,246,0)",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.border = "1px solid rgba(139,92,246,0.6)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 0 10px 1px rgba(139,92,246,0.2)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.border = "1px solid rgba(139,92,246,0.25)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 0 0 0 rgba(139,92,246,0)";
      }}
    >
      <p className="text-sm font-medium text-purple-100 line-clamp-2 mb-2">{ticket.title}</p>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colorClass}`}>
          {state}
        </span>
        <span className="text-xs text-purple-500">{elapsed(ticket.created_at)}</span>
      </div>
      {isGate && (
        <button
          onClick={handleApprove}
          className="mt-2 w-full text-xs rounded px-2 py-1 font-medium text-yellow-200 transition-colors"
          style={{
            backgroundColor: "rgba(161,98,7,0.35)",
            border: "1px solid rgba(234,179,8,0.4)",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.backgroundColor = "rgba(161,98,7,0.55)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.backgroundColor = "rgba(161,98,7,0.35)";
          }}
        >
          Approve →
        </button>
      )}
    </div>
  );
}
