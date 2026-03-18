import { AgentSession, WorkflowEvent } from "@/lib/api";

const EVENT_ICONS: Record<string, string> = {
  state_transition: "→",
  agent_completed: "✓",
  artifact_created: "📄",
  gate_approved: "✅",
  error: "✗",
};

const SESSION_COLORS: Record<string, string> = {
  completed: "bg-green-100 text-green-800",
  running: "bg-blue-100 text-blue-800",
  failed: "bg-red-100 text-red-800",
};

function fmt(ts: string): string {
  return new Date(ts).toLocaleTimeString();
}

export default function AgentTimeline({
  sessions,
  events,
}: {
  sessions: AgentSession[];
  events: WorkflowEvent[];
}) {
  return (
    <div className="mt-4 space-y-6">
      {sessions.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-purple-500 uppercase tracking-wide mb-2">
            Agent Sessions
          </h3>
          <div className="space-y-2">
            {sessions.map((s) => (
              <div
                key={s.agent_session_id}
                className="flex items-center justify-between rounded px-3 py-2 border border-purple-900/60 bg-purple-900/20"
              >
                <div>
                  <span className="text-sm font-medium text-purple-100">{s.agent_name}</span>
                  <span
                    className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                      SESSION_COLORS[s.status] ?? "bg-gray-700 text-gray-200"
                    }`}
                  >
                    {s.status}
                  </span>
                </div>
                <span className="text-xs text-purple-400">
                  {fmt(s.started_at)}
                  {s.finished_at ? ` → ${fmt(s.finished_at)}` : " …"}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Workflow Events
        </h3>
        <div className="space-y-1">
          {events.map((ev) => (
            <div key={ev.event_id} className="flex items-start gap-2 text-xs py-1">
              <span className="text-purple-500 w-5 text-center flex-shrink-0">
                {EVENT_ICONS[ev.event_type] ?? "·"}
              </span>
              <div className="flex-1 min-w-0">
                <span className="font-medium text-purple-200">{ev.event_type}</span>
                {ev.from_state && ev.to_state && (
                  <span className="text-purple-400 ml-1">
                    {ev.from_state} → {ev.to_state}
                  </span>
                )}
                {ev.message && (
                  <span className="text-purple-500 ml-1 truncate block">{ev.message}</span>
                )}
              </div>
              <span className="text-purple-600 flex-shrink-0">{fmt(ev.created_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
