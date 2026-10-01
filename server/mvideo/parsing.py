"""Conservative filename extraction; uncertainty is data, never a guessed identity."""
from pathlib import Path
import re
import unicodedata


def parse_filename(name: str) -> dict:
    raw = Path(name).stem
    text = unicodedata.normalize("NFC", raw).strip()
    warnings = []
    year = None
    years = re.findall(r"\((\d{4})\)", text)
    suffix = re.search(r"\s*\((\d{4})\)$", text)
    if suffix and len(years) == 1 and 1888 <= int(suffix[1]) <= 2100:
        year = int(suffix[1])
        text = text[:suffix.start()].strip()
    else:
        warnings.append("ambiguous_year" if years else "missing_year")
    parts = text.split(" - ")
    artist = None
    title = text
    if len(parts) == 2 and all(x.strip() for x in parts):
        artist, title = [x.strip() for x in parts]
    elif len(parts) > 2:
        # A spaced hyphen may be in either the artist or song. Keep the full title.
        warnings.append("ambiguous_separator")
    else:
        warnings.append("missing_artist")
    return dict(artist=artist, title=title, year=year, raw_name=raw, warnings=warnings)
