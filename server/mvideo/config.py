from dataclasses import dataclass
from pathlib import Path
import math
import os


@dataclass(frozen=True)
class Settings:
    library: Path
    state: Path
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    cache_bytes: int = 20 * 1024**3
    watch_mode: str = 'polling'
    watch_interval: float = 15
    file_stability_seconds: float = 5

    @classmethod
    def from_env(cls):
        return cls(Path(os.environ.get("MVIDEO_LIBRARY", r"L:\MusicVideos")),
                   Path(os.environ.get("MVIDEO_STATE", ".state")),
                   os.environ.get("MVIDEO_FFMPEG", "ffmpeg"),
                   os.environ.get("MVIDEO_FFPROBE", "ffprobe"),
                   int(os.environ.get("MVIDEO_CACHE_GB", "20")) * 1024**3,
                   os.environ.get('MVIDEO_WATCH_MODE', 'polling'),
                   float(os.environ.get('MVIDEO_WATCH_INTERVAL', '15')),
                   float(os.environ.get('MVIDEO_FILE_STABILITY_SECONDS', '5')))

    def prepare(self):
        if self.watch_mode not in {'polling', 'native', 'off'}:
            raise ValueError('Watch mode must be polling, native or off')
        if not math.isfinite(self.watch_interval) or self.watch_interval <= 0:
            raise ValueError('Watch interval must be positive')
        if not math.isfinite(self.file_stability_seconds) or self.file_stability_seconds < 0:
            raise ValueError('File stability seconds must be nonnegative')
        root = self.library.resolve()
        state = self.state.resolve()
        if state == root or root in state.parents:
            raise ValueError("Application state must be outside the source library")
        state.mkdir(parents=True, exist_ok=True)
        for name in ("thumbnails", "playback", "artwork"):
            (state / name).mkdir(exist_ok=True)
