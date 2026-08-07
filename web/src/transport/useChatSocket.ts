import { useCallback, useEffect, useRef } from "react";
import { ChatSocket, socketUrl } from "./ChatSocket";
import { useChatStore } from "@/state/chatStore";
import { clientId } from "@/lib/identity";

export function useChatSocket() {
  const socket = useRef<ChatSocket | null>(null);

  useEffect(() => {
    const { apply, setConnection } = useChatStore.getState();
    const instance = new ChatSocket(socketUrl(clientId()), {
      onEvent: apply,
      onStateChange: setConnection,
      onProtocolError: (reason, raw) => {
        console.error(`[protocol] ${reason}`, raw);
      },
    });
    socket.current = instance;
    instance.connect();
    return () => {
      instance.close();
      socket.current = null;
    };
  }, []);

  const send = useCallback((text: string) => {
    const { sessionId, questionSent } = useChatStore.getState();
    questionSent(text);
    socket.current?.send({
      type: "user_message",
      text,
      ...(sessionId ? { session_id: sessionId } : {}),
    });
  }, []);

  const cancel = useCallback(() => {
    socket.current?.send({ type: "cancel" });
  }, []);

  return { send, cancel };
}
