# Mixins

How behaviour is shared between the data classes: what a mixin is, the two
that every time-resolved class uses, the topical mixins `SpectroscopyData` is
made of, and how to write or adopt one.

---

## What a mixin is

A *mixin* is a small class that holds a group of related methods and **no
data of its own**. It is never instantiated alone. A core class lists it among
its base classes and so gains its methods:

```python
class ProcessData(TimeOriginMixin, HistoryMixin, BaseModel):
    ds: xr.Dataset
    ...
```

```
             TimeOriginMixin      HistoryMixin       pydantic.BaseModel
             (time origin)        (history)          (fields, validation)
                    │                  │                     │
                    └──────────────────┼─────────────────────┘
                                       ▼
          class ProcessData(TimeOriginMixin, HistoryMixin, BaseModel)
```

Three rules follow from that:

- **No fields, no `__init__`.** The data lives in the pydantic fields of the host (`ds`, `metadata`). A mixin only reads them through `self`.
- **Mixins first, `BaseModel` last.** Python looks a method up from left to right along the *method resolution order* (MRO), so a mixin's method is found before pydantic's machinery, and pydantic still builds the model.
- **A mixin names what it needs.** It uses a few attributes and methods the host has to provide. That short list is its *contract* (below).

### Why mixins and not copies

Setting a time origin works the same for process data, MS, GC and
spectroscopy. Written four times, the copies drift apart: one reads a
timezone-naive time as UTC, another drops the zone, and the same experiment
ends up with three different clocks. That happened before the mixin existed.
Written once, a fix reaches every class at once, and learning
`with_tos_start` on one class means knowing it on all of them.

The rule in [`CONTRIBUTING.md`](../CONTRIBUTING.md): **when a second class needs a
behaviour one class already has, move it into a mixin rather than duplicating
it.** A host adapts a mixin through its hooks, never by overriding or copying
the public methods.

---

## The shared mixins

| mixin | module | gives | needs from the host | used by |
|---|---|---|---|---|
| `TimeOriginMixin` | `lab_data_parser._time` | `tos_start`, `timestamps`, `with_tos_start`, `set_tos_start`, `del_tos_start`, `move_tos_start_by`, `select_timestamp_range` | `ds` (with a `tos` coordinate), `tos`, `_new(ds)`, `select_tos_range(min_s, max_s, empty=...)` | `SpectroscopyData`, `ProcessData`, `MSData`, `GCData` |
| `HistoryMixin` | `lab_data_parser.history` | `history`, `format_history()` | `ds` (the history sits in `ds.attrs["history"]`) | `SpectroscopyData`, `XPSData`, `ProcessData`, `GCData`, `MSData`, `TPRData` |

`XRDData`, `TGAData` and `PhysisorptionData` use neither yet: `XRDData`
stores absolute timestamps as a coordinate instead of a `tos_start`, and the
three do not record a history (tracked as an open issue).

---

## `TimeOriginMixin`: one clock

### What it stores

Every time-resolved class keeps time as `tos`, seconds since one origin, and
the origin itself as **one string** in `ds.attrs["tos_start"]`, written and
read only through `encode_tos_start` / `decode_tos_start`:

```
2026-04-21T14:42:00+02:00[Europe/Amsterdam]
└──────── ISO 8601 ───────┘└── IANA zone ──┘   (RFC 9557)
```

The offset alone (`+02:00`) is the offset of that one instant; it does not
know daylight saving, so a winter run read with a summer origin would show
`+02:00` timestamps. The zone in brackets keeps it right. Plain ISO strings
(older files, fixed offsets) still decode.

### What it gives

| member | kind | what it does |
|---|---|---|
| `tos_start` | property | the origin as a `pandas.Timestamp` in its zone, or `None` |
| `timestamps` | property | `tos_start + tos` for every sample, a `DatetimeIndex`; `None` without either |
| `with_tos_start(t)` | step | re-anchors: `tos` shifts by minus the distance the origin moved, **the timestamps stay** |
| `set_tos_start(t)` | step | stamps a new origin, **`tos` stays**, the timestamps move (to correct a wrong clock) |
| `del_tos_start()` | step | drops the origin, `tos` becomes purely relative |
| `move_tos_start_by(delta)` | step | `with_tos_start(tos_start + delta)`; a number is seconds, else a `pandas.Timedelta` or `"1h30min"` |
| `select_timestamp_range(start, end, empty="warn")` | step | converts the bounds against `tos_start` and hands them to the host's `select_tos_range`, so the two never drift apart; raises without an origin |

