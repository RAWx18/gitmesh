/**
 * `useLiveEventSocket`: small reconnecting WebSocket hook for the
 * `/api/projects/:id/events/ws` stream.
 *
 * Extracted from `LiveRunWidget` so future live-event consumers (run
 * detail pages, dashboards) can share the wiring instead of inlining
 * a copy of the connect/reconnect/dispose dance.
 */

import { useEffect, useRef } from "react";
import type { LiveEvent } from "@gitmesh/core";

export interface UseLiveEventSocketConfig {
  projectId: string | null | undefined;
  /** if false, the socket isn't opened (lets callers gate on "is anything live?") */
  enabled: boolean;
  /** called on every successfully-parsed event */
  onEvent: (event: LiveEvent) => void;
  /** ms between reconnect attempts on close/error */
  reconnectDelayMs?: number;
}

export function useLiveEventSocket({
  projectId,
  enabled,
  onEvent,
  reconnectDelayMs = 1500,
}: UseLiveEventSocketConfig): void {
  // Capture the latest onEvent reference so reconnects don't dangle on stale closures.
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!projectId || !enabled) return;

    let closed = false;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const scheduleReconnect = () => {
      if (closed) return;
      reconnectTimer = window.setTimeout(connect, reconnectDelayMs);
    };

    const connect = () => {
      if (closed) return;
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${protocol}://${window.location.host}/api/projects/${encodeURIComponent(projectId)}/events/ws`;
      socket = new WebSocket(url);

      socket.onmessage = (message) => {
        const raw = typeof message.data === "string" ? message.data : "";
        if (!raw) return;
        let event: LiveEvent;
        try {
          event = JSON.parse(raw) as LiveEvent;
        } catch {
          return;
        }
        onEventRef.current(event);
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        socket.close(1000, "live_event_socket_unmount");
      }
    };
  }, [projectId, enabled, reconnectDelayMs]);
}
