// Small wrapper around fetch. Every call goes to /api/..., adds the login
// token, and turns error responses into a readable message.

const TOKEN_KEY = "desk_token";

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

// FastAPI errors come in a few shapes; this turns each one into one sentence.
function errorMessage(body, status) {
  const detail = body?.detail;
  if (!detail) return `Request failed (${status})`;
  if (typeof detail === "string") return detail;
  if (detail.problems) return `${detail.message}: ${detail.problems.join("; ")}`;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ");
  return JSON.stringify(detail);
}

export async function api(path, { method = "GET", body, file } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (file) {
    payload = new FormData();
    payload.append("file", file);
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`/api${path}`, { method, headers, body: payload });

  if (res.status === 401 && token) {
    // token expired or user deactivated: go back to the login screen
    setToken(null);
    window.location.reload();
  }
  if (res.status === 204) return null;

  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorMessage(data, res.status));
  return data;
}
