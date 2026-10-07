import { useCallback, useEffect, useState } from "react";
import {
  createSession,
  deleteDocument,
  fetchHealth,
  listDocuments,
  listMessages,
  uploadDocument,
  type Document,
  type Health,
  type Message,
} from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentList } from "./components/DocumentList";
import { UploadZone } from "./components/UploadZone";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selected, setSelected] = useState<Document | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      if (selected) {
        const updated = docs.find((d) => d.id === selected.id);
        if (updated) setSelected(updated);
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load documents");
    }
  }, [selected]);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await fetchHealth());
    } catch {
      setHealth({
        status: "degraded",
        database: false,
        llm_provider: "none",
        openai: false,
        openai_error: null,
        ollama: false,
        ollama_error: "API unreachable",
      });
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    void listDocuments()
      .then(setDocuments)
      .catch((e) =>
        setLoadError(e instanceof Error ? e.message : "Failed to load documents"),
      );
  }, []);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (!hasProcessing) return;
    const id = window.setInterval(refreshDocuments, 2000);
    return () => clearInterval(id);
  }, [documents, refreshDocuments]);

  const selectDocument = async (doc: Document) => {
    setSelected(doc);
    setSessionId(null);
    setMessages([]);
    if (doc.status !== "ready") return;
    try {
      const session = await createSession(doc.id);
      setSessionId(session.id);
      setMessages(await listMessages(session.id));
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to start chat");
    }
  };

  const handleUpload = async (file: File) => {
    setLoadError(null);
    const doc = await uploadDocument(file);
    await refreshDocuments();
    await selectDocument(doc);
  };

  const handleDelete = async (id: number) => {
    await deleteDocument(id);
    if (selected?.id === id) {
      setSelected(null);
      setSessionId(null);
      setMessages([]);
    }
    await refreshDocuments();
  };

  const reloadMessages = async () => {
    if (!sessionId) return;
    setMessages(await listMessages(sessionId));
  };

  return (
    <div className="app">
      <header className="top-bar">
        <h1>DocGaze</h1>
        {health && (
          <span className={`health health-${health.status}`}>
            {health.status === "ok"
              ? `LLM: ${health.llm_provider === "openai" ? "OpenAI" : "Ollama"}`
              : [
                  health.openai_error && `OpenAI: ${health.openai_error}`,
                  health.ollama_error && `Ollama: ${health.ollama_error}`,
                ]
                  .filter(Boolean)
                  .join(" · ") || "LLM unavailable"}
          </span>
        )}
      </header>

      {loadError && <p className="banner error">{loadError}</p>}

      <div className="layout">
        <aside className="sidebar">
          <UploadZone onUpload={handleUpload} disabled={health?.status !== "ok"} />
          <DocumentList
            documents={documents}
            selectedId={selected?.id ?? null}
            onSelect={selectDocument}
            onDelete={handleDelete}
          />
        </aside>
        <main>
          <ChatPanel
            document={selected}
            sessionId={sessionId}
            messages={messages}
            onMessagesChange={reloadMessages}
          />
        </main>
      </div>
    </div>
  );
}
