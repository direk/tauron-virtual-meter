"""Storage namespace and resumable migration of this integration's files."""
from __future__ import annotations

import logging
from pathlib import Path

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def storage_key(entry_id: str, suffix: str) -> str:
    """HA Store supports subdirectories in its key."""
    return f"{DOMAIN}/{DOMAIN}.{entry_id}.{suffix}"


def migrate_storage(storage_root: Path, entry_id: str) -> dict[str, int]:
    """Move only this entry's legacy files, before loading any of its stores.

    Renames within .storage are atomic. Bytes, permissions and HA's storage
    envelope remain unchanged; HA does not validate the envelope's old key
    when loading, and writes the new key on the next save. Existing destination
    files win; differing legacy files are preserved under legacy/ for review.
    Running again completes a partially interrupted migration.
    """
    target = storage_root / DOMAIN
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    counts = {"moved": 0, "duplicates": 0, "conflicts": 0}
    prefix = f"{DOMAIN}.{entry_id}."
    for source in sorted(storage_root.iterdir()):
        if not source.name.startswith(prefix) or source.is_symlink() or not source.is_file():
            continue
        destination = target / source.name
        if not destination.exists():
            source.rename(destination)
            counts["moved"] += 1
        elif source.read_bytes() == destination.read_bytes():
            source.unlink()
            counts["duplicates"] += 1
        else:
            legacy_dir = target / "legacy"
            legacy_dir.mkdir(mode=0o700, exist_ok=True)
            backup = legacy_dir / source.name
            number = 1
            while backup.exists():
                backup = legacy_dir / f"{source.name}.{number}"
                number += 1
            source.rename(backup)
            counts["conflicts"] += 1
    return counts


async def async_migrate_storage(hass, entry_id):
    counts = await hass.async_add_executor_job(
        migrate_storage, Path(hass.config.path(".storage")), entry_id
    )
    if any(counts.values()):
        _LOGGER.info("Przeniesiono archiwum do podkatalogu %s: %s", DOMAIN, counts)
    if counts["conflicts"]:
        _LOGGER.warning("Zachowano %s starszych plików w %s/legacy; nowsze pliki docelowe pozostają aktywne",
                        counts["conflicts"], DOMAIN)
