// Shows where a request is in the workflow:
// submitted -> in progress -> delivered -> accepted (or rejected)
const STEPS = ["submitted", "in_progress", "delivered", "accepted"];

export function label(status) {
  return status.replace("_", " ");
}

export default function StatusTrack({ status }) {
  // a rejected request sits on the "delivered" step, marked as rejected
  const current = status === "rejected" ? STEPS.indexOf("delivered") : STEPS.indexOf(status);

  return (
    <ol className="track" aria-label={`Status: ${label(status)}`}>
      {STEPS.map((step, i) => {
        let state = i < current ? "done" : i === current ? "current" : "todo";
        const isRejected = status === "rejected" && i === current;
        return (
          <li key={step} className={`${state} ${isRejected ? "rejected" : ""}`}>
            {isRejected ? "rejected" : label(step)}
          </li>
        );
      })}
    </ol>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{label(status)}</span>;
}
