import React, { useState } from "react";
import { Check, GripVertical, ChevronUp, ChevronDown, X } from "lucide-react";
import { placeTrack, moveTrack } from "../playlist";
import { Thumb, TrackText, DRAG } from "./Track";
export default function PlaylistEditor({
  draft,
  dirty,
  busy,
  onChange,
  onSave,
  onDelete,
  onReload,
  tracks,
}) {
  const [renaming, setRenaming] = useState(false),
    [drop, setDrop] = useState(false);
  if (!draft)
    return (
      <section className="editor">
        <h2>Your next great mix.</h2>
        <p className="muted">
          Choose a playlist, or create one to start adding songs.
        </p>
      </section>
    );
  function dropTrack(event, beforeId = null) {
    event.preventDefault();
    event.stopPropagation();
    setDrop(false);
    if (busy) return;
    const id = event.dataTransfer.getData(DRAG),
      track = draft.items.find((v) => v.id === id) || tracks.current.get(id);
    if (track)
      onChange({ ...draft, items: placeTrack(draft.items, track, beforeId) });
  }
  function acceptDrag(event) {
    if (!busy && event.dataTransfer.types.includes(DRAG)) {
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "move";
      setDrop(true);
    }
  }
  return (
    <section
      className={`editor ${drop ? "drop-active" : ""}`}
      onDragEnter={acceptDrag}
      onDragOver={acceptDrag}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setDrop(false);
      }}
      onDrop={dropTrack}
      aria-labelledby="playlist-heading"
    >
      <div className="editor-heading">
        {renaming ? (
          <input
            autoFocus
            aria-label="Playlist name"
            maxLength={120}
            value={draft.name}
            disabled={busy}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            onBlur={() => setRenaming(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setRenaming(false);
            }}
          />
        ) : (
          <h2 id="playlist-heading">{draft.name}</h2>
        )}
        <span className={dirty ? "muted" : "saved"} role="status">
          {dirty ? (
            "Unsaved changes"
          ) : (
            <>
              <Check size={18} /> All changes saved
            </>
          )}
        </span>
      </div>
      <textarea
        aria-label="Playlist description"
        maxLength={2000}
        value={draft.description}
        disabled={busy}
        onChange={(e) => onChange({ ...draft, description: e.target.value })}
        placeholder="Describe this playlist"
      />
      <div className="editor-actions">
        <button disabled={busy} onClick={() => setRenaming(true)}>
          Rename
        </button>
        <button disabled={busy} onClick={onDelete}>
          Delete
        </button>
        <button
          className="primary save"
          disabled={
            busy || !dirty || !draft.name.trim() || draft.items.length > 5000
          }
          onClick={onSave}
        >
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
      <div className="playlist-note">
        <span>Drag songs here. Drag to reorder.</span>
        <span>{draft.items.length.toLocaleString()} videos</span>
      </div>
      <ol className="playlist-tracks">
        {draft.items.map((video, index) => (
          <li
            className="playlist-track"
            key={video.id}
            draggable={!busy}
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = "copyMove";
              e.dataTransfer.setData(DRAG, video.id);
            }}
            onDragEnd={() => setDrop(false)}
            onDragEnter={acceptDrag}
            onDragOver={acceptDrag}
            onDrop={(e) => dropTrack(e, video.id)}
          >
            <span className="position">{index + 1}</span>
            <GripVertical className="grip" size={19} />
            <Thumb video={video} />
            <TrackText video={video} />
            <span className="year">{video.year || "—"}</span>
            <div className="track-actions">
              <button
                aria-label={`Move ${video.title} up`}
                disabled={busy || index === 0}
                onClick={() =>
                  onChange({
                    ...draft,
                    items: moveTrack(draft.items, video.id, -1),
                  })
                }
              >
                <ChevronUp size={16} />
              </button>
              <button
                aria-label={`Move ${video.title} down`}
                disabled={busy || index === draft.items.length - 1}
                onClick={() =>
                  onChange({
                    ...draft,
                    items: moveTrack(draft.items, video.id, 1),
                  })
                }
              >
                <ChevronDown size={16} />
              </button>
              <button
                aria-label={`Remove ${video.title}`}
                disabled={busy}
                onClick={() =>
                  onChange({
                    ...draft,
                    items: draft.items.filter((v) => v.id !== video.id),
                  })
                }
              >
                <X size={16} />
              </button>
            </div>
          </li>
        ))}
      </ol>
      {!draft.items.length && (
        <p className="empty">
          Drop your first video here, or use Add in the library.
        </p>
      )}
      <button className="reload" disabled={busy} onClick={onReload}>
        Reload saved playlist
      </button>
    </section>
  );
}
