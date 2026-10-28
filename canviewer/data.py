"""Log loading and per-signal sample access. No UI code lives here."""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from asammdf import MDF

logger = logging.getLogger(__name__)

# Timestamps above this are absolute Unix seconds (1973+); anything smaller is
# seconds since the MDF header start time. Logs recorded by python-can's MF4
# logger carry absolute timestamps and a header start time that is just the
# file-creation time, so the header must not be added to them.
EPOCH_THRESHOLD_S = 1e8

# Decoded series kept in memory; each is two arrays of the signal's samples.
_SERIES_CACHE_SIZE = 512

_MDF_MASTER_CHANNEL = 2  # asammdf channel_type of a time master channel
_CONVERTIBLE_SUFFIXES = {".asc", ".blf", ".trc", ".log", ".csv"}


@dataclass(frozen=True)
class SignalInfo:
    """DBC metadata for one decoded signal."""

    name: str
    message: str = ""
    message_id: Optional[int] = None
    unit: str = ""
    comment: str = ""
    senders: Tuple[str, ...] = ()
    choices: Optional[Dict[int, str]] = None


@dataclass(frozen=True)
class Series:
    """The raw samples of one signal. `ns` is UTC epoch nanoseconds."""

    ns: np.ndarray
    values: np.ndarray


@dataclass
class LogData:
    """A decoded log: signal catalog plus lazy per-signal sample access."""

    mdf: MDF
    catalog: Dict[str, SignalInfo]
    tz: str
    title: str = ""
    _cache: "OrderedDict[str, Series]" = field(default_factory=OrderedDict, repr=False)

    @property
    def signal_names(self) -> List[str]:
        return sorted(self.catalog)

    @property
    def messages(self) -> Dict[str, List[str]]:
        """Message name -> sorted signal names (signals without a message omitted)."""
        out: Dict[str, List[str]] = {}
        for info in self.catalog.values():
            if info.message:
                out.setdefault(info.message, []).append(info.name)
        return {m: sorted(s) for m, s in sorted(out.items())}

    def choices(self, name: str) -> Optional[Dict[int, str]]:
        info = self.catalog.get(name)
        return info.choices if info else None

    def series(self, name: str) -> Optional[Series]:
        """Return the signal's own samples (no resampling or interpolation)."""
        if name in self._cache:
            self._cache.move_to_end(name)
            return self._cache[name]
        if name not in self.catalog:
            return None
        try:
            sig = self.mdf.get(name)
        except Exception:  # noqa: BLE001 - a corrupt channel must not take the UI down
            logger.exception("could not read signal %s", name)
            return None
        ns = to_epoch_ns(np.asarray(sig.timestamps, dtype="float64"), self.mdf.start_time)
        series = Series(ns=ns, values=np.asarray(sig.samples))
        self._cache[name] = series
        while len(self._cache) > _SERIES_CACHE_SIZE:
            self._cache.popitem(last=False)
        return series

    def local_times(self, ns: np.ndarray) -> pd.DatetimeIndex:
        """UTC epoch ns -> tz-naive wall-clock times in the display timezone.

        Plotly serialises tz-aware values without their offset anyway, so the
        wall-clock form is used throughout and `local_to_ns` inverts it.
        """
        return pd.to_datetime(ns, unit="ns", utc=True).tz_convert(self.tz).tz_localize(None)

    def local_to_ns(self, text: str) -> Optional[int]:
        """Parse a Plotly x value (display-timezone wall clock) to UTC epoch ns."""
        try:
            ts = pd.Timestamp(text)
            if ts.tzinfo is None:
                ts = ts.tz_localize(self.tz, ambiguous=True, nonexistent="shift_forward")
            return int(ts.value)
        except (ValueError, TypeError):
            return None


def to_epoch_ns(timestamps: np.ndarray, start_time: Optional[pd.Timestamp]) -> np.ndarray:
    """Convert MDF timestamps (seconds) to UTC epoch nanoseconds."""
    if timestamps.size == 0:
        return np.empty(0, dtype="int64")
    offset = 0.0
    if timestamps[0] < EPOCH_THRESHOLD_S and start_time is not None:
        offset = start_time.timestamp()
    return np.rint((timestamps + offset) * 1e9).astype("int64")


def convert_to_mf4(path: Path, cache_dir: Path) -> Path:
    """Return an .mf4 for `path`, converting text/BLF logs into `cache_dir`.

    .mf4 files are used in place. Conversions are cached by file name, size and
    mtime so an edited log is never served stale.
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".mf4", ".mdf"}:
        return path
    if path.suffix.lower() not in _CONVERTIBLE_SUFFIXES:
        raise ValueError(f"unsupported log type {path.suffix!r} (use .mf4, .asc, .blf, .trc)")

    stat = path.stat()
    tag = hashlib.sha1(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:10]
    target = cache_dir / f"{path.stem}.{tag}.mf4"
    if target.is_file():
        return target

    import can  # imported lazily: only needed for non-MF4 inputs

    cache_dir.mkdir(parents=True, exist_ok=True)
    # Written under a temporary name (python-can picks the format from the
    # suffix, so it must still end in .mf4) so an interrupted conversion is
    # never mistaken for a finished one.
    partial = target.with_name(target.stem + ".partial.mf4")
    logger.info("converting %s -> %s", path, target)
    try:
        with can.LogReader(str(path), relative_timestamp=False) as reader:
            with can.Logger(str(partial)) as writer:
                # python-can would subtract the first timestamp; keep them absolute.
                writer._start_time = 0  # type: ignore[attr-defined]
                for msg in reader:
                    writer(msg)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _catalog_from_dbc(dbc_path: Path, present: set) -> Dict[str, SignalInfo]:
    """Signal metadata for every DBC signal that is actually in the log."""
    import cantools

    db = cantools.database.load_file(str(dbc_path))
    catalog: Dict[str, SignalInfo] = {}
    for msg in db.messages:
        for sig in msg.signals:
            if sig.name not in present or sig.name in catalog:
                continue
            choices = (
                {int(k): str(v) for k, v in sig.choices.items()} if sig.choices else None
            )
            catalog[sig.name] = SignalInfo(
                name=sig.name,
                message=msg.name,
                message_id=msg.frame_id,
                unit=sig.unit or "",
                comment=(sig.comment or "").strip(),
                senders=tuple(msg.senders),
                choices=choices,
            )
    return catalog


def load_log(
    path: str,
    dbc: str,
    tz: str = "UTC",
    cache_dir: Optional[Path] = None,
    title: Optional[str] = None,
) -> LogData:
    """Decode `path` against `dbc` and return a `LogData`."""
    cache_dir = cache_dir or Path.home() / ".canviewer-cache"
    mf4 = convert_to_mf4(Path(path), cache_dir)
    dbc_path = Path(dbc).expanduser()
    if not dbc_path.is_file():
        raise FileNotFoundError(f"DBC not found: {dbc_path}")

    raw = MDF(str(mf4))
    mdf = raw.extract_bus_logging(database_files={"CAN": [(str(dbc_path), 0)]})
    mdf.configure(raise_on_multiple_occurrences=False)

    present = {
        ch.name
        for group in mdf.groups
        for ch in group["channels"]
        if ch.channel_type != _MDF_MASTER_CHANNEL
    }
    catalog = _catalog_from_dbc(dbc_path, present)
    if not catalog:
        raise ValueError(f"no signals in {path} decode against {dbc_path}")
    return LogData(mdf=mdf, catalog=catalog, tz=tz, title=title or Path(path).name)
