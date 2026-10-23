"""``ProcessData``: the operational data of a set-up (flows, pressures, temperatures, valves, events).

Whatever ran the set-up, LabVIEW or one of the lab-control Python programs
(``box2-control``, ``box5-control``), the result is one layout:

- dims ``tos`` (samples, seconds since ``tos_start``) and ``channel`` (the tag:
  ``PI-900``, ``F1-1-He``, ``Reactor T``);
- along ``channel`` the coordinates ``quantity``, ``unit``, ``kind``,
  ``species``, ``device``, ``description`` and every other scalar the channel
  line holds (an MFC's ``factor``, its ``feed``);
- along ``tos`` x ``channel`` the values: ``pv`` always, and as recorded
  ``sp``, ``device_pv``, ``device_sp`` (an MFC's own figures before its
  correction factor), ``target``, ``working``, ``requested`` (a controller's
  setpoint layers), ``status``, ``owner`` and ``mode`` (codes, with CF
  ``flag_values`` / ``flag_meanings``);
- along ``tos`` the coordinate ``session`` (Connect to Disconnect, or one
  LabVIEW start) and the variables ``state`` and ``estop``;
- along ``event`` the event log (``event_time`` in UTC, ``event_level``,
  ``event_source``, ``event_text``, ``event_detail``) and along ``switch``
  the valve switches (``switch_time``, ``switch_kind``, ``switch_feed_before``,
  ...): absolute times, so moving the origin never touches them;
- in ``ds.attrs`` ``tos_start``, ``set_up``, ``format``, ``timezone``,
  ``sessions`` (start, ambient pressure and settings of each), ``calibrations``,
  the files read and the history.

Parsers return the record ``{"data": {"time", "channels", "fields", "rows"},
"meta": {...}, "events": {...}, "switches": {...}}`` (see
``labcontrol/daylog.py`` and ``labview/b67box5.py``); ``ProcessData`` never
reads a file itself.
"""

import logging
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence, Union

import numpy as np
import numpy.typing as npt
import pandas as pd
import xarray as xr
from pydantic import BaseModel, ConfigDict, Field, field_validator

from lab_data_parser._selection import EmptyWindow, window_mask
from lab_data_parser._time import TimeOriginMixin, TimestampLike, _to_timestamp, decode_tos_start, encode_tos_start
from lab_data_parser.history import HistoryMixin, decode_attrs, encode_attrs, records_step
from lab_data_parser.naming.species.convention import ConventionLike, Unknown, get_convention
from lab_data_parser.processdata.labcontrol.daylog import (
    FIELDS,
    MODE_WORDS,
    NO_CODE,
    OWNER_CODES,
    STATE_CODES,
    STATUS_CODES,
)

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

FLOAT_FIELDS = tuple(name for name, kind in FIELDS.values() if kind == "float")
CODE_FIELDS = {"status": STATUS_CODES, "owner": OWNER_CODES, "mode": MODE_WORDS}
LONG_NAMES = {
    "pv": "process value, in the channel's unit",
    "sp": "setpoint, in the channel's unit",
    "device_pv": "process value as the device gives it (before its correction factor)",
    "device_sp": "setpoint as the device gets it (before its correction factor)",
    "target": "setpoint the programme or operator asked for",
    "working": "setpoint on its way to the target (a ramp)",
    "requested": "setpoint last sent to the device",
    "status": "status of each value",
    "owner": "who set the setpoint",
    "mode": "an MFC's control mode as it reports it",
    "state": "state of the set-up",
    "estop": "E-STOP latched",
}
CHANNEL_COORDS = ("quantity", "unit", "kind", "species", "device", "description")
RESERVED = {"tos", "channel", "session", "state", "estop", "event", "switch"}
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _flags(codes: Mapping[str, int], none: bool = True) -> dict[str, Any]:
    words = (["none"] if none else []) + [w.replace(" ", "_").replace("(", "").replace(")", "") for w in codes]
    return {"flag_values": ([NO_CODE] if none else []) + list(codes.values()), "flag_meanings": " ".join(words)}


def _channel_coords(channels: list[dict[str, Any]], taken: set[str]) -> dict[str, tuple]:
    """One coordinate per scalar key of the channel lines; text where values are mixed."""
    keys = list(dict.fromkeys([*CHANNEL_COORDS, *(k for c in channels for k in c if k != "tag")]))
    coords: dict[str, tuple] = {}
    for key in keys:
        values = [c.get(key) for c in channels]
        if any(isinstance(v, (dict, list)) for v in values):
            continue  # nested: kept in attrs["channel_info"]
        name = f"channel_{key}" if key in taken or key in RESERVED else key
        present = [v for v in values if v is not None]
        if present and all(isinstance(v, bool) for v in present) and len(present) == len(values):
            coords[name] = ("channel", np.array(values, dtype=bool))
        elif present and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
            coords[name] = ("channel", np.array([np.nan if v is None else float(v) for v in values]))
        else:
            coords[name] = ("channel", np.array(["" if v is None else str(v) for v in values], dtype=object))
    return coords


