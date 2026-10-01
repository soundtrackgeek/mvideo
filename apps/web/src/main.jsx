import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { request } from "./api";
import Studio from "./Studio";
import Pairing from "./components/Pairing";
import "./style.css";
function App() {
  const [paired, setPaired] = useState(
      !!sessionStorage.getItem("mvideo-session"),
    ),
    [error, setError] = useState("");
  async function disconnect() {
    try {
      await request("/api/session", { method: "DELETE" });
    } catch (error) {
      setError(
        "Local session removed. Server revocation was unavailable; revoke it on the PC if needed.",
      );
    }
    sessionStorage.removeItem("mvideo-session");
    setPaired(false);
  }
  return paired ? (
    <Studio onDisconnect={disconnect} />
  ) : (
    <>
      <header>
        <div className="brand">mvideo</div>
        <span className="app-title">Playlist studio</span>
      </header>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <Pairing
        onPaired={() => {
          setError("");
          setPaired(true);
        }}
      />
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
