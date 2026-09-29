import { useEffect, useState } from "react";
import { api } from "./api.js";
import { EpisodeTable } from "./RequestDetail.jsx";

// Lets an operator find free episodes (filter by task and quality),
// tick some, and assign them to the request in one go.
export default function EpisodePicker({ request, onAssigned }) {
  const [taskNames, setTaskNames] = useState([]);
  const [taskName, setTaskName] = useState("");
  const [quality, setQuality] = useState("");
  const [result, setResult] = useState({ total: 0, items: [] });
  const [selected, setSelected] = useState(new Set());
  const [error, setError] = useState("");

  useEffect(() => {
    api("/episodes/task-names").then((names) => {
      setTaskNames(names);
      // start with the request's own task if we have episodes for it
      if (names.includes(request.task_name.toLowerCase())) setTaskName(request.task_name.toLowerCase());
    });
  }, [request.id]);

  async function search() {
    const params = new URLSearchParams({ unassigned_only: "true", limit: "50" });
    if (taskName) params.set("task_name", taskName);
    if (quality) params.set("quality", quality);
    else params.set("assignable_only", "true");
    try {
      setResult(await api(`/episodes?${params}`));
      setSelected(new Set());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    search();
  }, [taskName, quality]);

  function toggle(id) {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  }

  async function assign() {
    setError("");
    try {
      await api(`/requests/${request.id}/assignments`, {
        method: "POST",
        body: { episode_ids: [...selected] },
      });
      await search();
      onAssigned();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="picker">
      <h3>Add episodes</h3>
      <div className="filters">
        <label>
          Task
          <select value={taskName} onChange={(e) => setTaskName(e.target.value)}>
            <option value="">Any task</option>
            {taskNames.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          Quality
          <select value={quality} onChange={(e) => setQuality(e.target.value)}>
            <option value="">Good or usable</option>
            <option value="good">Good</option>
            <option value="usable">Usable</option>
            <option value="bad">Bad (cannot be assigned)</option>
          </select>
        </label>
        <button className="primary" disabled={selected.size === 0} onClick={assign}>
          Assign {selected.size || ""} selected
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Showing {result.items.length} of {result.total} unassigned episodes.
      </p>
      <EpisodeTable
        episodes={result.items}
        selectable={(ep) => (
          <input
            type="checkbox"
            aria-label={`Select ${ep.episode_id}`}
            checked={selected.has(ep.episode_id)}
            onChange={() => toggle(ep.episode_id)}
          />
        )}
      />
    </section>
  );
}