def _resolve_origin(tos_start: Optional[TimestampLike], meta: dict[str, Any], time: np.ndarray) -> Optional[pd.Timestamp]:
    """The origin: the one given, else the first session's start, else the first sample."""
    zone = meta.get("timezone")
    starts = [decode_tos_start(s.get("tos_start")) for s in meta.get("sessions", []) if s.get("tos_start")]
    reference = min(starts) if starts else None
    if tos_start is not None:
        if reference is None and zone:
            reference = pd.Timestamp("2000-01-01", tz=zone)
        return _to_timestamp(tos_start, reference)
    if reference is not None:
        return reference
    if not len(time):
        return None
    first = pd.Timestamp(time.min())
    return first.tz_localize("UTC").tz_convert(zone) if zone else first


def _seconds_since(time: np.ndarray, origin: Optional[pd.Timestamp]) -> np.ndarray:
    if origin is None:
        return np.zeros(len(time)) if len(time) == 0 else (time - time.min()) / np.timedelta64(1, "s")
    base = origin.tz_convert("UTC").tz_localize(None) if origin.tzinfo is not None else origin
    return (time - base.to_datetime64()) / np.timedelta64(1, "s")


def build_dataset(record: dict[str, Any], tos_start: Optional[TimestampLike] = None) -> xr.Dataset:
    """Build the ``ProcessData`` Dataset from a parser record.

    Parameters
    ----------
    record : dict
        ``data`` (``time``: UTC ``datetime64`` when the meta names a timezone,
        else naive local; ``channels``; ``fields``; ``rows``), ``meta``, and
        optionally ``events`` and ``switches``.
    tos_start : pandas.Timestamp, datetime, numpy.datetime64 or str, optional
        The origin of ``tos``; a naive value is read in the data's timezone.
        Defaults to the start of the first session, else the first sample.

    Returns
    -------
    xarray.Dataset
        The layout described in the module docstring.
    """
    data, meta = record["data"], dict(record.get("meta", {}))
    time = np.asarray(data["time"], dtype="datetime64[ns]")
    channels = list(data["channels"])
    origin = _resolve_origin(tos_start, meta, time)
    data_vars: dict[str, tuple] = {}
    for name, values in data["fields"].items():
        attrs = {"long_name": LONG_NAMES.get(name, name)}
        if name in CODE_FIELDS:
            attrs.update(_flags(CODE_FIELDS[name], none=name != "status"))
        data_vars[name] = (("tos", "channel"), np.asarray(values), attrs)
    rows = dict(data.get("rows", {}))
    session = np.asarray(rows.pop("session", np.ones(len(time))), dtype="int16")
    for name, values in rows.items():
        attrs = {"long_name": LONG_NAMES.get(name, name)}
        if name == "state":
            attrs.update(_flags(STATE_CODES))
        elif name == "estop":
            attrs.update({"flag_values": [NO_CODE, 0, 1], "flag_meanings": "none no yes"})
        data_vars[name] = (("tos",), np.asarray(values), attrs)

    events = record.get("events") or {}
    if len(events.get("time", ())):
        for key, values in events.items():
            data_vars[f"event_{key}"] = (("event",), np.asarray(values), {"long_name": f"event {key}" + (", UTC" if key == "time" else "")})
    switches = record.get("switches") or {}
    if len(switches.get("time", ())):
        for key, values in switches.items():
            data_vars[f"switch_{key}"] = (("switch",), np.asarray(values), {"long_name": f"valve switch {key}" + (", UTC" if values.dtype.kind == "M" else "")})

    coords: dict[str, Any] = {
        "tos": ("tos", _seconds_since(time, origin), {"units": "s", "long_name": "time since tos_start"}),
        "session": ("tos", session, {"long_name": "session, see attrs['sessions']"}),
        "channel": ("channel", np.array([str(c["tag"]) for c in channels], dtype=object)),
        **_channel_coords(channels, set(data_vars)),
    }
    nested = {str(c["tag"]): {k: v for k, v in c.items() if isinstance(v, (dict, list))} for c in channels}
    attrs = {k: v for k, v in meta.items() if v is not None}
    if any(nested.values()):
        attrs["channel_info"] = {k: v for k, v in nested.items() if v}
    if origin is not None:
        attrs["tos_start"] = encode_tos_start(origin)
    return xr.Dataset(data_vars=data_vars, coords=coords, attrs=attrs)


