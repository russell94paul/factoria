"use client";

import { useRef, useState } from "react";
import { createTicket, uploadFile } from "@/lib/api";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export default function CreateTicketModal({ onClose, onCreated }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [grain, setGrain] = useState("");
  const [metrics, setMetrics] = useState("");
  const [constraints, setConstraints] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSubmitting(true);
    setError(null);

    try {
      const metricsArr = metrics.trim() ? metrics.split("\n").map((s) => s.trim()).filter(Boolean) : undefined;
      const constraintsArr = constraints.trim() ? constraints.split("\n").map((s) => s.trim()).filter(Boolean) : undefined;

      const result = await createTicket({
        title,
        description,
        ticket_kind: "DATA_ENGINEERING",
        grain: grain.trim() || undefined,
        metrics: metricsArr,
        constraints: constraintsArr,
      });

      if (files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          setUploadProgress(`Uploading ${files[i].name} (${i + 1}/${files.length})…`);
          await uploadFile(result.ticket_id, files[i]);
        }
        setUploadProgress(null);
      }

      onCreated();
      onClose();
    } catch (err) {
      setError(String(err));
      setSubmitting(false);
      setUploadProgress(null);
    }
  }

  const inputClass = "w-full rounded px-3 py-2 text-sm text-purple-100 placeholder-purple-600 focus:outline-none focus:ring-1 focus:ring-purple-500";
  const inputStyle = { backgroundColor: "#12091F", border: "1px solid rgba(139,92,246,0.3)" };
  const labelClass = "block text-xs font-medium text-purple-400 mb-1";

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="rounded-lg shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto" style={{ backgroundColor: "#241740", border: "1px solid rgba(139,92,246,0.4)" }}>
        <div className="px-6 py-4 border-b" style={{ borderColor: "rgba(139,92,246,0.3)" }}>
          <h2 className="text-base font-semibold text-white">New Ticket</h2>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {/* Title */}
          <div>
            <label className={labelClass}>Title <span className="text-purple-500">*</span></label>
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
            <label className={labelClass}>Metrics <span className="text-purple-600 font-normal">(one per line)</span></label>
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
            <label className={labelClass}>Constraints <span className="text-purple-600 font-normal">(one per line)</span></label>
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
            <label className={labelClass}>Source Data <span className="text-purple-600 font-normal">(CSV, Parquet, JSON)</span></label>
            <div
              className={`rounded border-2 border-dashed p-4 text-center cursor-pointer transition-colors ${dragging ? "border-purple-400 bg-purple-900/20" : "border-purple-800/60 hover:border-purple-700"}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
              onClick={() => fileInputRef.current?.click()}
            >
              <p className="text-xs text-purple-400">Drop files here or <span className="text-purple-300 underline">browse</span></p>
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
                  <li key={f.name} className="flex items-center justify-between text-xs text-purple-300 bg-purple-900/20 rounded px-2 py-1">
                    <span className="truncate">{f.name} <span className="text-purple-500">({(f.size / 1024).toFixed(1)} KB)</span></span>
                    <button type="button" onClick={() => removeFile(f.name)} className="ml-2 text-purple-500 hover:text-purple-300">✕</button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {uploadProgress && <p className="text-xs text-purple-300">{uploadProgress}</p>}
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
