# Process data: `ProcessData`

The operational data of a set-up: flows, pressures, temperatures, valve
positions, and what happened while they were recorded. Whatever ran the
set-up, the result is one class, `ProcessData`
(`lab_data_parser.processdata`):

| software | set-up | what it writes | reader |
|---|---|---|---|
| **box2-control** ([lab-control-b67box2-highpressuresetup](https://github.com/urakawa-group/lab-control-b67box2-highpressuresetup)) | Box 2, high pressure | a day file (CSV or Zarr) and an event file per day | `ProcessData.from_day_log` |
| **box5-control** ([lab-control-b67box5-ftir](https://github.com/urakawa-group/lab-control-b67box5-ftir)) | Box 5, DRIFTS | a day file (CSV) with valve switches, an event file per day | `ProcessData.from_day_log` |
| **LabVIEW** `box5_drifts_v02.vi` | Box 5, DRIFTS (until box5-control takes over) | one tab-separated `.txt` per start | `ProcessData.from_labview_b67box5` |

Both lab-control programs write the same layout, the *lab day-file layout*,
specified in their `docs/data-format.md`. It is shared as that written spec,
never as code: the programs do not import this package and this package does
not import them. A change to the layout bumps the version in the file's
`# format:` line; this reader refuses a version it does not know, rather than
reading it wrong.

```python
import lab_data_parser as ldp

box2 = ldp.ProcessData.from_day_log("01_raw/box2/data")        # every day file, events from ../logs
box5 = ldp.ProcessData.from_day_log("01_raw/box5/data/2026-10-23_box5.csv")
old = ldp.ProcessData.from_labview_b67box5("01_raw/box5/labview", tos_start=tos_start)
```

The older name of the class was `LVData` (subpackage `labview`); it is gone,
without an alias. `LVData.from_b67_box5_txt` is now
`ProcessData.from_labview_b67box5`, and LabVIEW's channel names lost their
`" PV"` (`"Reactor T PV"` is the channel `"Reactor T"`, its value `pv`).

---

## The layout

One `xarray.Dataset` (`data.ds`), four dimensions:

| dimension | what runs along it |
|---|---|
| `tos` | the samples, in seconds since `tos_start`; coordinate `session` |
| `channel` | the tags (`PI-900`, `FIC-500`, `F1-1-He`, `Cell T`); coordinates `quantity`, `unit`, `kind`, `species`, `device`, `description`, and every other scalar of the channel's header line (`device_unit`, `writable`, an MFC's `factor` and `feed`, ...) |
| `event` | the event log: `event_time` (UTC), `event_level`, `event_source`, `event_text`, `event_detail` (a traceback) |
| `switch` | the valve switches: `switch_time`, `switch_kind`, `switch_feed_before`, `switch_feed_after`, `switch_sent`, `switch_confirmed`, `switch_step`, `switch_cycle`, `switch_note`, and any key a newer software adds |

The values, along `tos` x `channel`, as far as the file records them:

| variable | meaning | written by |
|---|---|---|
| `pv` | the process value, in the channel's unit; always there | all |
| `sp` | the setpoint (NaN for an indicator) | box2, box5 |
| `device_pv`, `device_sp` | an MFC's own figures, before its correction factor | box5 |
| `target`, `working`, `requested` | a controller's setpoint layers: where it should go, what is written now (a ramp on its way), what was last asked for | box2 |
| `status` | `0` ok, `1` warning, `2` error, `3` idle (no reading) | all (LabVIEW: ok or idle) |
| `owner` | who set the setpoint: `0` manual, `1` programme, `2` ramp, `3` safety, `-1` none | box2 |
| `mode` | an MFC's control mode as it reports it: `0` bus, `3` fully closed, `8` fully open, `18` bus (RS232), `-1` none | box2 |

and along `tos` alone `state` (`1` reading, `2` controlling) and `estop`
(`1` while the E-STOP is latched). The code variables carry CF
`flag_values` and `flag_meanings`, so the file explains itself in any
NetCDF viewer.

`ds.attrs` holds `tos_start`, `set_up`, `format`, `timezone`, `software`,
`days`, `sessions`, `calibrations`, `source_files`, `event_files`, the
remaining header lines under `header`, and the history.

> [!NOTE]
> **Units stay as the software stored them.** The lab-control programs store
> every quantity in one fixed unit (pressure `bar(a)`, temperature `degC`,
> flow `mLn/min`, normal conditions 0 °C and 1 atm), whatever the device works
> in; the device's own unit is the coordinate `device_unit`. The LabVIEW
> reader writes what we know about its channels in the same notation, so old
> and new runs compare directly. The one exception: LabVIEW logged the vent
> pressure in `bar(g)`.

### Why one value array per field, not one variable per channel

`LVData` kept one variable per column (`"F1 He PV"`). The lab-control files
record up to eight fields per channel, and a column per field per channel
would be 60 variables for Box 5. With `tos` x `channel` arrays, "every
pressure" is `ds.pv.where(ds.quantity == "pressure")`, "every failed
reading" is `ds.status == 2`, and a channel's setpoint sits beside its value.
Box 2's own Dataset (`core/dataset.py`) uses the same shape.

---

## Readers

### `from_day_log(path, *, set_up=None, events=True, tos_start=None, keep_unknown=False)`

`path` is a day file, a list of them, or the data folder.

- **CSV, Zarr and NetCDF.** `2026-10-21_box2.csv`; a Zarr store
  `2026-10-21_box2.zarr` (Box 2 with `[log] format = "zarr"`; needs the extra
  `lab_data_parser[zarr]`); and the NetCDF that `box2 export` writes. All
  three read into the same object.
- **A folder** reads every day file in day order (`<day>_<set-up>.csv`
  before `<day>_<set-up>_2.csv`) and skips the switch tables
  (`*_switches.csv`, a copy of the `# switch:` lines for Excel). Set-ups may
  share a folder: then `set_up="box2"` picks one, and without it the reader
  refuses.
- **Events** are read from `<day>_<set-up>.log` beside the data file or in the
  `logs` folder beside the data folder (the software's defaults, `data/` and
  `logs/`). `events=False` reads none, a path reads those files.
- **Several files** join along time on the union of their channels: a
  `_2.csv` (written when the settings changed the channel set) adds its
  channels, and a channel a file did not record is NaN there with status
  `idle`. One tag in two units refuses to join.
- **Sessions** (Connect to Disconnect) are numbered once across the files. A
  session that ran over midnight goes on in the next day's file under the same
  `tos_start`; it keeps one number, and `sessions[i]["files"]` names both.
- **`tos_start`** is the start of the first session, as the software wrote
  it (with its IANA zone). Give one to re-anchor; a naive time is read in the
  log's timezone. `tos` is computed from the `time (UTC)` column, never from
  the file's per-session `tos / s`, so every session sits on one axis.
- **Unknown columns.** Every column is matched to a tag of a `# channel:` line
  and a field word (`PV`, `SP`, `device PV`, `target`, `status`, ...). A field
  this version does not know is skipped with a warning naming the column;
  `keep_unknown=True` keeps a numeric one as its own variable (`PI-900 drift /
  bar(a)` becomes `drift`). The software can add columns without breaking this
  reader.

### `from_labview_b67box5(filepath, *, tos_start=None, keep_unknown_channels=False)`

The LabVIEW log of Box 5: one tab-separated `.txt` per start, named
`%Y-%m-%d_%H-%M-%S.txt`, comma decimals, a `timestamp` column
`%d-%m-%Y %H:%M:%S` in local time (the repeated hour of the autumn change is
resolved from the monotonic log), no units and no setpoints in the file.

- Each file is one **session** (one LabVIEW start).
- The export **changed over time** (`F1 CO PV` from 2026-07): a folder mixing
  both reads on the union of the columns; an unknown column is skipped with a
  warning (`keep_unknown_channels=True` keeps it). Add it to `CHANNEL_META` in
  `processdata/labview/b67box5.py` to read it with metadata.
- Tags are LabVIEW's, without `" PV"`. `rename_channels(BOX5_CONTROL_TAGS)`
  puts them on box5-control's tags, so one analysis reads old and new runs:

| LabVIEW | box5-control | | LabVIEW | box5-control |
|---|---|---|---|---|
| `Reactor T` | `Cell T` | | `F2 He` | `F2-1-He` |
| `Analytic P` | `BPR Analytic` | | `F2 H2` | `F2-2-H2` |
| `Vent P` | `BPR Vent` (LabVIEW: bar(g), box5-control: bar(a)) | | `F2 CO2` | `F2-3-CO2` |
| `F1 He`, `F1 H2`, `F1 CO2`, `F1 CO` | `F1-1-He`, `F1-2-H2`, `F1-3-CO2`, `F1-4-CO` | | `F2 Ar` | `F2-5-Ar` |
| `Feed` | `Valve` | | | |

> [!WARNING]
> **LabVIEW v02 logged `F2 Ar` 2.3 % low.** Tracing the VI's block diagram
> (box5-control, `docs/labview-inventory.md`) showed that the Ar reading is
> multiplied by F1-He's correction factor (1.123) instead of its own (1.149).
> The setpoint uses the right one. `scale("F2 Ar", 1.149 / 1.123)` corrects
> every logged PV, and the step is recorded in the history.

### `from_dataframe(df, timestamp_col="timestamp", tos_start=None, channel_meta=None, metadata=None)`

A table with a timestamp column and one column per channel (its `pv`);
`channel_meta` maps a column to what is known about it (`unit`, `quantity`,
`species`).

### `from_netcdf(filepath)`

What `to_netcdf` wrote, everything included.

---

## Accessors

- **Channels**: `channels`, `fields`, `channels_of(quantity, species=, kind=)`, `get_channel(tag, field="pv")` (a NumPy array along `tos`), `get_channel_unit(tag)`, `data["PI-900"]` (its `pv`)
- **Time**: `tos`, `tos_start`, `timestamps`, `n_samples`, `sampling_interval`
- **What happened**: `sessions` (each with its start, the ambient pressure, the settings at Connect, the files), `calibrations` (Box 2's zero offsets: tag, new and previous offset, when, and the raw readings behind it), `events` and `switches` (pandas tables, times in the data's timezone, with a `tos` column beside them), `set_up`

```python
data.events[data.events["level"] == "ERROR"]          # what failed, with the traceback in "detail"
data.switches["tos"]                                   # every valve switch, on the samples' axis
(data.ds["status"] == 0).mean("tos")                   # share of good readings per channel
data.ds["pv"].sel(tos=ir.tos, method="nearest")        # the process values at every spectrum
```

## Processing (immutable, recorded)

- `select_channels(tags)`, `select_quantity("flow")`, `select_session(n)`
- `select_tos_range`, `select_timestamp_range`, and the four time-origin methods `with_tos_start`, `set_tos_start`, `del_tos_start`, `move_tos_start_by`. A window cuts the events and switches too.
- `resample(step_s, method)`: fixed-width bins; values by `mean`, `median`, `first` or `last`, skipping NaN; `status` the worst of the bin (error over warning over ok, idle only when nothing was read); `estop` 1 if latched at any time of the bin; the other codes the last value
- `smooth_moving(window_size)`: the readings (`pv`, `device_pv`) only, never setpoints or codes; the window shrinks at the edges and skips NaN
- `scale(tag, factor, fields=("pv",))`, `rename_channels(mapping)` (the old tags are kept as `former_tag`), `rename_species(convention)`

## Export

- `to_netcdf` / `from_netcdf`: values, codes, events, switches, sessions, calibrations, history; the value arrays compressed
- `to_dataframe(field="pv", with_timestamps=False)`, `to_csv(path, field="pv")`: one column per channel

---

## Storage: CSV, Zarr or NetCDF

The question was whether the rigs could log in a compressed binary format
instead of CSV. They can (Box 2 writes Zarr already), and this reader takes
both. Measured on one real Box 2 day (2026-10-22, 52,786 rows at 1 s, 6
channels):

| format | size | read with `from_day_log` | strengths | weaknesses |
|---|---|---|---|---|
| CSV (default) | 7.0 MB (1.3 MB gzipped) | 0.32 s | appends line by line, a crash loses at most the last flush; opens in Excel and any editor; readable in 20 years | large; Excel locks it while open (the software then queues the rows) |
| Zarr (Box 2 `format = "zarr"`) | 2.0 MB in 63 files | 0.22 s | compressed, chunked, appendable | a folder of many small files (one per 600-row chunk and variable): slow on OneDrive and network drives; no Excel; a crash mid-append can damage the last chunk |
| NetCDF4 (`box2 export`, `to_netcdf`) | 1.9 MB; 1.4 MB from `ProcessData.to_netcdf` | 0.10 s | one compressed file, self-describing, every tool reads it | not appendable while the rig runs |

**Recommendation.** Keep **CSV as the raw log on the rig** (`01_raw`): it is
what survives a power cut, and its size does not matter at a few MB a day.
Turn a run into **one NetCDF** with `ProcessData.to_netcdf` in `02_processed`,
next to the spectra and MS data of the same run. Zarr pays off only for one
store that keeps growing over weeks; for day files it adds a folder of small
files and buys a factor of 3.5 that NetCDF gives too. A finished month of CSV
days can be zipped for the archive, but unzip before reading: a gzip stream
cannot be appended to, so it is no format for a running log.

---

## Notes for the lab-control software

What would make the logs more useful still. None of these is needed for the
reader to work.

- **Write `"species"` in the channel line of every flow.** Box 5 names the gas
  only in the tag (`F1-1-He`) and the description (`feed 1, He`); the reader
  takes it from the tag pattern `F<line>-<n>-<species>` for now. Box 2's MFCs
  carry no species at all.
- **One key for the set-up.** Box 2 writes `# bench: box2`, Box 5
  `# set-up: box5`. Both are read; one name would be cleaner.
- **One time format.** The `# switch:` record holds Unix seconds (`"time":
  1792738860.0`), everything else ISO 8601 with offset. Both are read.
- **`estop` in Box 5**, once it has an E-STOP (phase 5); without the column
  the variable is simply absent.
- **Commanded switches** (phase 5) with `sent` and `confirmed`, and `step` /
  `cycle` from the programme runner (phase 7): the reader keeps every key of a
  switch record, so they arrive without a change here.

## Parsers

- `lab_data_parser.processdata.labcontrol.daylog`: `read` (files, folders, events, joined), `read_csv`, `read_dataset` (Zarr and NetCDF), `read_events`, `find_day_files`, `find_event_files`, `switch_columns`; the field table `FIELDS` and the codes `STATUS_CODES`, `STATE_CODES`, `OWNER_CODES`, `MODE_WORDS`
- `lab_data_parser.processdata.labview.b67box5`: `read`, `CHANNEL_META`, `BOX5_CONTROL_TAGS`

Both return the record `ProcessData` is built from (`build_dataset`):
`{"data": {"time", "channels", "fields", "rows"}, "meta": {...}, "events":
{...}, "switches": {...}}`, times in UTC. A reader for another program fills
the same record and never touches the class.

See also: [examples/process_data.ipynb](../../examples/process_data.ipynb),
[High pressure in Box 2](../examples/high-pressure-box2.md),
[DRIFTS in Box 5](../examples/drifts-box5.md).