class ProcessData(TimeOriginMixin, HistoryMixin, BaseModel):
    """The process data of a set-up: every channel's values over time, its sessions, events and valve switches.

    Read with :meth:`from_day_log` (box2-control, box5-control),
    :meth:`from_labview_b67box5` (LabVIEW, Box 5) or :meth:`from_dataframe`.
    The backing store is one ``xr.Dataset`` (``ds``), see
    :mod:`lab_data_parser.processdata.core`. Every processing method returns
    a new instance.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True, ignored_types=(cached_property,))

    ds: xr.Dataset = Field(description="xarray Dataset with dims 'tos' and 'channel' (and 'event', 'switch').")

    @field_validator("ds", mode="before")
    @classmethod
    def validate_ds(cls, v: Any) -> xr.Dataset:
        """Check the layout of ``ds``: a ``tos`` and a ``channel`` dimension and a ``pv`` variable."""
        if not isinstance(v, xr.Dataset):
            raise TypeError(f"'ds' must be an xr.Dataset, got {type(v)}")
        for dim in ("tos", "channel"):
            if dim not in v.dims:
                raise ValueError(f"Dataset must have a {dim!r} dimension")
        if "pv" not in v.data_vars:
            raise ValueError("Dataset must have a 'pv' variable (tos x channel)")
        return v

    def _new(self, ds: xr.Dataset) -> "ProcessData":
        """A new instance around ``ds``."""
        return ProcessData(ds=ds)

    # ---------------------------------------------------------------- properties

    @property
    def channels(self) -> list[str]:
        """The channel tags, in file order.

        Returns
        -------
        list of str
            The ``channel`` coordinate.
        """
        return [str(c) for c in self.ds["channel"].values]

    @property
    def fields(self) -> list[str]:
        """The recorded values per channel (``pv``, ``sp``, ``status``, ...).

        Returns
        -------
        list of str
            The names of the ``tos`` x ``channel`` variables.
        """
        return [name for name, v in self.ds.data_vars.items() if set(v.dims) == {"tos", "channel"}]

    @property
    def set_up(self) -> Optional[str]:
        """The set-up the data come from (``"box2"``, ``"box5"``), if known.

        Returns
        -------
        str or None
            ``ds.attrs["set_up"]``.
        """
        return self.ds.attrs.get("set_up")

    @property
    def n_samples(self) -> int:
        """Number of samples along ``tos``.

        Returns
        -------
        int
            Length of the ``tos`` dimension.
        """
        return int(self.ds.sizes["tos"])

    @property
    def tos(self) -> npt.NDArray:
        """Seconds since ``tos_start`` of every sample.

        Returns
        -------
        numpy.ndarray
            The ``tos`` coordinate.
        """
        return self.ds.coords["tos"].values

    @property
    def sampling_interval(self) -> Optional[float]:
        """Median time step between consecutive samples, in seconds.

        Returns
        -------
        float or None
            Median of ``numpy.diff(tos)``, ``None`` for fewer than two samples.
        """
        if self.n_samples < 2:
            return None
        return float(np.median(np.diff(self.tos)))

    @property
    def sessions(self) -> list[dict[str, Any]]:
        """The sessions (Connect to Disconnect, or one LabVIEW start), with their start and settings.

        Returns
        -------
        list of dict
            As the software wrote them, numbered once across the files read
            (``session`` matches the ``session`` coordinate), plus ``files``.
        """
        return list(self.ds.attrs.get("sessions", []))

    @property
    def calibrations(self) -> list[dict[str, Any]]:
        """The zero offsets set or cleared while the data were written (box2-control).

        Returns
        -------
        list of dict
            Tag, new and previous offset, when, and the raw readings behind it.
        """
        return list(self.ds.attrs.get("calibrations", []))

    @property
    def events(self) -> pd.DataFrame:
        """The event log: what happened, with its level, source and traceback.

        Returns
        -------
        pandas.DataFrame
            Columns ``time`` (in the data's timezone), ``tos`` (seconds since
            ``tos_start``), ``level``, ``source``, ``text``, ``detail``; empty
            when no event file was read.
        """
        return self._table("event")

    @property
    def switches(self) -> pd.DataFrame:
        """The valve switches (box5-control): when, which feed before and after, how it was confirmed.

        Returns
        -------
        pandas.DataFrame
            One row per switch; every moment (``time``, ``sent``, ``confirmed``)
            in the data's timezone with a ``tos`` column beside ``time``.
        """
        return self._table("switch")

    def _zone(self) -> Optional[str]:
        origin = self.tos_start
        if origin is not None and origin.tzinfo is not None:
            return str(origin.tzinfo)
        return self.ds.attrs.get("timezone")

    def _table(self, dim: str) -> pd.DataFrame:
        prefix = f"{dim}_"
        names = [n for n, v in self.ds.data_vars.items() if v.dims == (dim,)]
        if not names:
            return pd.DataFrame(columns=["time", "tos"])
        zone = self._zone()
        table = {}
        for name in names:
            values = self.ds[name].values
            if values.dtype.kind == "M":
                stamps = pd.DatetimeIndex(values).tz_localize("UTC")
                values = stamps.tz_convert(zone) if zone else stamps
            table[name.removeprefix(prefix)] = values
        frame = pd.DataFrame(table)
        frame.insert(1, "tos", self._tos_of(self.ds[f"{prefix}time"].values))
        return frame

    def _tos_of(self, moments: np.ndarray) -> np.ndarray:
        """Seconds since ``tos_start`` of UTC moments (NaN without an origin)."""
        origin = self.tos_start
        if origin is None:
            return np.full(len(moments), np.nan)
        return _seconds_since(np.asarray(moments, dtype="datetime64[ns]"), origin)

    # ---------------------------------------------------------------- channel access

    def get_channel(self, name: str, field: str = "pv") -> npt.NDArray:
        """Return one channel's values.

        Parameters
        ----------
        name : str
            Channel tag, as in ``channels``.
        field : str, optional
            Which value (default is ``"pv"``): any of ``fields``.

        Returns
        -------
        numpy.ndarray
            1-D array along ``tos``.

        Raises
        ------
        KeyError
            If the channel or the field is not present.
        """
        self._check_channels([name])
        if field not in self.fields:
            raise KeyError(f"Field {field!r} not recorded. Available: {self.fields}")
        return self.ds[field].sel(channel=name).values

    def get_channel_unit(self, name: str) -> Optional[str]:
        """Return a channel's unit.

        Parameters
        ----------
        name : str
            Channel tag.

        Returns
        -------
        str or None
            The ``unit`` coordinate, ``None`` when empty.

        Raises
        ------
        KeyError
            If the channel is not present.
        """
        self._check_channels([name])
        unit = str(self.ds["unit"].sel(channel=name).item())
        return unit or None

    def channels_of(
        self, quantity: Optional[str] = None, *, species: Optional[str] = None, kind: Optional[str] = None
    ) -> list[str]:
        """Return the channels of a quantity, species or kind.

        Parameters
        ----------
        quantity : str, optional
            ``"flow"``, ``"pressure"``, ``"temperature"``, ``"feed"``, ...
        species : str, optional
            The species of a flow (``"CO2"``).
        kind : str, optional
            ``"indicator"``, ``"controller"``, ``"indicator+controller"``, ...

        Returns
        -------
        list of str
            The matching tags, possibly empty.
        """
        keep = np.ones(self.ds.sizes["channel"], dtype=bool)
        for coord, value in (("quantity", quantity), ("species", species), ("kind", kind)):
            if value is not None:
                keep &= self.ds[coord].values == value
        return [c for c, k in zip(self.channels, keep) if k]

    def _check_channels(self, names: Iterable[str]) -> None:
        missing = [n for n in names if n not in self.channels]
        if missing:
            raise KeyError(f"Channel(s) not found: {missing}. Available: {self.channels}")

    # ---------------------------------------------------------------- selection

    @records_step
    def select_channels(self, channels: Sequence[str]) -> "ProcessData":
        """Return the data of some channels only (events and switches are kept).

        Parameters
        ----------
        channels : sequence of str
            Tags to keep, in this order.

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        KeyError
            If a tag is not present.
        """
        self._check_channels(channels)
        return self._new(self.ds.sel(channel=list(channels)))

    @records_step
    def select_quantity(self, quantity: str) -> "ProcessData":
        """Return the channels of one quantity only (``"flow"``, ``"pressure"``, ...).

        Parameters
        ----------
        quantity : str
            The quantity.

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        ValueError
            If no channel measures that quantity.
        """
        names = self.channels_of(quantity)
        if not names:
            raise ValueError(f"No channel measures {quantity!r}; quantities: {sorted(set(self.ds['quantity'].values))}")
        return self.select_channels(names)

    @records_step
    def select_tos_range(
        self, min_s: Optional[float] = None, max_s: Optional[float] = None, empty: EmptyWindow = "warn"
    ) -> "ProcessData":
        """Return the samples, events and switches inside a time-on-stream window.

        Parameters
        ----------
        min_s, max_s : float, optional
            Inclusive bounds of ``tos`` in seconds; ``None`` leaves a side open.
        empty : {"warn", "raise"}, optional
            What to do when no sample falls inside: log it and return the empty
            selection (default), or raise ``ValueError``.

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        ValueError
            If the window is empty and ``empty="raise"``.
        """
        mask = window_mask(self.tos, min_s, max_s, what="sample", axis="tos", unit="s", empty=empty)
        return self._new(self._cut(mask, min_s, max_s))

    @records_step
    def select_session(self, session: Union[int, Sequence[int]]) -> "ProcessData":
        """Return one session (or several), with the events and switches of its time span.

        Parameters
        ----------
        session : int or sequence of int
            Session number(s), as in ``sessions``.

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        ValueError
            If no sample belongs to the session(s).
        """
        wanted = [session] if isinstance(session, (int, np.integer)) else list(session)
        mask = np.isin(self.ds["session"].values, wanted)
        if not mask.any():
            raise ValueError(f"No sample of session(s) {wanted}; sessions: {sorted(set(self.ds['session'].values.tolist()))}")
        tos = self.tos[mask]
        ds = self._cut(mask, float(tos.min()), float(tos.max()))
        ds.attrs = {**ds.attrs, "sessions": [s for s in self.sessions if s.get("session") in wanted]}
        return self._new(ds)

    def _cut(self, mask: npt.NDArray, min_s: Optional[float], max_s: Optional[float]) -> xr.Dataset:
        """``ds`` with the samples of ``mask`` and the events and switches inside [min_s, max_s]."""
        ds = self.ds.isel(tos=mask)
        for dim in ("event", "switch"):
            if dim in ds.dims:
                when = self._tos_of(ds[f"{dim}_time"].values)
                keep = np.ones(len(when), dtype=bool)
                if min_s is not None:
                    keep &= ~(when < min_s)
                if max_s is not None:
                    keep &= ~(when > max_s)
                ds = ds.isel({dim: keep})
        return ds

    # ---------------------------------------------------------------- processing

    @records_step
    def resample(self, step_s: float, method: Literal["mean", "median", "first", "last"] = "mean") -> "ProcessData":
        """Bin the samples into equal time intervals.

        Values (``pv``, ``sp``, ...) are aggregated with ``method``, skipping
        NaN; a code takes the last recorded one of the bin, ``status`` the
        worst (error over warning over ok, idle only when nothing was read),
        ``estop`` is 1 when it was latched at any time of the bin.

        Parameters
        ----------
        step_s : float
            Bin width in seconds.
        method : {"mean", "median", "first", "last"}, optional
            Aggregation of the values (default is ``"mean"``).

        Returns
        -------
        ProcessData
            New instance on a uniform grid of bin centres; a bin without samples is NaN.

        Raises
        ------
        ValueError
            If ``step_s`` is not positive or ``method`` is unknown.
        """
        if step_s <= 0:
            raise ValueError("step_s must be > 0")
        if method not in ("mean", "median", "first", "last"):
            raise ValueError(f"method must be 'mean', 'median', 'first' or 'last', got {method!r}")
        if self.n_samples == 0:
            return self._new(self.ds.copy())
        tos = self.tos
        bins = np.floor((tos - tos[0]) / step_s).astype(int)
        n_bins = int(bins.max()) + 1
        index = range(n_bins)

        def aggregate(values: np.ndarray, how: str, fill: float) -> np.ndarray:
            frame = pd.DataFrame(values.reshape(len(values), -1))
            out = frame.groupby(bins).agg(how).reindex(index)
            return out.fillna(fill).to_numpy().reshape((n_bins, *values.shape[1:]))

        new_vars = {}
        for name, variable in self.ds.data_vars.items():
            if "tos" not in variable.dims:
                new_vars[name] = variable
                continue
            values = variable.transpose("tos", ...).values
            if values.dtype.kind == "f":
                result = aggregate(values, method, np.nan)
            elif name == "status":
                worst = np.where(values == STATUS_CODES["idle"], -1, values)  # idle only when nothing else
                result = aggregate(worst, "max", -1)
                result = np.where(result < 0, STATUS_CODES["idle"], result).astype(values.dtype)
            elif name == "estop":
                result = aggregate(values, "max", NO_CODE).astype(values.dtype)
            else:
                result = aggregate(values, "last", NO_CODE).astype(values.dtype)
            new_vars[name] = (variable.transpose("tos", ...).dims, result, variable.attrs)
        session = aggregate(self.ds["session"].values, "last", NO_CODE).astype("int16")
        coords = {k: v for k, v in self.ds.coords.items() if "tos" not in v.dims}
        coords["tos"] = ("tos", tos[0] + (np.arange(n_bins) + 0.5) * step_s, self.ds["tos"].attrs)
        coords["session"] = ("tos", session, self.ds["session"].attrs)
        ds = xr.Dataset(new_vars, coords=coords, attrs={**self.ds.attrs, "resample_step_s": step_s, "resample_method": method})
        return self._new(ds)

    @records_step
    def smooth_moving(self, window_size: int = 5) -> "ProcessData":
        """Smooth the readings (``pv``, ``device_pv``) with a centred moving average.

        Setpoints and codes are left alone. The window shrinks at the edges and
        skips NaN, so the ends are not pulled towards zero and a gap does not spread.

        Parameters
        ----------
        window_size : int, optional
            Number of samples in the window (default is ``5``).

        Returns
        -------
        ProcessData
            New instance, same ``tos``.

        Raises
        ------
        ValueError
            If ``window_size`` is less than 1.
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        ds = self.ds.copy()
        for name in ("pv", "device_pv"):
            if name in ds:
                values = ds[name].transpose("tos", "channel").values
                smoothed = pd.DataFrame(values).rolling(window_size, center=True, min_periods=1).mean().to_numpy()
                ds[name] = (("tos", "channel"), smoothed, ds[name].attrs)
        ds.attrs = {**ds.attrs, "smooth_moving_window": window_size}
        return self._new(ds)

    @records_step
    def scale(self, channel: str, factor: float, *, fields: Sequence[str] = ("pv",)) -> "ProcessData":
        """Multiply one channel's values by a factor (e.g. a correction factor LabVIEW got wrong).

        LabVIEW v02 multiplied the ``F2 Ar`` reading by F1-He's factor
        (1.123) instead of its own (1.149); ``scale("F2 Ar", 1.149 / 1.123)``
        corrects every logged PV.

        Parameters
        ----------
        channel : str
            The tag.
        factor : float
            The factor.
        fields : sequence of str, optional
            The values to scale (default is ``("pv",)``).

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        KeyError
            If the channel or a field is not present.
        """
        self._check_channels([channel])
        ds = self.ds.copy(deep=True)
        for name in fields:
            if name not in self.fields or name not in FLOAT_FIELDS:
                raise KeyError(f"Cannot scale {name!r}; values: {[f for f in self.fields if f in FLOAT_FIELDS]}")
            ds[name].loc[{"channel": channel}] = ds[name].sel(channel=channel) * factor
        return self._new(ds)

    @records_step
    def rename_channels(self, mapping: Mapping[str, str]) -> "ProcessData":
        """Rename channels, e.g. LabVIEW names onto the tags of the lab-control software.

        ``processdata.labview.b67box5.BOX5_CONTROL_TAGS`` maps the LabVIEW
        names of Box 5 onto box5-control's. A tag the data do not hold is ignored.

        Parameters
        ----------
        mapping : mapping of str to str
            Old tag to new tag.

        Returns
        -------
        ProcessData
            New instance; the old tags are kept in the coordinate ``former_tag``.

        Raises
        ------
        ValueError
            If two channels would get the same tag.
        """
        old = self.channels
        new = [mapping.get(c, c) for c in old]
        if len(set(new)) != len(new):
            raise ValueError(f"Renaming gives duplicate tags: {sorted({t for t in new if new.count(t) > 1})}")
        former = self.ds["former_tag"].values if "former_tag" in self.ds.coords else np.array(old, dtype=object)
        ds = self.ds.assign_coords(channel=("channel", np.array(new, dtype=object)), former_tag=("channel", former))
        return self._new(ds)

    @records_step
    def rename_species(self, convention: ConventionLike = None, unknown: Unknown = "keep") -> "ProcessData":
        """Rename the ``species`` coordinate to a naming convention; tags and values are untouched.

        Parameters
        ----------
        convention : None, str, Path, dict or SpeciesConvention, optional
            ``None`` (default) for the standard convention of
            :mod:`lab_data_parser.naming.species`, a JSON file, an already read
            JSON object, or a convention.
        unknown : {"keep", "raise", "none"}, optional
            What to do with species the convention does not know (default:
            keep the name and warn).

        Returns
        -------
        ProcessData
            New instance; ``ds.attrs["species_convention"]`` names the convention.
        """
        resolved = get_convention(convention)
        species = [resolved.get_canonical(s, unknown) if s else s for s in self.ds["species"].values.tolist()]
        species = ["" if s is None else s for s in species]
        ds = self.ds.assign_coords(species=("channel", np.array(species, dtype=object)))
        ds.attrs = {**ds.attrs, "species_convention": resolved.name}
        return self._new(ds)

    # ---------------------------------------------------------------- export

    def to_dataframe(self, field: str = "pv", with_timestamps: bool = False) -> pd.DataFrame:
        """Return one field of every channel as a wide table indexed by ``tos``.

        Parameters
        ----------
        field : str, optional
            Which value (default is ``"pv"``).
        with_timestamps : bool, optional
            Prepend a ``timestamp`` column when ``tos_start`` is set (default is ``False``).

        Returns
        -------
        pandas.DataFrame
            One column per channel.

        Raises
        ------
        KeyError
            If the field is not recorded.
        """
        if field not in self.fields:
            raise KeyError(f"Field {field!r} not recorded. Available: {self.fields}")
        frame = pd.DataFrame(self.ds[field].transpose("tos", "channel").values, index=pd.Index(self.tos, name="tos"), columns=self.channels)
        if with_timestamps and self.timestamps is not None:
            frame.insert(0, "timestamp", self.timestamps)
        return frame

    def to_csv(self, filepath: PathLike, field: str = "pv") -> None:
        """Write one field of every channel as CSV, with timestamps when ``tos_start`` is set.

        Parameters
        ----------
        filepath : str or pathlib.Path
            Destination.
        field : str, optional
            Which value (default is ``"pv"``).
        """
        self.to_dataframe(field, with_timestamps=self.tos_start is not None).to_csv(filepath)

    def to_netcdf(self, filepath: PathLike) -> None:
        """Write everything (values, events, switches, sessions, history) as NetCDF4, compressed.

        Parameters
        ----------
        filepath : str or pathlib.Path
            Destination.
        """
        ds = self.ds.copy()
        ds.attrs = encode_attrs({k: v for k, v in ds.attrs.items() if v is not None})
        for name in ds.variables:
            ds[name].attrs = encode_attrs({k: v for k, v in ds[name].attrs.items() if v is not None})
            ds[name].encoding = {}
        encoding = {name: {"zlib": True, "complevel": 4} for name in self.fields}
        ds.to_netcdf(filepath, engine="h5netcdf", encoding=encoding)
        logger.debug("Saved NetCDF -> %s", filepath)

    # ---------------------------------------------------------------- constructors

    @classmethod
    @records_step
    def from_day_log(
        cls,
        path: Union[PathLike, Sequence[PathLike]],
        *,
        set_up: Optional[str] = None,
        events: Union[bool, PathLike, Sequence[PathLike]] = True,
        tos_start: Optional[TimestampLike] = None,
        keep_unknown: bool = False,
    ) -> "ProcessData":
        """Read the day files of box2-control or box5-control (CSV, Zarr or NetCDF) and their events.

        Parameters
        ----------
        path : str, pathlib.Path or sequence of them
            A day file (``2026-10-21_box2.csv``, ``.zarr``, ``.nc``), several,
            or the data folder.
        set_up : str, optional
            The set-up to read from a folder several share (``"box2"``).
        events : bool, str, pathlib.Path or sequence of them, optional
            ``True`` (default) reads ``<day>_<set-up>.log`` from beside the data
            file or the ``logs`` folder beside the data folder, ``False`` none,
            a path (file or folder) those.
        tos_start : pandas.Timestamp, datetime, numpy.datetime64 or str, optional
            The origin of ``tos``; default is the start of the first session.
            A naive value is read in the timezone of the log.
        keep_unknown : bool, optional
            Keep a numeric column of a field this version does not know as its
            own variable instead of skipping it (default is ``False``).

        Returns
        -------
        ProcessData
            Every channel, session, event, valve switch and calibration of the files.
        """
        from lab_data_parser.processdata.labcontrol import daylog

        record = daylog.read(path, set_up=set_up, events=events, keep_unknown=keep_unknown)
        return cls(ds=build_dataset(record, tos_start))

    @classmethod
    @records_step
    def from_labview_b67box5(
        cls, filepath: PathLike, *, tos_start: Optional[TimestampLike] = None, keep_unknown_channels: bool = False
    ) -> "ProcessData":
        """Read the LabVIEW log of building 67, box 5 (one file, or a folder of them).

        Every vintage of the export is read (``F1 CO PV`` from 2026-07); a
        folder may mix them. Each file is one session (one LabVIEW start).
        Tags are LabVIEW's (``"F1 He"``); ``rename_channels(BOX5_CONTROL_TAGS)``
        puts them on box5-control's.

        Parameters
        ----------
        filepath : str or pathlib.Path
            A tab-separated ``.txt`` file or a folder of them.
        tos_start : pandas.Timestamp, datetime, numpy.datetime64 or str, optional
            The origin of ``tos``; default is the first row of the first file.
        keep_unknown_channels : bool, optional
            Read a column the parser does not know with empty metadata instead
            of skipping it (default is ``False``).

        Returns
        -------
        ProcessData
            ``pv`` and ``status`` of every channel; a channel a file did not
            record is NaN (``idle``) over its rows.
        """
        from lab_data_parser.processdata.labview import b67box5

        record = b67box5.read(filepath, keep_unknown_channels=keep_unknown_channels)
        return cls(ds=build_dataset(record, tos_start))

    @classmethod
    @records_step
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        timestamp_col: str = "timestamp",
        tos_start: Optional[TimestampLike] = None,
        channel_meta: Optional[dict[str, dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "ProcessData":
        """Build from a table: one timestamp column, one column per channel (its ``pv``).

        Parameters
        ----------
        df : pandas.DataFrame
            The table.
        timestamp_col : str, optional
            The column of absolute timestamps (default is ``"timestamp"``).
        tos_start : pandas.Timestamp, datetime, numpy.datetime64 or str, optional
            The origin of ``tos``; default is the first timestamp.
        channel_meta : dict, optional
            Column -> what is known about the channel (``unit``, ``quantity``, ``species``, ...).
        metadata : dict, optional
            Further attributes for ``ds.attrs``.

        Returns
        -------
        ProcessData
            New instance.

        Raises
        ------
        ValueError
            If ``timestamp_col`` is not a column of ``df``.
        """
        if timestamp_col not in df.columns:
            raise ValueError(f"Column {timestamp_col!r} not found in dataframe")
        stamps = pd.to_datetime(df[timestamp_col])
        origin = None if tos_start is None else pd.Timestamp(tos_start)
        if stamps.dt.tz is None and origin is not None and origin.tzinfo is not None:
            stamps = stamps.dt.tz_localize(origin.tzinfo)
        zone = str(stamps.dt.tz) if stamps.dt.tz is not None else None
        if origin is None and len(stamps):
            origin = stamps.iloc[0]
        elif origin is not None and origin.tzinfo is None and zone:
            origin = origin.tz_localize(zone)
        time = stamps.dt.tz_convert("UTC").dt.tz_localize(None) if zone else stamps
        columns = [c for c in df.columns if c not in {timestamp_col, "tos", "timestamp", "timestamps"}]
        channel_meta = channel_meta or {}
        pv = df[columns].to_numpy(dtype=float) if columns else np.empty((len(df), 0))
        record = {
            "data": {
                "time": time.to_numpy(dtype="datetime64[ns]"),
                "channels": [{"tag": c, **channel_meta.get(c, {})} for c in columns],
                "fields": {"pv": pv, "status": np.where(np.isnan(pv), 3, 0).astype("int8")},
                "rows": {"session": np.ones(len(df), dtype="int16")},
            },
            "meta": {**(metadata or {}), "timezone": zone},
        }
        return cls(ds=build_dataset(record, origin))

    @classmethod
    @records_step
    def from_netcdf(cls, filepath: PathLike) -> "ProcessData":
        """Load a ``ProcessData`` saved with :meth:`to_netcdf`.

        Parameters
        ----------
        filepath : str or pathlib.Path
            The file.

        Returns
        -------
        ProcessData
            The instance as it was saved, its history continued.
        """
        with xr.open_dataset(filepath, engine="h5netcdf") as handle:  # read and close: Windows locks it
            ds = handle.load()
        ds.attrs = decode_attrs(dict(ds.attrs))
        for name in ds.variables:
            ds[name].attrs = decode_attrs(dict(ds[name].attrs))
        return cls(ds=ds)

    # ---------------------------------------------------------------- dunder

    def __repr__(self) -> str:
        duration = float(self.tos[-1] - self.tos[0]) if self.n_samples > 1 else 0.0
        parts = [
            f"set_up={self.set_up!r}" if self.set_up else None,
            f"n_samples={self.n_samples}",
            f"channels={len(self.channels)}",
            f"fields={self.fields}",
            f"sessions={len(self.sessions)}" if self.sessions else None,
            f"events={self.ds.sizes['event']}" if "event" in self.ds.dims else None,
            f"switches={self.ds.sizes['switch']}" if "switch" in self.ds.dims else None,
            f"duration={duration:.1f}s",
            f"tos_start={self.tos_start}" if self.tos_start is not None else None,
        ]
        return f"ProcessData({', '.join(p for p in parts if p)})"

    __str__ = __repr__

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, name: str) -> npt.NDArray:
        return self.get_channel(name)
