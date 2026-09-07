import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { subscribeToLiveEvents, type LiveEvent } from "@/lib/api";

/**
 * Subscribes to GET /api/events/stream for the component's lifetime and
 * invalidates the given TanStack Query keys whenever a live event matching
 * `eventTypes` arrives — the queue/audit views then refetch without a
 * manual page reload. See docs/design/lovable/09-frontend-integration-plan.md, Phase 5.
 */
export function useLiveEvents(eventTypes: string[], queryKeys: string[][]) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = subscribeToLiveEvents((event: LiveEvent) => {
      if (!eventTypes.includes(event.event_type)) return;
      for (const key of queryKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    });
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
