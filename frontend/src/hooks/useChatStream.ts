import { useCallback, useState } from "react";
import { streamChat } from "../api/client";

export function useChatStream(sessionId: number | null) {
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const send = useCallback(
    async (
      message: string,
      onToken: (token: string) => void,
      onDone: () => void,
      onStarted?: () => void,
      onStreamStarted?: () => void,
    ) => {
      if (!sessionId) return;
      setStreaming(true);
      setStreamError(null);
      try {
        await streamChat(
          sessionId,
          message,
          (ev) => {
            if (ev.type === "started") onStreamStarted?.();
            if (ev.type === "token") onToken(ev.content);
            if (ev.type === "error") setStreamError(ev.content);
            if (ev.type === "done") onDone();
          },
          onStarted,
        );
      } catch (e) {
        setStreamError(e instanceof Error ? e.message : "Chat failed");
      } finally {
        setStreaming(false);
      }
    },
    [sessionId],
  );

  return { send, streaming, streamError };
}
