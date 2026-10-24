"""Read the day files of the lab-control software (Box 2 high-pressure set-up, Box 5 DRIFTS).

Both rigs write one layout, specified in their ``docs/data-format.md`` and
shared as that written spec, never as code: one data file and one event file
per set-up and local day, every session (Connect to Disconnect) appended.

.. code-block:: text

    # format: box2-control day log, CSV, version 1
    # bench: box2                       (Box 5: "# set-up: box5")
    # timezone: Europe/Amsterdam
    # channel: {"tag": "PI-900", "quantity": "pressure", "unit": "bar(a)", "kind": "indicator", ...}
    time (UTC),time (local),session,tos / s,state,estop,PI-900 PV / bar(a),PI-900 status,...
    # session: {"session": 1, "tos_start": "2026-10-21T16:54:00+02:00[Europe/Amsterdam]", ...}
    2026-10-21T14:54:00.000Z,2026-10-21T16:54:00.000+02:00,1,0,reading,0,101,ok,...
    # calibration: {...}                (Box 2: a zero offset set or cleared)
    # switch: {"time": ..., "kind": "observed", "feed_before": 1, "feed_after": 2, ...}   (Box 5)

The columns are not taken from a fixed list. Each one is matched to a tag of
the ``# channel:`` lines and a field (:data:`FIELDS`: ``PV``, ``SP``,
``device PV``, ``target``, ``status``, ``mode``, ...), so a column the
software adds later is skipped with a warning, never a failure. Box 2 can also
write the day as a Zarr store, and ``box2 export`` writes NetCDF; both hold the
Dataset layout of Box 2's ``core/dataset.py`` (``time`` x ``channel``) and are
read by :func:`read_dataset`.

The event file is one tab-separated line per event (time with offset, level,
source, text), a traceback on the lines after it, each starting with a tab
(:func:`read_events`).

:func:`read` returns the parser dict of :mod:`lab_data_parser.processdata`
(``data``, ``meta``, ``events``, ``switches``); it does not interpret: values
stay in the stored units of the file, names stay as the software wrote them.
"""

from __future__ import annotations

import io
import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

FORMAT_PATTERN = re.compile(r"^(?P<software>[\w-]+) day log, (?P<kind>\w+), version (?P<version>\d+)$")
SUPPORTED_VERSION = 1  # a software not named below
# per software, the newest layout this reader knows; box5-control 2 added a controller's
# target, working, requested SP and owner (2026-10-24), the columns Box 2 has written since 1
SUPPORTED_VERSIONS = {"box2-control": 1, "box5-control": 2}

# The column fields of a channel: column word -> (variable, kind). "float" is a value
# in the channel's unit (or the device's for device PV / SP), the others are codes.
FIELDS: dict[str, tuple[str, str]] = {
    "PV": ("pv", "float"),
    "SP": ("sp", "float"),
    "device PV": ("device_pv", "float"),
    "device SP": ("device_sp", "float"),
    "target": ("target", "float"),
    "working": ("working", "float"),
    "requested": ("requested", "float"),
    "status": ("status", "status"),
    "owner": ("owner", "owner"),
    "mode": ("mode", "mode"),
}
FIXED_COLUMNS = ("time (UTC)", "time (local)", "session", "tos / s", "state", "estop")

# Codes as Box 2 stores them in its Dataset (core/datalog.py), so Zarr, NetCDF and CSV agree.
STATUS_CODES = {"ok": 0, "warning": 1, "error": 2, "idle": 3}
STATE_CODES = {"reading": 1, "controlling": 2}
OWNER_CODES = {"manual": 0, "programme": 1, "ramp": 2, "safety": 3}
MODE_WORDS = {"bus": 0, "fully closed": 3, "fully open": 8, "bus (RS232)": 18}
NO_CODE = -1  # owner, mode or state not recorded

# keys of a switch record that hold a moment (Unix seconds or ISO 8601)
SWITCH_TIME_KEYS = ("time", "sent", "confirmed")


