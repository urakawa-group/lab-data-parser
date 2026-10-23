"""Read the LabVIEW process log of building 67, box 5 (DRIFTS, ``box5_drifts_v02.vi``).

One tab-separated ``.txt`` per start, named ``%Y-%m-%d_%H-%M-%S.txt``; a
``timestamp`` column (``%d-%m-%Y %H:%M:%S``, local time) and one column per
reading, comma decimals, no units and no setpoints in the file::

    timestamp  Reactor T PV  Analytic P PV  Vent P PV  F1 He PV ... F2 Ar PV  Feed

The channel set changed over time (``F1 CO PV`` from 2026-07), so a folder
can mix files of both kinds: they are joined on the union of the channels.
A column not in :data:`CHANNEL_META` is skipped with a warning.

What the parser knows about a channel (unit, quantity, species) is ours, not
the file's; it is written in the notation of the lab-control day logs
(``degC``, ``bar(a)``, ``mLn/min``) so LabVIEW and box5-control logs compare
directly. LabVIEW's flow PV is the MFC's reading times its correction factor,
as box5-control's PV (see its ``docs/labview-inventory.md``), with one
exception: v02 multiplies ``F2 Ar`` by F1-He's factor (1.123 instead of
1.149), so every logged ``F2 Ar PV`` is 2.3 % low; ``ProcessData.scale``
corrects it. ``Vent P`` is in bar(g), as LabVIEW worked; box5-control logs
bar(a).

:data:`BOX5_CONTROL_TAGS` maps the LabVIEW names onto the tags of
box5-control, for ``ProcessData.rename_channels``.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TIMEZONE = "Europe/Amsterdam"
LOG_SUFFIXES = (".txt", ".csv", ".ab")

# column -> what we know about the channel; the tag is the column without " PV"
CHANNEL_META: dict[str, dict[str, Any]] = {
    "Reactor T PV": {"quantity": "temperature", "unit": "degC", "kind": "controller", "description": "DRIFTS cell"},
    "Analytic P PV": {"quantity": "pressure", "unit": "bar(a)", "kind": "controller", "description": "analytic back-pressure controller"},
    "Vent P PV": {"quantity": "pressure", "unit": "bar(g)", "kind": "controller", "description": "vent back-pressure controller"},
    "F1 He PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "He", "feed": 1},
    "F1 H2 PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "H2", "feed": 1},
    "F1 CO2 PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "CO2", "feed": 1},
    # only in logs written from 2026-07 on (a CO controller was added to feed 1)
    "F1 CO PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "CO", "feed": 1},
    "F2 He PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "He", "feed": 2},
    "F2 H2 PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "H2", "feed": 2},
    "F2 CO2 PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "CO2", "feed": 2},
    "F2 Ar PV": {"quantity": "flow", "unit": "mLn/min", "kind": "controller", "species": "Ar", "feed": 2},
    "Feed": {"quantity": "feed", "unit": "feed", "kind": "indicator", "description": "feed on the cell, 1 or 2"},
}

# LabVIEW tag -> box5-control tag (box5-control settings/box5.example.toml, 2026-10-23)
BOX5_CONTROL_TAGS: dict[str, str] = {
    "Reactor T": "Cell T",
    "Analytic P": "BPR Analytic",
    "Vent P": "BPR Vent",
    "F1 He": "F1-1-He",
    "F1 H2": "F1-2-H2",
    "F1 CO2": "F1-3-CO2",
    "F1 CO": "F1-4-CO",
    "F2 He": "F2-1-He",
    "F2 H2": "F2-2-H2",
    "F2 CO2": "F2-3-CO2",
    "F2 Ar": "F2-5-Ar",
    "Feed": "Valve",
}


def tag_of(column: str) -> str:
    """Return the channel tag of a LabVIEW column: the name without its ``" PV"``.

    Parameters
    ----------
    column : str
        The column name, e.g. ``"F1 He PV"``.

    Returns
    -------
    str
        The tag, e.g. ``"F1 He"``.
    """
    return column.removesuffix(" PV")


def read(
    path: str | Path,
    *,
    sep: str = "\t",
    timezone: Optional[str] = TIMEZONE,
    keep_unknown_channels: bool = False,
) -> dict[str, Any]:
    """Read one LabVIEW log, or every log of a folder in file-name order.

    Parameters
    ----------
    path : str or pathlib.Path
        A log file or a folder of them (``.txt``, ``.csv``, ``.ab``).
    sep : str, optional
        Column separator (default is a tab).
    timezone : str or None, optional
        The zone the local timestamps were written in (default is
        ``"Europe/Amsterdam"``); ``None`` leaves them naive.
    keep_unknown_channels : bool, optional
        Read a column missing from :data:`CHANNEL_META` with empty metadata
        instead of skipping it (default is ``False``).

    Returns
    -------
    dict
        The parser record of :mod:`lab_data_parser.processdata`: ``data``
        (``time`` in UTC, ``channels``, ``fields`` with ``pv`` and ``status``,
        ``rows`` with ``session``: one session per file, i.e. per LabVIEW start)
        and ``meta`` (``set_up``, ``timezone``, ``sessions``, ``source_files``).

    Raises
    ------
    FileNotFoundError
        If the path does not exist or a folder holds no log file.
    ValueError
        If a file has no ``timestamp`` column.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        files = [path / f for f in sorted(os.listdir(path)) if f.endswith(LOG_SUFFIXES)]
        if not files:
            raise FileNotFoundError(f"No .txt, .csv or .ab log files found in directory {path}")
    else:
        files = [path]

    frames = []
    for number, file in enumerate(files, start=1):
        frame = pd.read_csv(file, sep=sep, header=0)
        if "timestamp" not in frame.columns:
            raise ValueError(f"{file.name}: expected a 'timestamp' column, got {list(frame.columns)}")
        frame = frame.dropna(subset=["timestamp"])  # the trailing blank line
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="%d-%m-%Y %H:%M:%S")
        if timezone is not None:
            # "infer" resolves the repeated hour of the autumn change from the monotonic log
            frame["timestamp"] = frame["timestamp"].dt.tz_localize(timezone, ambiguous="infer")
        frame["session"] = number
        frames.append(frame)

    columns = list(dict.fromkeys(c for f in frames for c in f.columns if c not in ("timestamp", "session")))
    mixed = {f.name: sorted(set(columns) - set(fr.columns)) for f, fr in zip(files, frames) if set(columns) - set(fr.columns)}
    if mixed:
        logger.warning("Log files in %s do not share the same channels; the missing ones are NaN: %s", path, mixed)
    unknown = [c for c in columns if c not in CHANNEL_META]
    if unknown and not keep_unknown_channels:
        logger.warning(
            "Skipping %d unknown channel(s) %s. The LabView export gained columns this parser does not "
            "know; add them to CHANNEL_META in processdata/labview/b67box5.py, or pass "
            "keep_unknown_channels=True.", len(unknown), unknown,
        )
        columns = [c for c in columns if c in CHANNEL_META]
    elif unknown:
        logger.warning("No metadata for channel(s) %s; reading them in with empty metadata.", unknown)

    df = pd.concat(frames, axis=0, ignore_index=True)
    time = df["timestamp"]
    time_utc = time.dt.tz_convert("UTC").dt.tz_localize(None) if time.dt.tz is not None else time
    pv = np.column_stack([_to_numeric(df[c]) if c in df else np.full(len(df), np.nan) for c in columns]) \
        if columns else np.empty((len(df), 0))
    status = np.where(np.isnan(pv), 3, 0).astype("int8")  # idle where a file did not record the channel
    channels = [{"tag": tag_of(c), "column": c, **CHANNEL_META.get(c, {})} for c in columns]
    sessions = [
        {"session": n, "tos_start": _first(frame["timestamp"]), "files": [file.name]}
        for n, (file, frame) in enumerate(zip(files, frames), start=1)
    ]
    logger.info("Read %d rows and %d channels from %d LabVIEW log(s)", len(df), len(columns), len(files))
    return {
        "data": {
            "time": time_utc.to_numpy(dtype="datetime64[ns]"),
            "channels": channels,
            "fields": {"pv": pv, "status": status},
            "rows": {"session": df["session"].to_numpy(dtype="int16")},
        },
        "meta": {
            "format": "LabVIEW box5_drifts_v02 log",
            "set_up": "box5",
            "timezone": timezone,
            "sessions": sessions,
            "source_files": [str(f) for f in files],
        },
    }


def _first(timestamps: pd.Series) -> Optional[str]:
    from lab_data_parser._time import encode_tos_start

    return encode_tos_start(timestamps.iloc[0]) if len(timestamps) else None


def _to_numeric(series: pd.Series) -> np.ndarray:
    """Convert a raw log column to float, accepting comma or dot as decimal separator."""
    if pd.api.types.is_numeric_dtype(series):
        return series.to_numpy(dtype=float)
    return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce").to_numpy(dtype=float)