The four origin operations follow the `with_` / `set_` / `del_` rule of the
whole package: `with_X` keeps the physical meaning (the moment each sample
was taken), `set_X` forces, `del_X` removes. A *later* origin means
*smaller* `tos` values.

**One timezone rule, everywhere.** Every time a user hands in is read through
`_to_timestamp(value, reference)`: a naive time is wall-clock time **in the
zone of the current origin**, never UTC and never with the zone dropped. So
the time copied off the lab journal means what it says:

```python
data.with_tos_start("2026-04-21 15:12:30")                  # 15:12:30 in Amsterdam, if the origin is
data.select_timestamp_range("2026-04-21 15:00", "18:00")    # bounds read the same way
```

Every step is decorated with `records_step`, so it lands in the history of
whichever host it is called on.

### The host's contract

```python
class Host(TimeOriginMixin, HistoryMixin, BaseModel):
    ds: xr.Dataset                       # with a "tos" coordinate

    @property
    def tos(self): return self.ds.coords["tos"].values

    def _new(self, ds): return Host(ds=ds)          # a copy around another Dataset, keeping what else the host holds

    @records_step
    def select_tos_range(self, min_s=None, max_s=None, empty="warn"):
        mask = window_mask(self.tos, min_s, max_s, what="sample", axis="tos", unit="s", empty=empty)
        return self._new(self.ds.isel(tos=mask))
```

`window_mask` (`lab_data_parser._selection`) is the shared empty-window
rule: a window without a sample logs the range the data cover and returns
the empty selection (`empty="raise"` raises instead); it never silently
returns everything.

### The two hooks

A host that keeps the origin somewhere else as well overrides two hooks, and
never the public methods:

| hook | default | override when |
|---|---|---|
| `_tos_start_raw()` | `self.ds.attrs.get("tos_start")` | the origin is stored elsewhere |
| `_with_tos_start(ds, tos_start)` | writes the encoded origin into `ds.attrs` and returns `self._new(ds)` | a second copy of the origin, or other time-based state, must change with it |

`LVData` used to override both, because it mirrored its attributes into a
second `metadata` dict (a known wart). `ProcessData` keeps everything in
`ds.attrs` and needs neither. Its events and valve switches are stored as
**absolute UTC times** for the same reason: moving the origin cannot leave
them behind, and their `tos` is computed when asked for.

---

## `HistoryMixin` and `records_step`: every object knows how it was made

`HistoryMixin` itself is small: `history` reads `ds.attrs["history"]`
(decoding it if it came from a NetCDF file) and `format_history()` prints it,
one line per step. The work is done by the decorator in the same module:

```python
from lab_data_parser.history import records_step

class Host(HistoryMixin, BaseModel):
    @records_step
    def smooth(self, window: int = 5) -> "Host":
        ...
        return self._new(ds)

    @classmethod
    @records_step                  # under @classmethod, for a constructor
    def from_file(cls, path, *, option=False) -> "Host":
        ...
```

What `records_step` does on every call:

1. **Binds the arguments** to the signature, defaults included, and turns them into JSON (`to_json_safe`): paths become text, timestamps ISO strings, arrays longer than 20 values a summary (shape, first and last value), a data object its type, its sizes and its own history (so `merge` keeps how the other half was made).
2. **Counts the depth** in a context variable. Only the **outermost** decorated call is recorded: `correct_baseline` calls `correct_offset` and `correct_pchip`, and only `correct_baseline` appears. `select_quantity` calls `select_channels`; one entry.
3. **Appends** `{"step", "parameters", "time", "version"}` to the history of the **returned** object, never of the input (`append_history`, which copies the Dataset if the result shares it with the input). A method that returns `self` unchanged records nothing.

For a constructor built from recorded steps that should appear as one, wrap
the inner calls in `suppress_recording()` and add the entry yourself with
`append_history(obj, step, parameters)`; `GCData.from_ezchrom_rslt_groups`
does that. A host that keeps its attributes outside `ds` as well defines
`_with_history(history)`, which `append_history` then calls.