# ---------------------------------------------------------------- files


def find_day_files(path: PathLike, set_up: Optional[str] = None) -> list[Path]:
    """Return the data files of a folder, or the file itself, in day order.

    Parameters
    ----------
    path : str or pathlib.Path
        A day file (``.csv``, ``.zarr`` or ``.nc``) or a folder of them.
    set_up : str, optional
        Keep only the files of this set-up (``"box2"``, ``"box5"``): set-ups
        may share a folder, the name is in the file name.

    Returns
    -------
    list of pathlib.Path
        ``<day>_<set-up>.csv`` before ``<day>_<set-up>_2.csv``; switch tables
        (``*_switches.csv``) are left out, their rows are in the data file.

    Raises
    ------
    FileNotFoundError
        If the path does not exist or the folder holds no day file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_file() or path.suffix == ".zarr":
        return [path]
    pattern = re.compile(r"^(?P<day>\d{4}-\d{2}-\d{2})_(?P<set_up>[^_.]+)(?:_(?P<n>\d+))?\.(csv|zarr|nc)$")
    found = []
    for item in path.iterdir():
        match = pattern.match(item.name)
        if match and (set_up is None or match["set_up"] == set_up):
            found.append((match["day"], match["set_up"], int(match["n"] or 1), item))
    if not found:
        raise FileNotFoundError(f"No day file (<day>_<set-up>.csv) in {path}" + (f" for {set_up!r}" if set_up else ""))
    set_ups = sorted({f[1] for f in found})
    if len(set_ups) > 1:
        raise ValueError(f"{path} holds the day files of several set-ups {set_ups}; pass set_up=...")
    return [f[3] for f in sorted(found, key=lambda f: (f[0], f[2]))]


def find_event_files(day_files: Iterable[Path]) -> list[Path]:
    """Return the event files that belong to day files, where the software puts them.

    Looks for ``<day>_<set-up>.log`` beside the data file and in a ``logs``
    folder beside the data folder (the defaults ``data/`` and ``logs/``).

    Parameters
    ----------
    day_files : iterable of pathlib.Path
        The data files.

    Returns
    -------
    list of pathlib.Path
        The event files found, each once, in day order.
    """
    out: list[Path] = []
    for file in day_files:
        match = re.match(r"^(\d{4}-\d{2}-\d{2}_[^_.]+)", file.name)
        if not match:
            continue
        name = f"{match[1]}.log"
        for candidate in (file.parent / name, file.parent.parent / "logs" / name):
            if candidate.is_file() and candidate not in out:
                out.append(candidate)
                break
    return out


# ---------------------------------------------------------------- the CSV day file


def read_csv(path: PathLike, keep_unknown: bool = False) -> dict[str, Any]:
    """Read one CSV day file.

    Parameters
    ----------
    path : str or pathlib.Path
        The file.
    keep_unknown : bool, optional
        Keep a numeric column whose field is not in :data:`FIELDS` as its own
        variable (named after the field) instead of skipping it with a warning
        (default is ``False``).

    Returns
    -------
    dict
        ``time`` (UTC, ``datetime64[ns]``), ``channels`` (one dict per channel,
        as in its ``# channel:`` line), ``fields`` (variable -> rows x channels
        array), ``rows`` (``session``, ``state``, ``estop``: one value per row,
        the session numbered within the file), ``header`` (the ``# key: value``
        lines), ``sessions``, ``calibrations`` and ``switches`` (lists of
        dicts, in file order).

    Raises
    ------
    ValueError
        If the file is not a lab-control day log of a version this reader knows.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    header: dict[str, str] = {}
    channels: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    calibrations: list[dict[str, Any]] = []
    switches: list[dict[str, Any]] = []
    data_lines: list[str] = []
    lists = {"channel": channels, "session": sessions, "calibration": calibrations, "switch": switches}
    for line in text.splitlines():
        if not line.startswith("#"):
            if line:
                data_lines.append(line)
            continue
        key, _, value = line[1:].strip().partition(": ")
        if key in lists:
            lists[key].append(json.loads(value))
        elif key:
            header[key] = value
    _check_format(header.get("format"), path)
    if not data_lines:
        raise ValueError(f"{path.name}: no column line")

    table = pd.read_csv(io.StringIO("\n".join(data_lines)), dtype=str, keep_default_na=False)
    columns = list(table.columns)
    n_rows, tags = len(table), [c["tag"] for c in channels]
    by_length = sorted(tags, key=len, reverse=True)  # "BPR Vent" before "BPR"
    fields: dict[str, np.ndarray] = {}
    skipped: list[str] = []
    for column in columns:
        if column in FIXED_COLUMNS:
            continue
        tag = next((t for t in by_length if column.startswith(t + " ")), None)
        word = column[len(tag) + 1:].split(" / ")[0] if tag else None
        if tag is None or (word not in FIELDS and not keep_unknown):
            skipped.append(column)
            continue
        name, kind = FIELDS.get(word, (_snake(word), "float"))
        if name not in fields:
            fill = np.nan if kind == "float" else (STATUS_CODES["idle"] if kind == "status" else NO_CODE)
            fields[name] = np.full((n_rows, len(tags)), fill, dtype=float if kind == "float" else np.int8)
        fields[name][:, tags.index(tag)] = _decode(table[column], kind)
    if skipped:
        logger.warning("%s: skipping %d column(s) this reader does not know: %s", path.name, len(skipped), skipped)

    time = pd.to_datetime(table["time (UTC)"], format="ISO8601", utc=True)
    rows: dict[str, np.ndarray] = {
        "session": table["session"].astype("int16").to_numpy() if "session" in table else np.ones(n_rows, "int16"),
    }
    if "state" in table:
        rows["state"] = _codes(table["state"], STATE_CODES, NO_CODE)
    if "estop" in table:
        rows["estop"] = pd.to_numeric(table["estop"], errors="coerce").fillna(NO_CODE).astype("int8").to_numpy()
    return {
        "time": time.dt.tz_localize(None).to_numpy(dtype="datetime64[ns]"),
        "channels": channels,
        "fields": fields,
        "rows": rows,
        "header": header,
        "sessions": sessions,
        "calibrations": calibrations,
        "switches": switches,
    }


