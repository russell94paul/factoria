"use client";

import { useState } from "react";
import Image from "next/image";
import { EnrichedTicket, WorkflowRun, Artifact, AgentSession } from "@/lib/api";
import ArtifactViewer from "./ArtifactViewer";
import AgentTimeline from "./AgentTimeline";

const STATE_COLORS: Record<string, string> = {
  TICKET_INTAKE: "bg-gray-700 text-gray-200",
  DESIGN_REVIEW: "bg-yellow-900/60 text-yellow-300",
  PROFILING: "bg-blue-900/60 text-blue-300",
  BUILD: "bg-purple-900/60 text-purple-300",
  QA: "bg-orange-900/60 text-orange-300",
  READY_FOR_REVIEW: "bg-yellow-900/60 text-yellow-300",
  PR_CREATION: "bg-teal-900/60 text-teal-300",
  DONE: "bg-green-900/60 text-green-300",
};

interface Props {
  ticket: EnrichedTicket;
  workflow: WorkflowRun | null;
  artifacts: Artifact[];
  sessions: AgentSession[];
}

export default function TicketDrawer({ ticket, workflow, artifacts, sessions }: Props) {
  const [tab, setTab] = useState<"artifacts" | "timeline">("artifacts");
  const state = ticket.current_state;
  const colorClass = STATE_COLORS[state] ?? "bg-gray-700 text-gray-200";

  return (
    <div className="min-h-screen" style={{ backgroundColor: "#1B1030" }}>
      {/* Header */}
      <header className="flex items-center px-6 py-3 border-b border-purple-900/60" style={{ backgroundColor: "#12091F" }}>
        <a href="/">
          <Image src="/factoria_logo_resized.png" alt="Factoria" width={120} height={32} className="object-contain" />
        </a>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8">
        <a href="/" className="text-sm text-purple-400 hover:text-purple-200 mb-4 block">
          ← Back to board
        </a>

        <div className="rounded-lg border border-purple-900/60 p-6" style={{ backgroundColor: "#241740" }}>
          <div className="flex items-start justify-between mb-4">
            <h1 className="text-xl font-semibold text-white">{ticket.title}</h1>
            <span className={`text-xs px-2 py-1 rounded-full font-medium whitespace-nowrap ml-4 ${colorClass}`}>
              {state}
            </span>
          </div>

          {ticket.description && (
            <p className="text-sm text-purple-200 mb-4">{ticket.description}</p>
          )}

          <div className="text-xs text-purple-400 mb-6">
            Created: {new Date(ticket.created_at).toLocaleString()}
            {workflow && (
              <span className="ml-4">
                Status: <span className="font-medium text-purple-200">{workflow.status}</span>
              </span>
            )}
          </div>

          {/* Tabs */}
          <div className="border-b border-purple-900/60 mb-4">
            <nav className="flex gap-4">
              {(["artifacts", "timeline"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`pb-2 text-sm font-medium border-b-2 capitalize ${
                    tab === t
                      ? "border-purple-400 text-purple-300"
                      : "border-transparent text-purple-500 hover:text-purple-300"
                  }`}
                >
                  {t}
                </button>
              ))}
            </nav>
          </div>

          {tab === "artifacts" && <ArtifactViewer artifacts={artifacts} />}
          {tab === "timeline" && (
            <AgentTimeline sessions={sessions} events={workflow?.events ?? []} />
          )}
        </div>
      </div>
    </div>
  );
}
