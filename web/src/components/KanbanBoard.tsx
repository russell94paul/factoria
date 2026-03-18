"use client";

import { useState } from "react";
import Image from "next/image";
import { EnrichedTicket } from "@/lib/api";
import TicketCard from "./TicketCard";
import CreateTicketModal from "./CreateTicketModal";

const COLUMNS = [
  "DATA_INGESTION",
  "TICKET_INTAKE",
  "DESIGN_REVIEW",
  "PROFILING",
  "BUILD",
  "QA",
  "READY_FOR_REVIEW",
  "PR_CREATION",
  "DONE",
] as const;

const COLUMN_LABELS: Record<string, string> = {
  DATA_INGESTION: "Data Ingestion",
  TICKET_INTAKE: "Intake",
  DESIGN_REVIEW: "Design Review",
  PROFILING: "Profiling",
  BUILD: "Build",
  QA: "QA",
  READY_FOR_REVIEW: "Ready for Review",
  PR_CREATION: "PR Creation",
  DONE: "Done",
};

interface Props {
  tickets: EnrichedTicket[];
  onRefresh: () => void;
}

export default function KanbanBoard({ tickets, onRefresh }: Props) {
  const [showCreate, setShowCreate] = useState(false);

  const byState: Record<string, EnrichedTicket[]> = {};
  for (const col of COLUMNS) byState[col] = [];
  for (const t of tickets) {
    const col = t.current_state;
    if (byState[col]) {
      byState[col].push(t);
    } else {
      byState["TICKET_INTAKE"].push(t);
    }
  }

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: "#1B1030" }}>
      <header className="flex items-center justify-between px-6 py-3 border-b border-purple-900/60" style={{ backgroundColor: "#12091F" }}>
        <div
          className="rounded-lg px-3 py-1.5"
          style={{
            backgroundColor: "#12091F",
            boxShadow: "0 0 12px 4px rgba(139,92,246,0.25), 0 2px 8px rgba(0,0,0,0.6)",
            filter: "drop-shadow(0 0 6px rgba(139,92,246,0.3))",
          }}
        >
          <Image src="/factoria_logo_resized.png" alt="Factoria" width={120} height={32} className="object-contain" />
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-500 font-medium"
        >
          + New Ticket
        </button>
      </header>

      <div className="flex-1 overflow-x-auto">
        <div className="flex gap-4 p-4 h-full" style={{ minWidth: `${COLUMNS.length * 200}px` }}>
          {COLUMNS.map((col) => (
            <div key={col} className="flex-shrink-0 w-48 flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-semibold text-purple-300 uppercase tracking-wide">
                  {COLUMN_LABELS[col]}
                </h2>
                <span className="text-xs text-purple-400 bg-purple-900/40 rounded-full px-2 py-0.5">
                  {byState[col].length}
                </span>
              </div>
              <div className="flex-1 space-y-2">
                {byState[col].map((t) => (
                  <TicketCard key={t.ticket_id} ticket={t} onApproved={onRefresh} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {showCreate && (
        <CreateTicketModal
          onClose={() => setShowCreate(false)}
          onCreated={onRefresh}
        />
      )}
    </div>
  );
}