def _check_format(value: Optional[str], path: Path) -> None:
    match = FORMAT_PATTERN.match(value or "")
    if match is None:
        raise ValueError(f"{path.name} is not a lab-control day log (first line: '# format: {value}')")
    known = SUPPORTED_VERSIONS.get(match["software"], SUPPORTED_VERSION)
    if int(match["version"]) > known:
        raise ValueError(
            f"{path.name} is a {value!r}; this reader knows version {known}. "
            "Update lab-data-parser (the layout changed, see the software's docs/data-format.md)."
        )


def _snake(word: str) -> str:
    return re.sub(r"\W+", "_", word.strip()).strip("_").lower()


def _decode(column: pd.Series, kind: str) -> np.ndarray:
    if kind == "float":
        return pd.to_numeric(column, errors="coerce").to_numpy(dtype=float)
    if kind == "status":
        return _codes(column, STATUS_CODES, STATUS_CODES["idle"])
    if kind == "owner":
        return _codes(column, OWNER_CODES, NO_CODE)
    # mode: a word, or "mode N" for a mode without one
    numbers = pd.to_numeric(column.str.removeprefix("mode "), errors="coerce")
    words = column.map(MODE_WORDS)
    return words.fillna(numbers).fillna(NO_CODE).astype("int8").to_numpy()


def _codes(column: pd.Series, codes: dict[str, int], missing: int) -> np.ndarray:
    return column.map(codes).fillna(missing).astype("int8").to_numpy()


# ---------------------------------------------------------------- Zarr and NetCDF (Box 2's Dataset)


