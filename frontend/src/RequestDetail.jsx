import { useEffect, useState } from "react";
import { api } from "./api.js";
import StatusTrack, { label } from "./StatusTrack.jsx";
import EpisodePicker from "./EpisodePicker.jsx";

// What each button says. The server decides WHICH buttons are allowed
// (request.allowed_next), and checks again when the button is pressed.
const ACTION_TEXT = {
  in_progress: "Start work",
  delivered: "Mark as delivered",
  accepted: "Accept delivery",
  rejected: "Reject delivery",
};

export default function RequestDetail({ requestId, isStaff, onChanged }) {
  const [request, setRequest] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const [r, e] = await Promise.all([
        api(`/requests/${requestId}`),
        api(`/requests/${requestId}/assignments`),
      ]);
      setRequest(r);
      setEpisodes(e);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [requestId]);

  async function changeStatus(status) {
    setError("");
    try {
      await api(`/requests/${requestId}/status`, {
        method: "POST",
        body: { status, comment: comment || null },
      });
      setComment("");
      await load();
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function unassign(episodeId) {
    setError("");
    try {
      await api(`/requests/${requestId}/assignments/${episodeId}`, { method: "DELETE" });
      await load();
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function afterAssign() {
    await load();
    onChanged();
  }

  if (!request) return error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>;

  const canEditEpisodes = isStaff && request.status === "in_progress";
  const missing = request.episodes_requested - request.episodes_assigned;

  return (
    <div className="detail">
      <h2>
        #{request.id} {request.task_name}
      </h2>
      <StatusTrack status={request.status} />

      <dl className="facts">
        <dt>Client</dt>
        <dd>{request.client_name}</dd>
        <dt>Episodes</dt>
        <dd className="num">
          {request.episodes_assigned} of {request.episodes_requested} assigned
        </dd>
        <dt>Deadline</dt>
        <dd>{request.deadline}</dd>
        {request.notes && (
          <>
            <dt>Notes</dt>
            <dd className="notes">{request.notes}</dd>
          </>
        )}
      </dl>

      {request.allowed_next.length > 0 && (
        <div className="actions">
          <input
            placeholder="Comment (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={2000}
          />
          {request.allowed_next.map((status) => (
            <button
              key={status}
              className={status === "rejected" ? "danger" : status === "accepted" ? "success" : "primary"}
              onClick={() => changeStatus(status)}
              disabled={status === "delivered" && missing > 0}
              title={status === "delivered" && missing > 0 ? `Assign ${missing} more episodes first` : ""}
            >
              {ACTION_TEXT[status] ?? label(status)}
            </button>
          ))}
        </div>
      )}
      {request.allowed_next.includes("delivered") && missing > 0 && (
        <p className="muted">Assign {missing} more episode{missing === 1 ? "" : "s"} before marking this as delivered.</p>
      )}
      {error && <p className="error">{error}</p>}

      <h3>Assigned episodes ({episodes.length})</h3>
      {episodes.length === 0 ? (
        <p className="muted">No episodes assigned yet.</p>
      ) : (
        <EpisodeTable
          episodes={episodes}
          action={canEditEpisodes ? (ep) => <button className="link" onClick={() => unassign(ep.episode_id)}>Remove</button> : null}
        />
      )}

      {canEditEpisodes && <EpisodePicker request={request} onAssigned={afterAssign} />}

      <h3>History</h3>
      <ul className="history">
        {request.history.map((h, i) => (
          <li key={i}>
            <span className="when">{new Date(h.changed_at).toLocaleString()}</span>{" "}
            <strong>{h.changed_by_name}</strong>{" "}
            {h.from_status ? `moved it from ${label(h.from_status)} to ${label(h.to_status)}` : "submitted it"}
            {h.comment && <span className="comment">“{h.comment}”</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EpisodeTable({ episodes, action, selectable }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {selectable && <th></th>}
            <th>Episode</th>
            <th>Robot</th>
            <th>Task</th>
            <th>Recorded</th>
            <th className="num">Seconds</th>
            <th>Quality</th>
            {action && <th></th>}
          </tr>
        </thead>
        <tbody>
          {episodes.map((ep) => (
            <tr key={ep.episode_id}>
              {selectable && <td>{selectable(ep)}</td>}
              <td>{ep.episode_id}</td>
              <td>{ep.robot_id}</td>
              <td>{ep.task_name}</td>
              <td>{new Date(ep.recorded_at).toLocaleDateString()}</td>
              <td className="num">{ep.duration_seconds}</td>
              <td><span className={`quality ${ep.quality}`}>{ep.quality}</span></td>
              {action && <td>{action(ep)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
