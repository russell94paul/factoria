"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Artifact, getArtifactContent } from "@/lib/api";

const ROLE_LABELS: Record<string, string> = {
  intake_summary: "Intake Summary",
  design_doc: "Design Document",
  profiling_report: "Profiling Report",
  profiling_doc: "Profiling Notes",
  dbt_model: "dbt Model",
  dbt_schema: "dbt Schema",
  compile_summary: "Compile Summary",
  qa_evidence: "QA Evidence",
  qa_report: "QA Report",
  pr_summary: "PR Summary",
};

function renderContent(path: string, content: string) {
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext === "md") {
    return (
      <div className="prose prose-sm max-w-none p-4">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    );
  }
  if (ext === "json") {
    let pretty = content;
    try {
      pretty = JSON.stringify(JSON.parse(content), null, 2);
    } catch {
      // use raw
    }
    return <pre className="text-xs p-4 overflow-auto">{pretty}</pre>;
  }
  return <pre className="text-xs p-4 overflow-auto">{content}</pre>;
}

function ArtifactRow({ artifact }: { artifact: Artifact }) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (!open && content === null) {
      setLoading(true);
      try {
        const text = await getArtifactContent(artifact.artifact_id);
        setContent(text);
      } catch {
        setContent("(failed to load content)");
      } finally {
        setLoading(false);
      }
    }
    setOpen(!open);
  }

  const fileName = artifact.file_path.split(/[\\/]/).pop() ?? artifact.file_path;
  const label = ROLE_LABELS[artifact.artifact_role] ?? artifact.artifact_role;

  return (
    <div className="border border-purple-900/60 rounded mb-2">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-2 text-left hover:bg-purple-900/20"
      >
        <div>
          <span className="text-sm font-medium text-purple-100">{label}</span>
          <span className="ml-2 text-xs text-purple-400">{fileName}</span>
        </div>
        <span className="text-purple-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-purple-900/60 bg-black/20">
          {loading ? (
            <p className="text-xs text-purple-400 p-4">Loading…</p>
          ) : content !== null ? (
            renderContent(artifact.file_path, content)
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function ArtifactViewer({ artifacts }: { artifacts: Artifact[] }) {
  if (artifacts.length === 0) {
    return <p className="text-sm text-purple-400 mt-4">No artefacts yet.</p>;
  }
  return (
    <div className="mt-4">
      {artifacts.map((a) => (
        <ArtifactRow key={a.artifact_id} artifact={a} />
      ))}
    </div>
  );
}