def read_dataset(path: PathLike) -> dict[str, Any]:
    """Read a Zarr day store or a NetCDF export (Box 2's ``time`` x ``channel`` Dataset).

    Parameters
    ----------
    path : str or pathlib.Path
        A ``.zarr`` folder (needs ``zarr``, the extra ``lab_data_parser[zarr]``)
        or a ``.nc`` file written by ``box2 export``.

    Returns
    -------
    dict
        The same keys as :func:`read_csv`.

    Raises
    ------
    ImportError
        If a Zarr store is read without ``zarr`` installed.
    """
    import xarray as xr

    from lab_data_parser.history import decode_attrs

    path = Path(path)
    if path.suffix == ".zarr":
        try:
            import zarr  # noqa: F401
        except ImportError as error:
            raise ImportError("Reading a Zarr day store needs zarr: pip install 'lab_data_parser[zarr]'") from error
        with xr.open_zarr(path) as handle:
            ds = handle.load()
    else:
        with xr.open_dataset(path, engine="h5netcdf") as handle:
            ds = handle.load()
    attrs = decode_attrs(dict(ds.attrs))
    channel_keys = [k for k, v in ds.coords.items() if v.dims == ("channel",) and k != "channel"]
    channels = [
        {"tag": str(tag), **{k: ds[k].values[i].item() for k in channel_keys}}
        for i, tag in enumerate(ds["channel"].values)
    ]
    fields = {
        name: ds[name].transpose("time", "channel").values
        for name, variable in ds.data_vars.items()
        if variable.dims in (("time", "channel"), ("channel", "time"))
    }
    rows = {"session": ds["session"].values.astype("int16") if "session" in ds else np.ones(ds.sizes["time"], "int16")}
    for name in ("state", "estop"):
        if name in ds:
            rows[name] = ds[name].values.astype("int8")
    sessions = attrs.pop("sessions", [])
    calibrations = attrs.pop("calibrations", [])
    for key in ("mode_channels", "setpoint_channels"):
        attrs.pop(key, None)
    return {
        "time": ds["time"].values.astype("datetime64[ns]"),
        "channels": channels,
        "fields": fields,
        "rows": rows,
        "header": attrs,
        "sessions": list(sessions),
        "calibrations": list(calibrations),
        "switches": list(attrs.pop("switches", [])),
    }


# ---------------------------------------------------------------- the event file


