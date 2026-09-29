import { useEffect, useState } from "react";
import { api } from "./api.js";
import RequestList from "./RequestList.jsx";
import RequestDetail from "./RequestDetail.jsx";

const FILTERS = ["", "submitted", "in_progress", "delivered", "rejected", "accepted"];

export default function StaffPage() {
  const [requests, setRequests] = useState([]);
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  async function load() {
    setRequests(await api(status ? `/requests?status=${status}` : "/requests"));
  }

  useEffect(() => {
    load();
  }, [status]);

  return (
    <div className="split">
      <section className="panel">
        <div className="list-header">
          <h2>All requests</h2>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            {FILTERS.map((s) => (
              <option key={s} value={s}>{s ? s.replace("_", " ") : "Any status"}</option>
            ))}
          </select>
        </div>
        <RequestList requests={requests} selectedId={selectedId} onSelect={setSelectedId}
                     showClient emptyText="No requests match this filter." />
        <ImportBox />
      </section>
      <section className="panel">
        {selectedId ? (
          <RequestDetail requestId={selectedId} isStaff onChanged={load} />
        ) : (
          <p className="muted">Select a request to move it forward or assign episodes.</p>
        )}
      </section>
    </div>
  );
}

function ImportBox() {
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function upload() {
    setBusy(true);
    setError("");
    setReport(null);
    try {
      setReport(await api("/episodes/import", { method: "POST", file }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="import">
      <summary>Import episodes from CSV</summary>
      <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files[0])} />
      <button className="primary" disabled={!file || busy} onClick={upload}>
        {busy ? "Importing…" : "Import file"}
      </button>
      {error && <p className="error">{error}</p>}
      {report && (
        <div className="report">
          <p>
            Read <strong>{report.rows_read}</strong> rows, imported <strong>{report.imported}</strong>,
            skipped <strong>{report.skipped}</strong>.
          </p>
          <ul>
            {Object.entries(report.skipped_by_reason).map(([reason, count]) => (
              <li key={reason}>{reason.replaceAll("_", " ")}: {count}</li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}
