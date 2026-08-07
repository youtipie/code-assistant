import type { Status } from "@/api/client";
import type { ConnectionState } from "@/transport/ChatSocket";
import "./ServerStatusBar.css";

interface Props {
  status: Status | undefined;
  connection: ConnectionState;
}

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: "Connecting",
  open: "Connected",
  reconnecting: "Reconnecting",
  closed: "Disconnected",
};

export function ServerStatusBar({ status, connection }: Props) {
  return (
    <div className="status">
      <span className={`status__conn status__conn--${connection}`}>
        <span className="status__dot" aria-hidden="true" />
        {CONNECTION_LABEL[connection]}
      </span>

      {status?.servers.map((server) => (
        <span
          key={server.name}
          className={`status__server status__server--${server.name} ${
            server.available ? "" : "status__server--down"
          }`}
          title={server.description || undefined}
        >
          {server.name}
          <span className="status__count mono">
            {server.available ? server.tool_count : "down"}
          </span>
        </span>
      ))}

      {status && <span className="status__model mono">{status.model}</span>}
    </div>
  );
}
