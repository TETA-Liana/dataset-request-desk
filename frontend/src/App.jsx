import { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import LoginForm from "./LoginForm.jsx";
import ClientPage from "./ClientPage.jsx";
import StaffPage from "./StaffPage.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));

  // If we already have a token (page refresh), ask the server who we are.
  useEffect(() => {
    if (!getToken()) return;
    api("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  function handleLogin(token, loggedInUser) {
    setToken(token);
    setUser(loggedInUser);
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  if (checking) return null;
  if (!user) return <LoginForm onLogin={handleLogin} />;

  return (
    <div className="app">
      <header className="topbar">
        <h1>Dataset Request Desk</h1>
        <div className="who">
          <span>
            {user.name} <span className="muted">({user.role})</span>
          </span>
          <button className="link" onClick={logout}>Log out</button>
        </div>
      </header>
      <main>{user.role === "client" ? <ClientPage user={user} /> : <StaffPage user={user} />}</main>
    </div>
  );
}
