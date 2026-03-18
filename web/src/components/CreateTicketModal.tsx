"use client";

import { useEffect, useRef, useState } from "react";
import { createTicket, getDataPreview, listUploads, uploadFile } from "@/lib/api";
import type { DataPreviewResult, UploadedFile } from "@/lib/api";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

/** Derive the DuckDB table name from an uploaded filename.
 *  Mirrors runner logic: safe_stem then strip RAW_ prefix.
 *  e.g. raw_orders.csv → ORDERS */
function fileToTableName(filename: string): string {
  let stem = filename.replace(/\.[^.]+$/, "").toUpperCase().replace(/[-\s]/g, "_");
  stem = stem.replace(/[^A-Z0-9_]/g, "_");
  if (stem.startsWith("RAW_")) stem = stem.slice(4);
  if (/^\d/.test(stem)) stem = `T_${stem}`;
  return stem || "UNKNOWN";
}

type PreviewState = DataPreviewResult | "loading" | "error" | null;

export default function CreateTicketModal({ onClose, onCreated }: Props) {
  // ── form fields ────────────────────────────────────────────────────────────
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [grain, setGrain] = useState("");
  const [metrics, setMetrics] = useState("");
  const [constraints, setConstraints] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  // ── submission ──────────────────────────────────────────────────────────────
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── preview phase ───────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<"form" | "previewing">("form");
  const [ticketId, setTicketId] = useState<string | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [openPanels, setOpenPanels] = useState<Set<string>>(new Set());
  const [previews, setPreviews] = useState<Record<string, PreviewState>>({});
  const [schemaRefreshing, setSchemaRefreshing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-refresh schemas once after 4 s (DATA_INGESTION runs async)
  useEffect(() => {
    if (phase !== "previewing" || !ticketId) return;
    const timer = setTimeout(async () => {
      try {
        const fresh = await listUploads(ticketId);
        setUploadedFiles(fresh);
      } catch {
        // silent
      }
    }, 4000);
    return () => clearTimeout(timer);
  }, [phase, ticketId]);

  // ── file helpers ────────────────────────────────────────────────────────────
  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const allowed = [".csv", ".parquet", ".json", ".jsonl"];
    const valid = Array.from(incoming).filter((f) =>
      allowed.some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...valid.filter((f) => !names.has(f.name))];
    });
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }

  // ── submit ──────────────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    setError(null);

    try {
      const metricsArr = metrics.trim()
        ? metrics.split("\n").map((s) => s.trim()).filter(Boolean)
        : undefined;
      const constraintsArr = constraints.trim()
        ? constraints.split("\n").map((s) => s.trim()).filter(Boolean)
        : undefined;

      const result = await createTicket({
        title,
        description,
        ticket_kind: "DATA_ENGINEERING",
        grain: grain.trim() || undefined,
        metrics: metricsArr,
        constraints: constraintsArr,
      });

      const collected: UploadedFile[] = [];
      if (files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          setUploadProgress(`Uploading ${files[i].name} (${i + 1}/${files.length})…`);
          const uf = await uploadFile(result.ticket_id, files[i]);
          collected.push(uf);
        }
        setUploadProgress(null);
      }

      setTicketId(result.ticket_id);
      setUploadedFiles(collected);
      onCreated(); // refresh board in background

      if (collected.length > 0) {
        setPhase("previewing");
        setSubmitting(false);
      } else {
        onClose();
      }
    } catch (err) {
      setError(String(err));
      setSubmitting(false);
      setUploadProgress(null);
    }
  }

  // ── preview panel helpers ───────────────────────────────────────────────────
  function togglePanel(tableName: string) {
    setOpenPanels((prev) => {
      const next = new Set(prev);
      if (next.has(tableName)) {
        next.delete(tableName);
      } else {
        next.add(tableName);
        // Lazy-load preview on first open
        if (!previews[tableName]) {
          loadPreview(tableName);
        }
      }
      return next;
    });
  }

  async function loadPreview(tableName: string) {
    if (!ticketId) return;
    setPreviews((prev) => ({ ...prev, [tableName]: "loading" }));
    try {
      const data = await getDataPreview(ticketId, tableName);
      setPreviews((prev) => ({ ...prev, [tableName]: data }));
    } catch {
      setPreviews((prev) => ({ ...prev, [tableName]: "error" }));
    }
  }

  async function handleRefreshSchemas() {
    if (!ticketId) return;
    setSchemaRefreshing(true);
    try {
      const fresh = await listUploads(ticketId);
      setUploadedFiles(fresh);
      // Re-load any open previews that previously errored
      Array.from(openPanels).forEach((tableName) => {
        if (previews[tableName] === "error") {
          loadPreview(tableName);
        }
      });
    } finally {
      setSchemaRefreshing(false);
    }
  }

  // ── styles ──────────────────────────────────────────────────────────────────
  const inputClass =
    "w-full rounded px-3 py-2 text-sm text-purple-100 placeholder-purple-600 focus:outline-none focus:ring-1 focus:ring-purple-500";
  const inputStyle = {
    backgroundColor: "#12091F",
    border: "1px solid rgba(139,92,246,0.3)",
  };
  const labelClass = "block text-xs font-medium text-purple-400 mb-1";

  // ── render: preview phase ───────────────────────────────────────────────────
  if (phase === "previewing") {
    return (
      <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
        <div
          className="rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
          style={{ backgroundColor: "#241740", border: "1px solid rgba(139,92,246,0.4)" }}
        >
          {/* Header */}
          <div
            className="px-6 py-4 border-b flex items-center justify-between"
            style={{ borderColor: "rgba(139,92,246,0.3)" }}
          >
            <div>
              <h2 className="text-base font-semibold text-white">Ticket Created</h2>
              <p className="text-xs text-purple-400 mt-0.5">
                {uploadedFiles.length} file{uploadedFiles.length !== 1 ? "s" : ""} uploaded — schema inferred during ingestion
              </p>
            </div>
            <button
              onClick={handleRefreshSchemas}
              disabled={schemaRefreshing}
              className="text-xs text-purple-400 hover:text-purple-200 disabled:opacity-50 px-2 py-1 rounded"
              style={{ border: "1px solid rgba(139,92,246,0.3)" }}
            >
              {schemaRefreshing ? "Refreshing…" : "Refresh schemas"}
            </button>
          </div>

          {/* File panels */}
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
            {uploadedFiles.map((uf) => {
              const tableName = fileToTableName(uf.filename);
              const isOpen = openPanels.has(tableName);
              const schema = uf.schema_json;
              const preview = previews[tableName];

              return (
                <div
                  key={uf.file_id}
                  className="rounded"
                  style={{ border: "1px solid rgba(139,92,246,0.25)", backgroundColor: "#12091F" }}
                >
                  {/* Panel header */}
                  <button
                    type="button"
                    onClick={() => togglePanel(tableName)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded shrink-0"
                        style={{ backgroundColor: "rgba(139,92,246,0.15)", color: "#a78bfa" }}
                      >
                        raw.{tableName.toLowerCase()}
                      </span>
                      <span className="text-sm text-purple-200 truncate">{uf.filename}</span>
                      <span className="text-xs text-purple-600 shrink-0">
                        {(uf.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      {schema ? (
                        <span className="text-xs text-emerald-400">
                          {schema.length} cols
                        </span>
                      ) : (
                        <span className="text-xs text-purple-600">schema pending…</span>
                      )}
                      <span className="text-purple-500 text-xs">{isOpen ? "▲" : "▼"}</span>
                    </div>
                  </button>

                  {/* Panel body */}
                  {isOpen && (
                    <div
                      className="px-4 pb-4 border-t"
                      style={{ borderColor: "rgba(139,92,246,0.2)" }}
                    >
                      {/* Schema */}
                      <div className="mt-3">
                        <p className="text-xs font-medium text-purple-400 mb-2">Schema</p>
                        {schema ? (
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                            {schema.map((col) => (
                              <div key={col.name} className="flex items-center gap-2">
                                <span className="text-xs text-purple-200 font-mono truncate">{col.name}</span>
                                <span className="text-xs text-purple-600 shrink-0">{col.type}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-purple-600 italic">
                            Schema will populate once DATA_INGESTION completes — click Refresh schemas above.
                          </p>
                        )}
                      </div>

                      {/* Preview rows */}
                      <div className="mt-4">
                        <p className="text-xs font-medium text-purple-400 mb-2">Preview (first 20 rows)</p>
                        {preview === "loading" && (
                          <p className="text-xs text-purple-600">Loading…</p>
                        )}
                        {preview === "error" && (
                          <p className="text-xs text-purple-600 italic">
                            Preview available once ingestion completes — click Refresh schemas then re-open.
                          </p>
                        )}
                        {preview === null && (
                          <p className="text-xs text-purple-600 italic">Requesting preview…</p>
                        )}
                        {preview && preview !== "loading" && preview !== "error" && (
                          <div className="overflow-x-auto">
                            <table className="text-xs w-full border-collapse">
                              <thead>
                                <tr>
                                  {preview.columns.map((col) => (
                                    <th
                                      key={col}
                                      className="text-left text-purple-400 font-medium px-2 py-1 whitespace-nowrap"
                                      style={{ borderBottom: "1px solid rgba(139,92,246,0.2)" }}
                                    >
                                      {col}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {preview.rows.map((row, i) => (
                                  <tr key={i} className={i % 2 === 0 ? "bg-purple-900/10" : ""}>
                                    {preview.columns.map((col) => (
                                      <td
                                        key={col}
                                        className="px-2 py-1 text-purple-200 max-w-[140px] truncate"
                                      >
                                        {row[col] == null ? (
                                          <span className="text-purple-700">null</span>
                                        ) : (
                                          String(row[col])
                                        )}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div
            className="px-6 py-4 border-t flex justify-end"
            style={{ borderColor: "rgba(139,92,246,0.3)" }}
          >
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm rounded font-medium text-white bg-purple-600 hover:bg-purple-500"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── render: form phase ──────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div
        className="rounded-lg shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
        style={{ backgroundColor: "#241740", border: "1px solid rgba(139,92,246,0.4)" }}
      >
        <div
          className="px-6 py-4 border-b"
          style={{ borderColor: "rgba(139,92,246,0.3)" }}
        >
          <h2 className="text-base font-semibold text-white">New Ticket</h2>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {/* Title */}
          <div>
            <label className={labelClass}>
              Title <span className="text-purple-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={inputClass}
              style={inputStyle}
              placeholder="e.g. Add fct_daily_orders from RAW.ORDERS"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className={labelClass}>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className={inputClass}
              style={inputStyle}
              placeholder="Describe the data engineering task…"
            />
          </div>

          {/* Grain */}
          <div>
            <label className={labelClass}>Grain</label>
            <input
              type="text"
              value={grain}
              onChange={(e) => setGrain(e.target.value)}
              className={inputClass}
              style={inputStyle}
              placeholder="e.g. one row per order per day"
            />
          </div>

          {/* Metrics */}
          <div>
            <label className={labelClass}>
              Metrics{" "}
              <span className="text-purple-600 font-normal">(one per line)</span>
            </label>
            <textarea
              value={metrics}
              onChange={(e) => setMetrics(e.target.value)}
              rows={3}
              className={inputClass}
              style={inputStyle}
              placeholder={"daily_revenue: sum of order_amount\norder_count: count of orders"}
            />
          </div>

          {/* Constraints */}
          <div>
            <label className={labelClass}>
              Constraints{" "}
              <span className="text-purple-600 font-normal">(one per line)</span>
            </label>
            <textarea
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              rows={2}
              className={inputClass}
              style={inputStyle}
              placeholder={"Exclude cancelled orders\nFilter to last 90 days"}
            />
          </div>

          {/* File upload */}
          <div>
            <label className={labelClass}>
              Source Data{" "}
              <span className="text-purple-600 font-normal">(CSV, Parquet, JSON)</span>
            </label>
            <div
              className={`rounded border-2 border-dashed p-4 text-center cursor-pointer transition-colors ${
                dragging
                  ? "border-purple-400 bg-purple-900/20"
                  : "border-purple-800/60 hover:border-purple-700"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                addFiles(e.dataTransfer.files);
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <p className="text-xs text-purple-400">
                Drop files here or{" "}
                <span className="text-purple-300 underline">browse</span>
              </p>
              <p className="text-xs text-purple-600 mt-1">.csv · .parquet · .json · .jsonl</p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.parquet,.json,.jsonl"
                className="hidden"
                onChange={(e) => addFiles(e.target.files)}
              />
            </div>
            {files.length > 0 && (
              <ul className="mt-2 space-y-1">
                {files.map((f) => (
                  <li
                    key={f.name}
                    className="flex items-center justify-between text-xs text-purple-300 bg-purple-900/20 rounded px-2 py-1"
                  >
                    <span className="truncate">
                      {f.name}{" "}
                      <span className="text-purple-500">
                        ({(f.size / 1024).toFixed(1)} KB)
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(f.name)}
                      className="ml-2 text-purple-500 hover:text-purple-300"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {uploadProgress && (
            <p className="text-xs text-purple-300">{uploadProgress}</p>
          )}
          {error && <p className="text-red-400 text-xs">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm rounded text-purple-300 hover:text-purple-100"
              style={{ border: "1px solid rgba(139,92,246,0.3)" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm rounded font-medium text-white bg-purple-600 hover:bg-purple-500 disabled:opacity-50"
            >
              {submitting ? (uploadProgress ?? "Creating…") : "Create Ticket"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
