"""Image metadata extraction (resolution, GPS, DateTime) — soft Pillow dep.

PRIN-ING-13 / design-docs/05-ingest §5.7. Returns gracefully-degraded
results when Pillow is not installed; the album CLI still works, just
with "—" placeholders for missing fields.

The returned dict uses string-friendly types so it can be JSON-serialized
into attrs.album.sources without further conversion. EXIF data beyond
resolution / GPS / DateTime is intentionally NOT extracted — the source
files in raws/ remain the authoritative carrier of full EXIF
(design-docs/05-ingest §5.7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from PIL import Image  # type: ignore

    _PILLOW_OK = True
except Exception:  # ImportError or backend missing
    _PILLOW_OK = False


def _format_dms(dms: Any, ref: str) -> str:
    """Convert GPS DMS tuple to a string like '31.23450°N'.

    Accepts IFRational-like or numeric tuples. Returns empty string on failure.
    """
    try:
        nums = [float(x) for x in dms]
    except Exception:
        return ""
    if len(nums) < 2:
        return ""
    d, m = nums[0], nums[1]
    s = nums[2] if len(nums) > 2 else 0.0
    decimal = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return f"{decimal:.5f}"


def _format_gps(gps_info: dict) -> str | None:
    """Render GPS IFD dict to a human string 'lat°X, lon°Y' or None on failure."""
    try:
        lat_dms = gps_info.get(2)
        lon_dms = gps_info.get(4)
        lat_ref = gps_info.get(1) or "N"
        lon_ref = gps_info.get(3) or "E"
        if not lat_dms or not lon_dms:
            return None
        lat = _format_dms(lat_dms, lat_ref)
        lon = _format_dms(lon_dms, lon_ref)
        if not lat or not lon:
            return None
        return f"{lat}°{lat_ref}, {lon}°{lon_ref}"
    except Exception:
        return None


def _normalize_datetime(s: Any) -> str | None:
    """EXIF 'YYYY:MM:DD HH:MM:SS' → 'YYYY-MM-DD HH:MM:SS'. Pass-through otherwise."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if len(s) >= 19 and s[4] == ":" and s[7] == ":":
        return f"{s[:4]}-{s[5:7]}-{s[8:10]} {s[11:19]}"
    return s or None


def read_image_meta(path: str | Path) -> dict[str, Any]:
    """Read resolution, GPS, and DateTime from an image file.

    Returns dict with keys: width, height, gps, captured.
    Each value is the actual data when available, else None.
    Corrupt or unreadable images return all-None, NOT an exception —
    the album CLI depends on graceful degradation (PRIN-ING-13).
    """
    out: dict[str, Any] = {"width": None, "height": None, "gps": None, "captured": None}
    if not _PILLOW_OK:
        return out
    try:
        with Image.open(str(path)) as im:
            out["width"], out["height"] = im.size
            exif: Any = im.getexif() or {}
            if not exif:
                return out
            # 306 = DateTime; 0x9003 = DateTimeOriginal (preferred when present)
            dt = exif.get(0x9003) or exif.get(306)
            if dt:
                out["captured"] = _normalize_datetime(dt)
            # 0x8825 = GPSInfo IFD
            gps_ifd = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
            if gps_ifd:
                gps_str = _format_gps(dict(gps_ifd))
                if gps_str:
                    out["gps"] = gps_str
    except Exception:
        pass
    return out


def pillow_available() -> bool:
    """Probe for Pillow availability (used by tests / health checks)."""
    return _PILLOW_OK
