import React, { useEffect, useRef, useState } from "react";
import { Search, Check, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { request } from "../api";
import { Thumb, TrackText, DRAG } from "./Track";
export default function LibraryPanel({
  draft,
  locked,
  onAdd,
  onTracks,
  onError,
}) {
  const [q, setQ] = useState(""),
    [field, setField] = useState("all"),
    [decade, setDecade] = useState("");
  const [offset, setOffset] = useState(0),
    [page, setPage] = useState(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const revision = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const timer = setTimeout(async () => {
      const params = new URLSearchParams({ q, field, limit: 24, offset });
      if (decade) params.set("decade", decade);
      if (offset && revision.current !== null)
        params.set("revision", revision.current);
      try {
        const result = await request("/api/videos?" + params, {
          signal: controller.signal,
        });
        setPage(result);
        revision.current = result.revision;
        onTracks(result.items);
      } catch (error) {
        if (error.name !== "AbortError") {
          setPage(null);
          setError(error.message);
          onError(error);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q, field, decade, offset, retry]);
  function filter(setter, value) {
    setter(value);
    setOffset(0);
    revision.current = null;
  }
  return (
    <section className="library-panel" aria-labelledby="library-heading">
      <h2 id="library-heading">Your library</h2>
      <div className="filters">
        <div className="search">
          <Search size={18} />
          <input
            aria-label="Search artists or songs"
            placeholder="Search artists or songs"
            value={q}
            onChange={(e) => filter(setQ, e.target.value)}
          />
        </div>
        <select
          aria-label="Search field"
          value={field}
          onChange={(e) => filter(setField, e.target.value)}
        >
          <option value="all">All fields</option>
          <option value="artist">Artist</option>
          <option value="title">Song title</option>
          <option value="year">Year</option>
        </select>
        <select
          aria-label="Decade"
          value={decade}
          onChange={(e) => filter(setDecade, e.target.value)}
        >
          <option value="">All decades</option>
          {Array.from({ length: 15 }, (_, i) => 1880 + i * 10).map((year) => (
            <option key={year} value={year}>
              {year}s
            </option>
          ))}
        </select>
      </div>
      <p className="result-count" aria-live="polite">
        {loading
          ? "Searching…"
          : page
            ? `${page.total.toLocaleString()} results`
            : "Library unavailable"}
      </p>
      {error && (
        <div role="alert">
          <p className="warning">{error}</p>
          <button
            onClick={() => {
              setOffset(0);
              revision.current = null;
              setRetry((x) => x + 1);
            }}
          >
            Retry / refresh
          </button>
        </div>
      )}
      <div className="library-tracks" aria-busy={loading}>
        {!loading &&
          page?.items.map((video) => {
            const included = draft?.items.some((item) => item.id === video.id);
            return (
              <article
                className="library-track"
                key={video.id}
                draggable={!!draft && !locked}
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "copyMove";
                  e.dataTransfer.setData(DRAG, video.id);
                }}
              >
                <Thumb video={video} />
                <div>
                  <TrackText video={video} />
                  <span className="year">{video.year || "Year unknown"}</span>
                </div>
                <button
                  className={included ? "" : "primary"}
                  disabled={!draft || locked || included}
                  onClick={() => onAdd(video)}
                  aria-label={`${included ? "Added" : "Add"} ${video.artist || ""} — ${video.title}`}
                >
                  {included ? <Check size={17} /> : <Plus size={17} />}
                  <span>{included ? "Added" : "Add"}</span>
                </button>
              </article>
            );
          })}
        {!loading && page?.total === 0 && (
          <p className="empty">
            No matching videos. Try another artist, song or decade.
          </p>
        )}
      </div>
      <nav className="pagination" aria-label="Library pages">
        <button
          disabled={loading || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 24))}
        >
          <ChevronLeft size={16} />
          Previous
        </button>
        <span>
          {page
            ? `Page ${Math.floor(offset / 24) + 1} of ${Math.max(1, Math.ceil(page.total / 24))}`
            : ""}
        </span>
        <button
          disabled={loading || page?.next_offset == null}
          onClick={() => setOffset(page.next_offset)}
        >
          Next
          <ChevronRight size={16} />
        </button>
      </nav>
    </section>
  );
}
