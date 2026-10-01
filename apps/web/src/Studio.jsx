import React, { useState, useEffect, useRef } from "react";
import { Plus } from "lucide-react";
import { request } from "./api";
import { placeTrack, draftKey } from "./playlist";
import LibraryPanel from "./components/LibraryPanel";
import PlaylistEditor from "./components/PlaylistEditor";
export default function Studio({ onDisconnect }) {
  const [playlists, setPlaylists] = useState([]),
    [draft, setDraft] = useState(null),
    [saved, setSaved] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [newName, setNewName] = useState(null);
  const tracks = useRef(new Map()),
    generation = useRef(0),
    dirty = !!draft && draftKey(draft) !== saved;
  useEffect(() => {
    refresh().catch(handleError);
  }, []);
  useEffect(() => {
    const handler = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  function handleError(error) {
    setError(
      error.status === 401
        ? "Session expired. Disconnect and pair again. Your unsaved playlist is still here."
        : error.message,
    );
  }
  async function refresh() {
    const value = await request("/api/playlists");
    setPlaylists(value.items);
    return value.items;
  }
  function mayDiscard() {
    return (
      !dirty || window.confirm("Discard unsaved changes to this playlist?")
    );
  }
  async function open(id) {
    if (busy || !mayDiscard()) return;
    const current = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const value = await request("/api/playlists/" + id);
      if (generation.current === current) {
        setDraft(value);
        setSaved(draftKey(value));
      }
    } catch (error) {
      handleError(error);
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  async function create(event) {
    event.preventDefault();
    if (busy || !mayDiscard()) return;
    setBusy(true);
    setError("");
    try {
      const value = await request("/api/playlists", {
        method: "POST",
        body: { name: newName.trim() },
      });
      const next = { ...value, items: [] };
      setDraft(next);
      setSaved(draftKey(next));
      setNewName(null);
      await refresh();
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const value = await request("/api/playlists/" + draft.id, {
        method: "PUT",
        body: {
          name: draft.name,
          description: draft.description,
          ids: draft.items.map((v) => v.id),
          version: draft.version,
        },
      });
      const next = { ...draft, ...value };
      setDraft(next);
      setSaved(draftKey(next));
      await refresh();
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (
      !window.confirm(
        `Delete “${draft.name}”? This removes the playlist; your videos stay in the library.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await request(
        "/api/playlists/" + draft.id + "?version=" + draft.version,
        { method: "DELETE" },
      );
      setDraft(null);
      setSaved("");
      await refresh();
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <header>
        <div className="brand">mvideo</div>
        <span className="app-title">Playlist studio</span>
        <div className="connection">
          <span>
            <i />
            Connected
          </span>
          <button
            disabled={busy}
            onClick={() => {
              if (mayDiscard()) onDisconnect();
            }}
          >
            Disconnect
          </button>
        </div>
      </header>
      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button
            disabled={busy}
            onClick={() => {
              refresh()
                .then(() => setError(""))
                .catch(handleError);
            }}
          >
            Refresh playlists
          </button>
        </div>
      )}
      <div className="studio">
        <aside>
          <h2>Playlists</h2>
          <button
            className="new-playlist"
            disabled={busy}
            onClick={() => setNewName("")}
          >
            <Plus size={18} />
            New playlist
          </button>
          {newName !== null && (
            <form className="new-form" onSubmit={create}>
              <input
                aria-label="New playlist name"
                autoFocus
                maxLength={120}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Playlist name"
              />
              <div>
                <button className="primary" disabled={busy || !newName.trim()}>
                  Create
                </button>
                <button type="button" onClick={() => setNewName(null)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
          <nav aria-label="Playlists">
            {playlists.map((p) => (
              <button
                key={p.id}
                aria-current={p.id === draft?.id ? "page" : undefined}
                disabled={busy}
                onClick={() => open(p.id)}
              >
                {p.name}
                <small>{p.available_count} videos</small>
              </button>
            ))}
          </nav>
          {!playlists.length && (
            <p className="muted sidebar-empty">
              Your playlists will appear here.
            </p>
          )}
        </aside>
        <LibraryPanel
          draft={draft}
          locked={busy}
          onAdd={(video) =>
            setDraft({ ...draft, items: placeTrack(draft.items, video) })
          }
          onTracks={(items) => {
            tracks.current = new Map(items.map((v) => [v.id, v]));
          }}
          onError={(error) => {
            if (error.status === 401) handleError(error);
          }}
        />
        <PlaylistEditor
          key={draft?.id || "empty"}
          draft={draft}
          dirty={dirty}
          busy={busy}
          onChange={setDraft}
          onSave={save}
          onDelete={remove}
          onReload={() => open(draft.id)}
          tracks={tracks}
        />
      </div>
    </>
  );
}
