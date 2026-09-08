"""Real photographs for each machine type.

WHY A MANIFEST RATHER THAN HARDCODED PATHS
------------------------------------------
The browse page shows a machine TYPE (a tractor, a rotavator), not one
person's listing. A type needs its own representative photos, separate from
whatever a particular owner happened to upload.

Photos are dropped into:

    frontend/public/machinery/<machine_key>/<anything>.jpg

and this module discovers them at startup. Adding pictures is therefore a
matter of copying files into a folder — no code change, no redeploy of the
backend, no editing a list by hand.

FALLBACK BEHAVIOUR
------------------
A type with no photos yet returns an empty list, and the frontend falls back
to the SVG illustration it already draws. So the page never shows a broken
image icon, which is what was happening on the browse grid when a listing
pointed at a missing upload.

WHAT IS NOT HERE
----------------
No stock photos are bundled with this project. Agricultural stock imagery is
almost always licensed, and shipping someone else's photographs inside a
farmer-facing app would be a copyright problem, not a shortcut. The folders
are created empty and ready.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

log = logging.getLogger("agri.machinery.photos")

# Resolved relative to the repo root so it works from either backend/ or root.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]                      # .../sustainable-agriculture
PHOTO_ROOT = _ROOT / "frontend" / "public" / "machinery"

# Served by Vite straight from public/, so the URL mirrors the folder path.
URL_PREFIX = "/machinery"

VALID_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def photos_for(machine_key: str) -> List[str]:
    """Every photo URL available for one machine type, sorted by filename.

    Sorting by name means an owner can control ordering with a numeric
    prefix (01-front.jpg, 02-side.jpg) rather than depending on filesystem
    order, which differs between Windows and Linux.
    """
    if not machine_key:
        return []

    folder = PHOTO_ROOT / machine_key
    try:
        if not folder.is_dir():
            return []
        files = sorted(
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in VALID_SUFFIXES
        )
        return [f"{URL_PREFIX}/{machine_key}/{f.name}" for f in files]
    except OSError as exc:
        log.warning("could not read photos for %s: %s", machine_key, exc)
        return []


def all_photos() -> Dict[str, List[str]]:
    """Photo lists for every machine type that has a folder."""
    from app.services.machinery import MACHINERY_KB
    return {key: photos_for(key) for key in MACHINERY_KB}


def coverage() -> Dict[str, object]:
    """Which types still need photographs. Useful while populating them."""
    from app.services.machinery import MACHINERY_KB

    counts = {key: len(photos_for(key)) for key in MACHINERY_KB}
    missing = [k for k, n in counts.items() if n == 0]
    return {
        "photo_root": str(PHOTO_ROOT),
        "url_prefix": URL_PREFIX,
        "counts": counts,
        "types_with_photos": len(counts) - len(missing),
        "types_total": len(counts),
        "missing": missing,
        "how_to_add": (
            f"Copy photographs into {PHOTO_ROOT}/<machine_key>/ using the "
            f"machine keys listed in counts. Any .jpg, .png or .webp file is "
            f"picked up automatically; prefix filenames with 01-, 02- to "
            f"control their order. No restart of the frontend is needed in "
            f"dev mode."),
    }


def ensure_folders() -> int:
    """Create an empty folder per machine type so the drop targets exist."""
    from app.services.machinery import MACHINERY_KB

    made = 0
    for key in MACHINERY_KB:
        folder = PHOTO_ROOT / key
        try:
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
                made += 1
        except OSError as exc:
            log.warning("could not create %s: %s", folder, exc)
    return made
