import { StatusBadge } from "./StatusTrack.jsx";

export default function RequestList({ requests, selectedId, onSelect, showClient, emptyText }) {
  if (requests.length === 0) return <p className="muted">{emptyText}</p>;

  return (
    <ul className="request-list">
      {requests.map((r) => (
        <li key={r.id}>
          <button className={r.id === selectedId ? "selected" : ""} onClick={() => onSelect(r.id)}>
            <span className="title">
              #{r.id} {r.task_name}
            </span>
            <StatusBadge status={r.status} />
            <span className="meta">
              {showClient && <>{r.client_name}, </>}
              <span className="num">{r.episodes_assigned}/{r.episodes_requested}</span> episodes, due {r.deadline}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
