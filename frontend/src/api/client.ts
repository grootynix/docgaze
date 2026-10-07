export type DocumentStatus = "processing" | "ready" | "failed";

export interface Document {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  chunk_count: number | null;
}

export interface ChatSession {
  id: number;
  document_id: number;
  title: string;
  created_at: string;
}

export interface Message {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Health {
  status: "ok" | "degraded";
  database: boolean;
  llm_provider: "openai" | "ollama" | "none";
  openai: boolean;
  openai_error: string | null;
  ollama: boolean;
  ollama_error: string | null;
}

const API = "/api";

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<Health> {
  return handleJson(await fetch(`${API}/health`));
}

export async function listDocuments(): Promise<Document[]> {
  return handleJson(await fetch(`${API}/documents`));
}

export async function uploadDocument(file: File): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  return handleJson(
    await fetch(`${API}/documents`, { method: "POST", body: form }),
  );
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`${API}/documents/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await res.text());
  }
}

export async function createSession(
  documentId: number,
  title = "Chat",
): Promise<ChatSession> {
  return handleJson(
    await fetch(`${API}/documents/${documentId}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
}

export async function listMessages(sessionId: number): Promise<Message[]> {
  return handleJson(await fetch(`${API}/sessions/${sessionId}/messages`));
}

export type StreamEvent =
  | { type: "started" }
  | { type: "token"; content: string }
  | { type: "done"; message_id: number }
  | { type: "error"; content: string };

export async function streamChat(
  sessionId: number,
  message: string,
  onEvent: (ev: StreamEvent) => void,
  onStarted?: () => void,
): Promise<void> {
  const res = await fetch(`${API}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  onStarted?.();
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      const payload = JSON.parse(line.slice(6)) as StreamEvent;
      onEvent(payload);
    }
  }
}
