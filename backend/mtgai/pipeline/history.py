"""Per-instance card-pool snapshots for the review->regen loop.

The re-entrant pipeline (see CLAUDE.md "Re-entrant pipeline / review->regen
loop") gives every looping-stage *instance* a stable identity, but the card pool
the verdicts are *about* lives in one mutable ``<asset>/cards/`` folder. A gate
stamps ``regen_reason``/``flagged_by`` flags; a later ``card_gen`` consumes and
clears them; by the time a downstream gate runs, the earlier flag-state is gone.
So an instance cannot be re-run faithfully from live state — you need the pool as
it stood on that instance's entry.

This module adds a write-once ``history/`` sidecar: one folder per instance
holding that instance's *output* (its ``cards/*.json`` +
``generation_progress.json``). Instance K's *entry* state is the output snapshot
of its immediate predecessor, so re-running K == restore the predecessor's
snapshot, then walk the engine forward from K (see
:func:`mtgai.pipeline.engine.rerun_instance`).

Design choices:

* **The live ``cards/`` folder stays the single working set** (always the loop
  tip). Downstream art/render stages — which have no concept of instances —
  read it unchanged, so they need zero changes.
* **Plain copies, not hardlinks** (~0.5 MB/instance, gitignored). Revisit only
  if I/O hurts.
* **``cards/_regen_archive/`` is excluded** from snapshots: it's a transient bag
  card_gen writes during regen, and history supersedes it.
* All operations run under the AI lock (the engine ``save_state`` seam, or a
  guarded endpoint), so there is never a concurrent writer to the live folder.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_DIRNAME = "history"
_CARDS_DIRNAME = "cards"
_PROGRESS_FILENAME = "generation_progress.json"
_REGEN_ARCHIVE = "_regen_archive"

# Stage_ids whose *instances* get an output snapshot: the four duplicable loop
# stages, plus ``lands`` — the last pre-loop stage that writes cards, so the
# backbone ``card_gen`` has an entry snapshot to restore from. Stages outside
# this set (mechanics, skeleton, finalize, art, render, ...) never snapshot.
SNAPSHOT_STAGES: frozenset[str] = frozenset(
    {"lands", "card_gen", "conformance", "balance", "ai_review"}
)

# The duplicable loop stages a user can re-run via the per-tab "Re-run" button —
# ``SNAPSHOT_STAGES`` minus the ``lands`` entry anchor (which has its own refresh
# and isn't part of the review->regen loop). Also the set the engine keeps at
# AUTO review_mode when re-appending the forward path, so the regen tail flows.
RERUNNABLE_STAGES: frozenset[str] = frozenset(
    {"card_gen", "conformance", "balance", "ai_review"}
)


def _asset_dir() -> Path:
    from mtgai.io.asset_paths import set_artifact_dir

    return set_artifact_dir()


def _history_root(asset: Path | None = None) -> Path:
    return (asset or _asset_dir()) / HISTORY_DIRNAME


def snapshot_dir(instance_id: str, asset: Path | None = None) -> Path:
    """Path to an instance's snapshot folder (``history/<instance_id>/``)."""
    return _history_root(asset) / instance_id


def snapshot_exists(instance_id: str, asset: Path | None = None) -> bool:
    """True if a usable snapshot (a ``cards/`` subfolder) exists for the instance."""
    return (snapshot_dir(instance_id, asset) / _CARDS_DIRNAME).is_dir()


def _rmtree_retry(path: Path) -> None:
    """``shutil.rmtree`` tolerant of a transient Windows lock (Defender / indexer).

    Mirrors the retry posture of :func:`mtgai.io.atomic.replace_with_retry`: a
    handful of exponential-backoff retries before giving up, since the on-access
    scanner / search indexer releases its handle within a beat.
    """
    if not path.exists():
        return
    delay = 0.05
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2


def snapshot_instance(instance_id: str, asset: Path | None = None) -> bool:
    """Copy the live card pool into ``history/<instance_id>/`` as this instance's output.

    Captures every top-level ``cards/*.json`` (the whole live working set,
    including the Lands tab's ``L-*``) + ``generation_progress.json``. The
    ``_regen_archive/`` subfolder is intentionally skipped (transient). Overwrites
    any prior snapshot for the id — a re-run re-emits on completion. Returns True
    if a snapshot was written, False if there were no live cards yet (nothing to
    capture — not an error).
    """
    asset = asset or _asset_dir()
    live_cards = asset / _CARDS_DIRNAME
    if not live_cards.is_dir():
        return False

    dest = snapshot_dir(instance_id, asset)
    _rmtree_retry(dest)
    dest_cards = dest / _CARDS_DIRNAME
    dest_cards.mkdir(parents=True, exist_ok=True)
    # Top-level *.json only — naturally excludes the _regen_archive/ subdir.
    for jf in live_cards.glob("*.json"):
        shutil.copy2(jf, dest_cards / jf.name)

    progress = asset / _PROGRESS_FILENAME
    if progress.exists():
        shutil.copy2(progress, dest / _PROGRESS_FILENAME)

    logger.info("Snapshotted instance %s", instance_id)
    return True


def restore_snapshot(instance_id: str, asset: Path | None = None) -> bool:
    """Restore ``history/<instance_id>/`` into the live card pool.

    Clears the live top-level ``cards/*.json`` and the transient
    ``cards/_regen_archive/`` (stale once a prior pool is restored), copies the
    snapshot's cards back, and round-trips ``generation_progress.json`` (restored
    if the snapshot had one, deleted otherwise). The Lands tab's ``L-*`` are part
    of the snapshot, so they come back too. Returns False if the snapshot is
    missing — the caller decides whether to fall back to a from-live re-run.
    """
    asset = asset or _asset_dir()
    src = snapshot_dir(instance_id, asset)
    src_cards = src / _CARDS_DIRNAME
    if not src_cards.is_dir():
        return False

    live_cards = asset / _CARDS_DIRNAME
    if live_cards.is_dir():
        for jf in live_cards.glob("*.json"):
            jf.unlink(missing_ok=True)
        _rmtree_retry(live_cards / _REGEN_ARCHIVE)
    live_cards.mkdir(parents=True, exist_ok=True)
    for jf in src_cards.glob("*.json"):
        shutil.copy2(jf, live_cards / jf.name)

    live_progress = asset / _PROGRESS_FILENAME
    snap_progress = src / _PROGRESS_FILENAME
    if snap_progress.exists():
        shutil.copy2(snap_progress, live_progress)
    else:
        live_progress.unlink(missing_ok=True)

    logger.info("Restored snapshot %s into live cards", instance_id)
    return True


def delete_snapshot(instance_id: str, asset: Path | None = None) -> None:
    """Remove an instance's snapshot folder (idempotent)."""
    _rmtree_retry(snapshot_dir(instance_id, asset))


def clear_all_history(asset: Path | None = None) -> None:
    """Remove the entire ``history/`` sidecar (idempotent)."""
    _rmtree_retry(_history_root(asset))
