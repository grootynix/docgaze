import { useEffect, useRef, useState } from "react";
import type { Document, Message } from "../api/client";
import { useChatStream } from "../hooks/useChatStream";

interface Props {
  document: Document | null;
  sessionId: number | null;
  messages: Message[];
  onMessagesChange: () => void;
}

export function ChatPanel({
  document,
  sessionId,
  messages,
  onMessagesChange,
}: Props) {
  const [input, setInput] = useState("");
  const [draftAssistant, setDraftAssistant] = useState("");
  const [waitingForTokens, setWaitingForTokens] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { send, streaming, streamError } = useChatStream(sessionId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, draftAssistant]);

  const chatDisabled =
    !document ||
    document.status !== "ready" ||
    !sessionId ||
    streaming;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || chatDisabled) return;
    setInput("");
    setDraftAssistant("");
    setWaitingForTokens(true);
    await send(
      text,
      (token) => {
        setWaitingForTokens(false);
        setDraftAssistant((prev) => prev + token);
      },
      () => {
        setWaitingForTokens(false);
        setDraftAssistant("");
        onMessagesChange();
      },
      () => {
        void onMessagesChange();
      },
      () => setWaitingForTokens(true),
    );
  };

  if (!document) {
    return (
      <div className="chat-panel empty">
        <p>Upload a PDF or text file to start.</p>
      </div>
    );
  }

  return (
    <div className="chat-panel">
      <header className="chat-header">
        <h2>{document.filename}</h2>
        {document.status === "processing" && (
          <span className="badge">Indexing document…</span>
        )}
        {document.status === "failed" && (
          <span className="badge error">{document.error_message ?? "Failed"}</span>
        )}
      </header>

      <div className="messages">
        {messages.map((m) => (
          <div key={m.id} className={`message message-${m.role}`}>
            <span className="role">{m.role === "user" ? "You" : "Assistant"}</span>
            <p>{m.content}</p>
          </div>
        ))}
        {(waitingForTokens || draftAssistant) && (
          <div className="message message-assistant">
            <span className="role">Assistant</span>
            <p>{draftAssistant || "Generating answer…"}</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {streamError && <p className="error-text">{streamError}</p>}

      <form className="chat-form" onSubmit={handleSubmit}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            document.status === "ready"
              ? "Ask about this document…"
              : "Chat unavailable until document is ready"
          }
          disabled={chatDisabled}
          rows={3}
        />
        <button type="submit" disabled={chatDisabled || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
