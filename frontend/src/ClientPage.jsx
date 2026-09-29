import { useEffect, useState } from "react";
import { api } from "./api.js";
import RequestList from "./RequestList.jsx";
import RequestDetail from "./RequestDetail.jsx";

export default function ClientPage() {
  const [requests, setRequests] = useState([]);
  const [selectedId, setSelectedId] = useState(null);

  async function load() {
    setRequests(await api("/requests"));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="split">
      <section className="panel">
        <NewRequestForm
          onCreated={async (created) => {
            await load();
            setSelectedId(created.id);
          }}
        />
        <h2>My requests</h2>
        <RequestList requests={requests} selectedId={selectedId} onSelect={setSelectedId}
                     emptyText="You have no requests yet. Create one above." />
      </section>
      <section className="panel">
        {selectedId ? (
          <RequestDetail requestId={selectedId} isStaff={false} onChanged={load} />
        ) : (
          <p className="muted">Select a request to see its status and delivered episodes.</p>
        )}
      </section>
    </div>
  );
}

function NewRequestForm({ onCreated }) {
  const empty = { task_name: "", episodes_requested: 100, deadline: "", notes: "" };
  const [form, setForm] = useState(empty);
  const [error, setError] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  function update(field) {
    return (e) => setForm({ ...form, [field]: e.target.value });
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const created = await api("/requests", {
        method: "POST",
        body: { ...form, episodes_requested: Number(form.episodes_requested), notes: form.notes || null },
      });
      setForm(empty);
      onCreated(created);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="new-request" onSubmit={submit}>
      <h2>New request</h2>
      <label>
        Task
        <input value={form.task_name} onChange={update("task_name")} placeholder="e.g. pick cup" required maxLength={255} />
      </label>
      <div className="row">
        <label>
          Episodes
          <input type="number" min="1" max="100000" value={form.episodes_requested} onChange={update("episodes_requested")} required />
        </label>
        <label>
          Deadline
          <input type="date" min={today} value={form.deadline} onChange={update("deadline")} required />
        </label>
      </div>
      <label>
        Notes
        <textarea value={form.notes} onChange={update("notes")} rows={2} maxLength={5000} />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary">Submit request</button>
    </form>
  );
}
