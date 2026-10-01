import React from "react";
import { Film } from "lucide-react";
export const DRAG = "application/x-mvideo-track";
export function Thumb({ video }) {
  return (
    <div className="thumb">
      {video.thumbnail && video.available !== false ? (
        <img
          draggable={false}
          src={video.thumbnail}
          alt=""
          loading="lazy"
          onError={(e) => {
            e.currentTarget.hidden = true;
          }}
        />
      ) : null}
      <Film aria-hidden="true" />
    </div>
  );
}
export function TrackText({ video }) {
  return (
    <div className="track-text">
      <strong>{video.artist || "Artist unidentified"}</strong>
      <span>{video.title}</span>
      {video.available === false && (
        <small className="warning">Unavailable · skipped during playback</small>
      )}
    </div>
  );
}
