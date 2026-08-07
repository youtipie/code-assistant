import { Navigate, Route, Routes, useMatch, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { SessionSidebar } from "@/components/SessionSidebar";
import { ChatRoute } from "@/routes/ChatRoute";
import { useChatStore } from "@/state/chatStore";
import "./App.css";

function Shell() {
  const navigate = useNavigate();

  const match = useMatch("/s/:sessionId");
  const openSessionId = match?.params.sessionId;
  const queryClient = useQueryClient();
  const reset = useChatStore((state) => state.reset);

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
    refetchInterval: 30_000,
  });

  const remove = useMutation({
    mutationFn: api.deleteSession,
    onSuccess: (_result, deletedId) => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });

      queryClient.removeQueries({ queryKey: ["messages", deletedId] });

      if (openSessionId === deletedId) {
        reset();
        navigate("/", { replace: true });
      }
    },
  });

  return (
    <div className="app">
      <SessionSidebar
        sessions={sessions ?? []}
        loading={isLoading}
        onNew={() => {
          reset();
          navigate("/");
        }}
        onDelete={(sessionId) => {
          remove.mutate(sessionId);
        }}
      />
      <main className="app__main">
        <Routes>
          <Route path="/" element={<ChatRoute />} />
          <Route path="/s/:sessionId" element={<ChatRoute />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export function App() {
  return <Shell />;
}