The history is plain JSON, so `to_netcdf` stores it (`encode_attrs`, prefix
`json:`) and `from_netcdf` appends its own entry. It is also what makes a
[`Pipeline`](concepts.md#pipelines-write-the-processing-once-run-it-on-every-run)
replayable: `Pipeline.from_history(obj)` turns the entries back into steps,
and refuses by name a step whose argument was summarised (an array, another
data object).

---

## Topical mixins: `SpectroscopyData` split by subject

`SpectroscopyData` has about 120 methods, too many for one file. Each topic
is a mixin in its own module, and the class is their sum:

```python
class SpectroscopyData(_AxisMixin, _SelectionMixin, TimeOriginMixin, _BackgroundMixin,
                       _BaselineMixin, _SignalMixin, _MergeMixin, _IOMixin, HistoryMixin, BaseModel):
```

| module | mixin | what is in it |
|---|---|---|
| `core.py` | (the class) | the fields, validators, `_new`, `from_arrays`, `_build_ds`, `_carry_auxiliary`, `_slice_auxiliary_to`, the operators `+` and `-`, `__repr__` |
| `_axis.py` | `_AxisMixin` | the axis in every unit (`axis(unit)`, `axis_label`, `wavenumber`, `wavelength_nm`, `energy_eV`, ...), the Raman names (`shift`, the excitation and scattered-light axes), the getters (`values`, `data_type`, `background`, `baseline`, `get_scan`, `get_scan_by_tos`, `get_evolution`, ...) |
| `_selection.py` | `_SelectionMixin` | `sort`, `select_by_idx`, `select_by_tos`, `select_wavenumber_range`, `select_axis_range`, `select_shift_range`, `select_tos_range`, `select_scan_id_range`, `mask_wavenumber_ranges`, `drop_scans`, `drop_spike_scans` |
| `_background.py` | `_BackgroundMixin` | `with_background` and its variants, `set_background`, `del_background`, the `data_type` conversions `to_single_beam`, `to_absorbance`, `to_log_1_r`, `to_kubelka_munk`, ... |
| `_baseline.py` | `_BaselineMixin` | `correct_offset`, `correct_pchip`, `correct_baseline`, `reapply_baseline`, `correct_drift`, `unbaseline`, `del_baseline` |
| `_signal.py` | `_SignalMixin` | smoothing, averaging, normalisation, Gram-Schmidt, signal-to-noise, `find_spike_scans` |
| `_merge.py` | `_MergeMixin` | `merge`, `merge_all` |
| `_io.py` | `_IOMixin` | NetCDF, CSV, the SpectroChemPy and RamanSPy bridges, the generic constructors |
| `_common.py` | (no mixin) | the constants the mixins share: `DataType`, `BACKGROUND_REFERENCED_TYPES`, the OMNIC label map, `_is_spectroscopy_data` |

For a user nothing changes: every method is called on the object as usual.
To find where one lives, open the module of its topic, or ask Python:

```python
[c.__name__ for c in type(ir).__mro__]        # every class SpectroscopyData is built from
import inspect; inspect.getmodule(type(ir).correct_baseline)   # lab_data_parser.spectroscopy._baseline
```

The rules for these mixins:

- **A topical mixin never imports `SpectroscopyData`.** That would be a circular import. Type checks use `_common._is_spectroscopy_data(obj)`, annotations the string `"SpectroscopyData"`.
- **A result is built with `self._new(ds=...)`**, which keeps the metadata, and `self._carry_auxiliary` / `self._slice_auxiliary_to` carry the background and the map coordinates along.
- **A new method goes into the module of its topic**, or a new module if none fits, never into `core.py`.

---

## Writing a new mixin, or adopting one

When a second class needs a behaviour that one class already has:

1. **Move it out** of the class into a mixin in its own module (`lab_data_parser/_<topic>.py` if it is shared across techniques). Keep the public signatures exactly as they were.
2. **Write the contract down** in the module docstring: which attributes and methods the host must provide. Use only those.
3. **Give hooks, not overrides.** Where hosts differ, call a private method with a sensible default (`_tos_start_raw`) that a host may override. A host never overrides the public method.
4. **Decorate the steps** with `records_step`, so every host records them.
5. **List it first** in the bases of every host, before `BaseModel`.
6. **Test it once for every host.** The tests of the time origin are parametrised over all hosts (`tests/test_tos_start.py`, `test_select_timestamp_range.py`, `test_time_origin_naive.py`: one `make_*` builder per class in `BUILDERS`); a new host adds its builder there, a new mixin gets the same kind of test.
7. **Update the table** on this page, in `CONTRIBUTING.md` and in the README.

Pitfalls:

- A mixin with a field breaks pydantic; keep data in the host.
- A `cached_property` on a mixin needs the host's `model_config` to list `ignored_types=(cached_property,)`.
- `_new` must keep everything the host holds besides `ds`, or every step quietly drops it.
- A mixin that needs the host's class (to build a new instance) gets it from `type(self)` or `self._new`, never by import.
