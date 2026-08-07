import { NavLink } from "react-router-dom";
import type { SessionSummary } from "@/api/client";
import "./SessionSidebar.css";

interface Props {
  sessions: SessionSummary[];
  loading: boolean;
  onNew: () => void;
  onDelete: (sessionId: string) => void;
}

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

export function SessionSidebar({ sessions, loading, onNew, onDelete }: Props) {
  return (
    <nav className="sidebar" aria-label="Conversations">
      <div className="sidebar__head">
        <span className="sidebar__brand">Engineering assistant</span>
      </div>

      <button type="button" className="sidebar__new" onClick={onNew}>
        New conversation
      </button>

      {loading && <p className="sidebar__empty">Loading…</p>}

      {!loading && sessions.length === 0 && (
        <p className="sidebar__empty">
          Nothing here yet. Ask something about the codebase to start.
        </p>
      )}

      <ul className="sidebar__list">
        {sessions.map((session) => (
          <li key={session.id} className="sidebar__row">
            <NavLink
              to={`/s/${session.id}`}
              className={({ isActive }) =>
                `sidebar__item ${isActive ? "sidebar__item--active" : ""}`
              }
            >
              <span className="sidebar__title">{session.title ?? "Untitled"}</span>
              <span className="sidebar__meta">
                {relativeTime(session.updated_at)} · {session.turn_count} turns
              </span>
            </NavLink>
            <button
              type="button"
              className="sidebar__delete"
              aria-label={`Delete ${session.title ?? "conversation"}`}
              onClick={() => {
                onDelete(session.id);
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>

      <p className="sidebar__scope">
        History is kept for this browser only.
      </p>
    </nav>
  );
}
