"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { EnrichedTicket, WorkflowRun, Artifact, AgentSession, UploadedFile, DataPreviewResult, listUploads, getDataPreview } from "@/lib/api";
import ArtifactViewer from "./ArtifactViewer";
import AgentTimeline from "./AgentTimeline";

const STATE_COLORS: Record<string, string> = {
  DATA_INGESTION: "bg-cyan-900/60 text-cyan-300",
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
  const [tab, setTab] = useState<"artifacts" | "timeline" | "data">("artifacts");
  const [uploads, setUploads] = useState<UploadedFile[]>([]);
  const [preview, setPreview] = useState<DataPreviewResult | null>(null);
  const [previewTable, setPreviewTable] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    listUploads(ticket.ticket_id).then(setUploads).catch(() => {});
  }, [ticket.ticket_id]);

  async function handlePreview(tableName: string) {
    if (previewTable === tableName) {
      setPreview(null);
      setPreviewTable(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewTable(tableName);
    try {
      const result = await getDataPreview(ticket.ticket_id, tableName);
      setPreview(result);
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }
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
              {(["artifacts", "data", "timeline"] as const).map((t) => (
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
          {tab === "data" && (
            <div className="space-y-4">
              {uploads.length === 0 ? (
                <p className="text-sm text-purple-400 italic">No files uploaded yet.</p>
              ) : (
                <div className="space-y-3">
                  {uploads.map((f) => {
                    const tblName = f.filename.replace(/\.[^.]+$/, "").toUpperCase().replace(/[-\s]/g, "_");
                    return (
                      <div key={f.file_id} className="rounded border border-purple-900/40 p-3" style={{ backgroundColor: "#1B1030" }}>
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-purple-100">{f.filename}</p>
                            <p className="text-xs text-purple-500 mt-0.5">
                              {(f.size_bytes / 1024).toFixed(1)} KB · {f.mime_type ?? "unknown"}
                            </p>
                          </div>
                          {f.schema_json && (
                            <button
                              onClick={() => handlePreview(tblName)}
                              className="text-xs px-2 py-1 rounded text-cyan-300 border border-cyan-800/50 hover:bg-cyan-900/30"
                            >
                              {previewTable === tblName ? "Hide" : "Preview"}
                            </button>
                          )}
                        </div>
                        {f.schema_json && (
                          <div className="mt-2">
                            <p className="text-xs text-purple-400 mb-1">Schema</p>
                            <div className="flex flex-wrap gap-1">
                              {f.schema_json.map((col) => (
                                <span key={col.name} className="text-xs px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-300">
                                  {col.name}: <span className="text-purple-500">{col.type}</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {previewLoading && <p className="text-sm text-purple-400">Loading preview…</p>}
              {preview && !previewLoading && (
                <div className="mt-3">
                  <p className="text-xs text-purple-400 mb-2">Preview: RAW.{preview.table} ({preview.rows.length} rows)</p>
                  <div className="overflow-x-auto">
                    <table className="text-xs w-full border-collapse">
                      <thead>
                        <tr>
                          {preview.columns.map((col) => (
                            <th key={col} className="text-left px-2 py-1 text-purple-300 border-b border-purple-900/40 whitespace-nowrap">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row, i) => (
                          <tr key={i} className={i % 2 === 0 ? "" : "bg-purple-900/10"}>
                            {preview.columns.map((col) => (
                              <td key={col} className="px-2 py-1 text-purple-200 border-b border-purple-900/20 whitespace-nowrap max-w-xs truncate">
                                {String(row[col] ?? "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
