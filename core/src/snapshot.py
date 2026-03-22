"""
Snapshot manager for OntoSkills Skill Drift Detector.

Automatically saves a copy of the ontology after each successful compilation,
maintaining a history of the last N snapshots to enable semantic diffing.
"""

import shutil
import hashlib
from pathlib import Path
from datetime import datetime

SNAPSHOT_DIR = Path('.ontoskills/snapshots')


def save_snapshot(ttl_path: Path) -> Path:
    """Save a timestamped snapshot of the ontology file."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    content = ttl_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()[:8]
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = SNAPSHOT_DIR / f'skills_{ts}_{sha}.ttl'

    shutil.copy2(ttl_path, dest)
    _prune_snapshots(keep=10)
    return dest


def get_latest_snapshot() -> Path | None:
    """Return the second-to-last snapshot (the previous version before the latest compile)."""
    snaps = sorted(SNAPSHOT_DIR.glob('*.ttl')) if SNAPSHOT_DIR.exists() else []
    return snaps[-2] if len(snaps) >= 2 else (snaps[0] if snaps else None)


def _prune_snapshots(keep: int = 10):
    """Delete oldest snapshots, keeping only the most recent `keep` files."""
    snaps = sorted(SNAPSHOT_DIR.glob('*.ttl'))
    for old in snaps[:-keep]:
        old.unlink()