def read_events(path: PathLike) -> dict[str, np.ndarray]:
    """Read one event file.

    Parameters
    ----------
    path : str or pathlib.Path
        A ``<day>_<set-up>.log`` file.

    Returns
    -------
    dict
        ``time`` (UTC, ``datetime64[ns]``), ``level``, ``source``, ``text``
        and ``detail`` (the traceback lines, joined; empty when none), one
        entry per event.
    """
    time, level, source, text, detail = [], [], [], [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("\t"):
            if detail:
                detail[-1] += ("\n" if detail[-1] else "") + line[1:]
            continue
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        time.append(parts[0])
        level.append(parts[1])
        source.append(parts[2])
        text.append(parts[3])
        detail.append("")
    stamps = pd.to_datetime(pd.Series(time, dtype=str), format="ISO8601", utc=True)
    return {
        "time": stamps.dt.tz_localize(None).to_numpy(dtype="datetime64[ns]"),
        "level": np.array(level, dtype=object),
        "source": np.array(source, dtype=object),
        "text": np.array(text, dtype=object),
        "detail": np.array(detail, dtype=object),
    }


# ---------------------------------------------------------------- one or more days


def read(
    path: Union[PathLike, Iterable[PathLike]],
    *,
    set_up: Optional[str] = None,
    events: Union[bool, PathLike, Iterable[PathLike]] = True,
    keep_unknown: bool = False,
) -> dict[str, Any]:
    """Read day files (one, a list, or a folder) and their events into one record.

    Files are joined along time on the union of their channels; a channel a
    file did not record is NaN there (status ``idle``). Sessions are numbered
    once across the files: a session that ran over midnight goes on in the next
    day's file under the same ``tos_start`` and keeps one number.

    Parameters
    ----------
    path : str, pathlib.Path or list of them
        Day files (``.csv``, ``.zarr``, ``.nc``) or a folder of them.
    set_up : str, optional
        The set-up to read from a folder several set-ups share.
    events : bool, str, pathlib.Path or list of them, optional
        ``True`` (default) reads the event files where the software puts them
        (:func:`find_event_files`), ``False`` none; a path or list reads those.
    keep_unknown : bool, optional
        See :func:`read_csv`.

    Returns
    -------
    dict
        ``data`` (``time``, ``channels``, ``fields``, ``rows``, sorted by time),
        ``meta`` (``format``, ``set_up``, ``timezone``, ``sessions``,
        ``calibrations``, ``source_files``, ``event_files`` and the other header
        lines), ``events`` and ``switches`` (column dicts, possibly empty).

    Raises
    ------
    FileNotFoundError
        If a path does not exist or a folder holds no day file.
    ValueError
        If a file is not a lab-control day log, or two files give one channel different units.
    """
    paths = [path] if isinstance(path, (str, Path)) else list(path)
    files = [f for p in paths for f in find_day_files(p, set_up)]
    days = [read_dataset(f) if f.suffix in (".zarr", ".nc") else read_csv(f, keep_unknown) for f in files]

    # channels: the union, in order of appearance; one unit per tag
    channels: dict[str, dict[str, Any]] = {}
    for file, day in zip(files, days):
        for channel in day["channels"]:
            known = channels.get(channel["tag"])
            if known is not None and known.get("unit") != channel.get("unit"):
                raise ValueError(
                    f"{file.name}: channel {channel['tag']!r} in {channel.get('unit')!r}, "
                    f"earlier files in {known.get('unit')!r}"
                )
            channels.setdefault(channel["tag"], channel)
    channels = {tag: _with_species(channel) for tag, channel in channels.items()}
    tags = list(channels)

    # sessions: one number per tos_start across files
    sessions: list[dict[str, Any]] = []
    number_of: dict[str, int] = {}
    session_maps = []
    for file, day in zip(files, days):
        local: dict[int, int] = {}
        for index, session in enumerate(day["sessions"], start=1):
            key = str(session.get("tos_start"))
            if key not in number_of:
                number_of[key] = len(sessions) + 1
                sessions.append({**session, "session": number_of[key], "files": [file.name]})
            elif file.name not in sessions[number_of[key] - 1]["files"]:
                sessions[number_of[key] - 1]["files"].append(file.name)
            local[int(session.get("session", index))] = number_of[key]
        session_maps.append(local)

    n_total = sum(len(d["time"]) for d in days)
    kinds = {name: kind for name, kind in FIELDS.values()}
    names = list(dict.fromkeys(name for d in days for name in d["fields"]))
    fields = {}
    for name in names:
        kind = kinds.get(name, "float")
        fill = np.nan if kind == "float" else (STATUS_CODES["idle"] if kind == "status" else NO_CODE)
        fields[name] = np.full((n_total, len(tags)), fill, dtype=float if kind == "float" else np.int8)
    row_names = list(dict.fromkeys(name for d in days for name in d["rows"]))
    rows = {name: np.full(n_total, NO_CODE, dtype="int16" if name == "session" else "int8") for name in row_names}
    time = np.empty(n_total, dtype="datetime64[ns]")
    start = 0
    for day, local in zip(days, session_maps):
        n = len(day["time"])
        stop = start + n
        time[start:stop] = day["time"]
        columns = [tags.index(c["tag"]) for c in day["channels"]]
        for name, values in day["fields"].items():
            fields[name][start:stop, columns] = values
        for name, values in day["rows"].items():
            if name == "session":
                values = np.array([local.get(int(v), int(v)) for v in values], dtype="int16") if local else values
            rows[name][start:stop] = values
        start = stop

    order = np.argsort(time, kind="stable")
    if not np.array_equal(order, np.arange(n_total)):
        time = time[order]
        fields = {name: values[order] for name, values in fields.items()}
        rows = {name: values[order] for name, values in rows.items()}

    header = {k: v for d in days for k, v in d["header"].items()}
    formats = sorted({str(d["header"]["format"]) for d in days if "format" in d["header"]})
    meta: dict[str, Any] = {
        "format": formats[0] if len(formats) == 1 else formats,
        "set_up": header.pop("set-up", None) or header.pop("bench", None) or set_up,
        "timezone": header.pop("timezone", None),
        "software": header.pop("source", None),
        "days": sorted({str(d["header"]["day"]) for d in days if "day" in d["header"]}),
        "header": {k: v for k, v in header.items() if k not in ("day", "format")},
        "sessions": sessions,
        "calibrations": [c for d in days for c in d["calibrations"]],
        "source_files": [str(f) for f in files],
    }

    if events is True:
        event_files = find_event_files(files)
    elif events is False or events is None:
        event_files = []
    else:
        event_paths = [events] if isinstance(events, (str, Path)) else list(events)
        event_files = [
            f for p in map(Path, event_paths) for f in (sorted(p.glob("*.log")) if p.is_dir() else [p])
        ]
    meta["event_files"] = [str(f) for f in event_files]

    return {
        "data": {"time": time, "channels": [channels[t] for t in tags], "fields": fields, "rows": rows},
        "meta": meta,
        "events": _join_events([read_events(f) for f in event_files]),
        "switches": switch_columns([s for d in days for s in d["switches"]]),
    }


# Box 5 names an MFC after its line, position and gas (``F1-1-He``); its channel line has no species yet
_LINE_TAG = re.compile(r"^F\d+-\d+-(?P<species>[A-Za-z0-9]+)$")


def _with_species(channel: dict[str, Any]) -> dict[str, Any]:
    """The channel with ``species`` where the line names one, else where the Box 5 tag does."""
    if channel.get("species"):
        return channel
    species = channel.get("gas")
    if not species and channel.get("quantity") == "flow":
        match = _LINE_TAG.match(str(channel["tag"]))
        species = match["species"] if match else None
    return {**channel, "species": species} if species else channel


def _join_events(parts: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    keys = ("time", "level", "source", "text", "detail")
    if not parts:
        return {k: np.array([], dtype="datetime64[ns]" if k == "time" else object) for k in keys}
    joined = {k: np.concatenate([p[k] for p in parts]) for k in keys}
    order = np.argsort(joined["time"], kind="stable")
    return {k: v[order] for k, v in joined.items()}


def switch_columns(records: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    """Turn switch records into columns, every key kept.

    Parameters
    ----------
    records : list of dict
        The ``# switch:`` lines, as read.

    Returns
    -------
    dict
        One array per key: the moments of :data:`SWITCH_TIME_KEYS` as UTC
        ``datetime64[ns]`` (NaT where empty), numbers as float (NaN where
        empty), anything else as text; sorted by ``time``.
    """
    keys = list(dict.fromkeys(k for r in records for k in r))
    if "time" not in keys:
        keys.insert(0, "time")
    out: dict[str, np.ndarray] = {}
    for key in keys:
        values = [r.get(key) for r in records]
        if key in SWITCH_TIME_KEYS:
            out[key] = _moments(values)
        elif all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in values):
            out[key] = np.array([np.nan if v is None else float(v) for v in values], dtype=float)
        else:
            out[key] = np.array(["" if v is None else (v if isinstance(v, str) else json.dumps(v)) for v in values], dtype=object)
    order = np.argsort(out["time"], kind="stable")
    return {k: v[order] for k, v in out.items()}


def _moments(values: list[Any]) -> np.ndarray:
    """Unix seconds or ISO 8601 text (with offset) to UTC datetime64[ns]; None to NaT."""
    out = np.full(len(values), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    for i, value in enumerate(values):
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            stamp = pd.Timestamp(float(value), unit="s", tz="UTC")
        else:
            stamp = pd.Timestamp(value)
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        out[i] = stamp.tz_localize(None).to_datetime64()
    return out
