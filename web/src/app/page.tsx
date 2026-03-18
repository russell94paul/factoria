"use client";

import { useEffect, useState, useCallback } from "react";
import { EnrichedTicket, listTickets } from "@/lib/api";
import KanbanBoard from "@/components/KanbanBoard";

const POLL_INTERVAL = 3000;

export default function HomePage() {
  const [tickets, setTickets] = useState<EnrichedTicket[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listTickets();
      setTickets(data);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-red-600 text-sm">{error}</p>
      </div>
    );
  }

  return <KanbanBoard tickets={tickets} onRefresh={refresh} />;
}
