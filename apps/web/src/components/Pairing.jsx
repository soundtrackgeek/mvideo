import React, { useState } from "react";
import { request } from "../api";
export default function Pairing({ onPaired }) {
  const [code, setCode] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function pair(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = await request("/api/pair", {
        method: "POST",
        body: { code },
      });
      sessionStorage.setItem("mvideo-session", value.token);
      onPaired();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="pairing">
      <div>
        <h1>
          Your collection.
          <br />
          Your running order.
        </h1>
        <p>
          Create a mix, rediscover a favourite,
          <br />
          then watch it on Apple TV.
        </p>
      </div>
      <form onSubmit={pair}>
        <h2>Connect to your library</h2>
        <p>
          Enter a fresh eight-digit pairing code from your mvideo server. This
          browser tab connects to the server you opened.
        </p>
        <label htmlFor="pair-code">Pairing code</label>
        <input
          id="pair-code"
          autoComplete="one-time-code"
          inputMode="numeric"
          pattern="[0-9]{8}"
          maxLength={8}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          required
        />
        <button className="primary" disabled={busy || code.length !== 8}>
          {busy ? "Connecting…" : "Connect library"}
        </button>
        {error && (
          <p role="alert" className="warning">
            {error}
          </p>
        )}
        <small>
          On the PC, run scripts/windows-start.ps1 -Pair. Sessions are shared
          with this tab only.
        </small>
      </form>
    </main>
  );
}
