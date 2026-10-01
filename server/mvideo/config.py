from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    library: Path
    state: Path
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    cache_bytes: int = 20 * 1024**3

    @classmethod
    def from_env(cls):
        return cls(Path(os.environ.get("MVIDEO_LIBRARY", r"L:\MusicVideos")),
                   Path(os.environ.get("MVIDEO_STATE", ".state")),
                   os.environ.get("MVIDEO_FFMPEG", "ffmpeg"),
                   os.environ.get("MVIDEO_FFPROBE", "ffprobe"),
                   int(os.environ.get("MVIDEO_CACHE_GB", "20")) * 1024**3)

    def prepare(self):
        root = self.library.resolve()
        state = self.state.resolve()
        if state == root or root in state.parents:
            raise ValueError("Application state must be outside the source library")
        state.mkdir(parents=True, exist_ok=True)
        for name in ("thumbnails", "playback", "artwork"):
            (state / name).mkdir(exist_ok=True)
