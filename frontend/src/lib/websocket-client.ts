/**
 * AEGIS-Marine: Resilient WebSocket Client (TASK-040)
 * Streams real-time case state progression (/cases/{id}/status) with exponential backoff
 * automatic reconnection, keep-alive ping/pong heartbeat, and subscription event dispatching.
 */

import type { CaseStatusMessage, ConnectionState } from "@/types";

export interface WebSocketClientOptions {
  baseUrl?: string;
  token?: string | null;
  initialDelayMs?: number;
  maxDelayMs?: number;
  backoffMultiplier?: number;
  maxReconnectAttempts?: number;
  heartbeatIntervalMs?: number;
}

export type MessageListener = (message: CaseStatusMessage) => void;
export type StateChangeListener = (state: ConnectionState) => void;
export type ErrorListener = (error: Event | Error) => void;

export class CaseStatusWebSocketClient {
  private caseId: string;
  private options: Required<WebSocketClientOptions>;
  private socket: WebSocket | null = null;
  private state: ConnectionState = "idle";
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private isManuallyClosed = false;

  private messageListeners = new Set<MessageListener>();
  private stateListeners = new Set<StateChangeListener>();
  private errorListeners = new Set<ErrorListener>();

  constructor(caseId: string, options: WebSocketClientOptions = {}) {
    this.caseId = caseId;

    const defaultWsUrl =
      typeof process !== "undefined" && process.env.NEXT_PUBLIC_WS_URL
        ? process.env.NEXT_PUBLIC_WS_URL.replace(/\/$/, "")
        : "ws://localhost:8000/api/v1";

    this.options = {
      baseUrl: options.baseUrl || defaultWsUrl,
      token: options.token ?? null,
      initialDelayMs: options.initialDelayMs ?? 1000,
      maxDelayMs: options.maxDelayMs ?? 16000,
      backoffMultiplier: options.backoffMultiplier ?? 1.5,
      maxReconnectAttempts: options.maxReconnectAttempts ?? 10,
      heartbeatIntervalMs: options.heartbeatIntervalMs ?? 15000,
    };
  }

  public getState(): ConnectionState {
    return this.state;
  }

  private setState(newState: ConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.stateListeners.forEach((listener) => {
        try {
          listener(newState);
        } catch {
          // Prevent listener exceptions from breaking client loop
        }
      });
    }
  }

  public onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  public onStateChange(listener: StateChangeListener): () => void {
    this.stateListeners.add(listener);
    listener(this.state);
    return () => this.stateListeners.delete(listener);
  }

  public onError(listener: ErrorListener): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  public connect(): void {
    if (typeof window === "undefined") {
      // Server-side rendering guard
      return;
    }

    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.isManuallyClosed = false;
    this.setState("connecting");

    const tokenParam = this.options.token
      ? `?token=${encodeURIComponent(this.options.token)}`
      : "";
    const wsUrl = `${this.options.baseUrl}/cases/${this.caseId}/status${tokenParam}`;

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.setState("connected");
        this.startHeartbeat();
      };

      this.socket.onmessage = (event: MessageEvent) => {
        try {
          const rawData = typeof event.data === "string" ? event.data : "";
          if (!rawData) return;

          const parsed = JSON.parse(rawData);
          // Filter out heartbeat pong frames
          if (parsed && parsed.type === "pong") {
            return;
          }

          const message: CaseStatusMessage = {
            case_id: parsed.case_id || this.caseId,
            status: parsed.status || "unknown",
            progress_pct: Number(parsed.progress_pct ?? 0),
            stage: parsed.stage,
            message: parsed.message,
            timestamp: parsed.timestamp || new Date().toISOString(),
            error: parsed.error,
          };

          this.messageListeners.forEach((listener) => {
            try {
              listener(message);
            } catch {
              // Ignore subscriber errors
            }
          });
        } catch {
          // Ignore non-JSON or malformed frames
        }
      };

      this.socket.onerror = (event: Event) => {
        this.setState("error");
        this.errorListeners.forEach((listener) => {
          try {
            listener(event);
          } catch {
            // Ignore subscriber errors
          }
        });
      };

      this.socket.onclose = (event: CloseEvent) => {
        this.stopHeartbeat();
        this.socket = null;

        if (this.isManuallyClosed || event.code === 1000) {
          this.setState("disconnected");
        } else {
          this.scheduleReconnect();
        }
      };
    } catch {
      this.setState("error");
      this.scheduleReconnect();
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send("ping");
      }
    }, this.options.heartbeatIntervalMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.isManuallyClosed) return;

    if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
      this.setState("disconnected");
      return;
    }

    this.setState("reconnecting");
    this.reconnectAttempts += 1;

    const delay = Math.min(
      this.options.initialDelayMs *
        Math.pow(this.options.backoffMultiplier, this.reconnectAttempts - 1),
      this.options.maxDelayMs
    );

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  public disconnect(): void {
    this.isManuallyClosed = true;
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.socket) {
      this.socket.close(1000, "Client explicit disconnect");
      this.socket = null;
    }

    this.setState("disconnected");
  }
}
