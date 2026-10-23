# Concepts

How the package is put together, and the seven ideas every data class shares.
Learn them once and every class reads the same way. How behaviour is shared
between the classes is its own page: [Mixins](mixins.md).

| concept | in one line |
|---|---|
| 🧱 [**Layers**](#how-the-package-is-structured) | raw file, parser, (vendor converter), data class: each talks only to its neighbour |
| 📜 [**History and logging**](#processing-history-and-logging-every-object-knows-how-it-was-made) | every object knows how it was made |
| 🕒 [**`tos_start`**](#tos_start-anchoring-time-on-stream-to-the-clock) | one clock for all instruments |
| 🔒 [**Immutability**](#immutable-transformations-every-method-returns-a-new-object) | every method returns a new object |
| 🔁 [**Pipelines**](#pipelines-write-the-processing-once-run-it-on-every-run) | write the processing once, run it on every run |
| 💾 [**NetCDF cache**](#read-once-cache-as-netcdf) | parse once, load fast, never next to the raw files |
| 🏷️ [**Species names**](#species-naming-conventions) | one canonical name per species, across instruments |
| 🧩 [**Mixins**](mixins.md) | shared behaviour is written once and mixed into every class |

---

## How the package is structured

Four layers, and each one only talks to the one next to it.

```
raw files --> parser module --> (vendor converter) --> core data class --> your analysis
              "data" + "meta"     common records        GCData, SpectroscopyData, ...
              dict, as written    SI units              xarray, immutable
```

**1. One subpackage per technique.** `spectroscopy` (with the `infrared`,
`raman` and `xps` readers inside), `massspec`, `processdata`, `xrd`, `tga`,
`tpr`, `physisorption`, `chromatography`. Peak shapes are not technique
specific and sit in one top-level module, `lab_data_parser.kernels` (Gaussian,
Lorentzian, pseudo-Voigt, Voigt; CasaXPS `GL`, `SGL`, `LA`), which every fit
imports. The pseudo-Voigt fraction `eta` is height-weighted unless
`fraction="area"` is passed (the diffraction convention). Inside each subpackage sits the core class in `core.py`
and one parser module per instrument or software (`omnic.py`, `quadstar.py`,
`daylog.py`). Where a technique has several manufacturers, each gets its own
subfolder (`chromatography/agilent/`), so a second vendor is added next to the
first and never inside it.

**2. Parser modules read, they do not interpret.** A parser returns a plain
dict with a `"data"` and a `"meta"` key, never a data class. It reads
everything the format offers, including what nobody has asked for yet, and
keeps it as the instrument wrote it: vendor names, vendor units, raw counts
next to scaled values. A parser should not fail on a file it can partly read.
Instrument exports drift over time (a new column, a renamed channel), so an
unknown entry is skipped with a warning, and old and new files read side by
side. Time comes from what the instrument recorded, not from a file name.

**3. A vendor converter where several vendors meet.** When different
manufacturers deliver the same kind of data, each vendor module translates
its own dict into one common record format (`ezchrom.to_injections()` for
chromatography). This is the only place where vendor names become generic
ones, minutes become seconds and counts become detector units. The core class
knows the common format only, so adding a vendor never touches it.

**4. One core class per technique.** `GCData`, `SpectroscopyData`, `MSData`,
`ProcessData`, ... wrap an `xarray` object in a pydantic model, so axes, units and
metadata travel with the numbers. The rules they share:

- **Built by `from_*` classmethods** (`from_ezchrom_rslt`, `from_omnic_spa`, `from_netcdf`), never by hand. Everything after the data arguments is keyword-only.
- **Immutable.** Every method returns a new object, so the raw object is always still there to compare against.
- **Shared where it is the same thing.** The time origin (`tos_start`, `timestamps`, the four origin operations, `select_timestamp_range`) and the history accessors are one implementation, mixed into every class (`lab_data_parser._time`, `lab_data_parser.history`); `SpectroscopyData` itself is composed of topical mixins (`spectroscopy/_axis.py`, `_selection.py`, `_background.py`, `_baseline.py`, `_signal.py`, `_merge.py`, `_io.py`). See [Mixins](mixins.md).
- **SI units for the axis.** Seconds, m⁻¹, eV for binding energy; convenience properties give the usual lab units. Values stay in the unit the instrument or software stores them in where that is the lab's working unit (`TPRData` in mV and °C, `ProcessData` in bar(a), degC and mLn/min), with the unit next to them.
- **One time origin.** `tos` in seconds plus one `tos_start` (see [`tos_start`](#tos_start-anchoring-time-on-stream-to-the-clock)), so every instrument shares the same clock.
- **Same names for the same operation in every class.** `select_tos_range`, `with_tos_start`, `merge`, `to_netcdf`, `rename_species`. Once one class is known, the others read the same way.
- **Metadata is kept, not trimmed.** What has no typed accessor yet is stored verbatim (JSON-encoded where NetCDF needs it), so it is there when it is needed.
- **Reachable from the root.** `ldp.GCData` is `ldp.chromatography.GCData`.
- **Every step is recorded.** The object carries its own processing history, and it survives saving (see [Processing history](#processing-history-and-logging-every-object-knows-how-it-was-made)).
- **One data class where techniques measure the same thing.** IR and Raman are both `SpectroscopyData` on one `wavenumber` axis; `IRData` and `RamanData` are only the readers.

**Across all of them, two shared helpers.** `naming` maps the spellings of a
species onto one convention, as an explicit `rename_species()` step and never
silently on read. And nothing is ever written next to the raw files: processed
data goes to its own folder (see [Read once, cache as NetCDF](#read-once-cache-as-netcdf)).

---

## Processing history and logging: every object knows how it was made

Two records are kept, and they answer different questions:

| | 📜 processing history | 🪵 log |
|---|---|---|
| answers | *what was done to this data?* | *what did the parser decide on the way?* |
| lives in | `ds.attrs["history"]`, on the object | `lab_data_parser.log`, per session |
| travels with the data | ✅ yes, survives `to_netcdf` | ❌ no |
| read it when | you want to know what a file is | a result looks odd |

**The processing history.** Every constructor and every processing step appends one entry to the object it *returns*, never to its input:

```
from_omnic_spa ──► select_tos_range ──► correct_baseline ──► to_netcdf ──► from_netcdf
      │                   │                    │                                │
      ▼                   ▼                    ▼                                ▼
  history[0]          history[1]           history[2]                       history[3]
```

```python
ir = (
    ldp.IRData.from_omnic_spa(dir_spa, tos_start=tos_start)
    .select_tos_range(0, 6 * 3600)
    .correct_baseline(anchor_range_cm=(2600, 2500), control_points_cm=[3450, 2720, 1750])
)
print(ir.format_history())
# 1. 2026-10-15T09:12:03+00:00  from_omnic_spa(filepath='.../spa', ..., tos_start='2025-05-15T10:00:00+02:00', ...)
# 2. 2026-10-15T09:12:04+00:00  select_tos_range(min_s=0, max_s=21600)
# 3. 2026-10-15T09:12:04+00:00  correct_baseline(anchor_range_cm=[2600, 2500], control_points_cm=[3450, 2720, 1750], ...)

ir.history[-1]   # {"step": "correct_baseline", "parameters": {...}, "time": "...", "version": "0.2.0"}
```

- **One entry per call you made.** `correct_baseline` calls `correct_offset` and `correct_pchip` internally; only `correct_baseline` is listed.
- **Every argument is stored**, files included, so the first entry says which raw data this came from. Arrays longer than 20 values are summarised (shape, first and last value).
- **`merge` nests histories:** it stores the other segment's own history inside its entry, so a merged run still says how each half was made.
- **It survives `to_netcdf` / `from_netcdf`;** loading adds a `from_netcdf` entry. A cached file still tells you, months later, which files and which baseline settings produced it.
- **Available on** `SpectroscopyData`, `XPSData`, `GCData`, `MSData`, `ProcessData` and `TPRData` (`.history`, `.format_history()`); `to_spectrochempy()` copies it into the `NDDataset`'s own history.

> [!NOTE]
> `XRDData`, `TGAData` and `PhysisorptionData` do not record a history yet. The older, step-specific records stay where they were and survive storing too: `merge_log` (spectroscopy), the baseline parameters `baseline_anchor_range_cm` / `baseline_pchip_*` (used by `reapply_baseline`), and `trace_corrections` (MS).

**The log.** Interpolated a background, dropped a baseline, found two merge segments overlapping, skipped an unknown column: these are warnings and info messages on the `lab_data_parser` logger.

```python
ldp.logging.setup_logger("INFO")                               # writes lab_data_parser.log in the working directory
ldp.logging.setup_logger("DEBUG", use_console_handler=True)    # also to the console
ldp.logging.disable_logging()
```

---

## `tos_start`: anchoring time-on-stream to the clock

Every data class stores time as *time-on-stream* (`tos`): elapsed seconds since the experiment began. It does not depend on clocks or timezones and survives every transformation and NetCDF round trip. One `tos_start`, a timezone-aware `pandas.Timestamp`, links it back to the wall clock. Absolute timestamps are derived on demand as `tos_start + tos` and never stored.

```
wall clock   14:42:00          15:12:30                    18:00:00
                │                  │                           │
tos_start ──────●                  │                           │
tos / s         0 ─────────────► 1830 ──────────────────────► 11880
                │                  │                           │
  Process  ─────┼──────────────────┼───────────────────────────┼──
  MSData   ─────┼──────────────────┼───────────────────────────┼──
  IRData   ─────┼──────────────────┼───────────────────────────┼──
                       one tos value = the same instant in every dataset
```

```python
tos_start = pd.Timestamp("2026-04-21 14:42:00", tz="Europe/Amsterdam")

lv = ldp.ProcessData.from_day_log(dir_box5_data, tos_start=tos_start)
ms = ldp.MSData.from_quadstar_asc(asc_file, tos_start=tos_start)
ir = ldp.IRData.from_omnic_spa(dir_spa, tos_start=tos_start)
```

> [!TIP]
> Give `tos_start` a **named timezone** (`tz="Europe/Amsterdam"`), not a fixed offset (`+02:00`). The zone name is stored with the origin (`2026-04-21T14:42:00+02:00[Europe/Amsterdam]`), so timestamps follow daylight saving: a March run anchored to a May origin still shows `+01:00`. Leave `tos_start` out and `ProcessData` and `MSData` take the start recorded in the file.

### Changing the origin afterwards

`ProcessData`, `SpectroscopyData`, `MSData` and `GCData` expose the same four immutable methods, mirroring the `with_` / `set_` / `del_` trio used for backgrounds. What matters is **what stays fixed**:

| method | what it changes | what stays fixed |
|---|---|---|
| `with_tos_start(tos_start)` | re-anchors: `tos` shifts by minus the distance the origin moved | 🔒 the absolute timestamps |
| `set_tos_start(tos_start)` | stamps a new origin, `tos` untouched | 🔒 the `tos` values (the timestamps move with the origin) |
| `del_tos_start()` | drops the origin | 🔒 `tos`, now a purely relative axis (`timestamps` is `None`) |
| `move_tos_start_by(delta)` | `with_tos_start(tos_start + delta)` | 🔒 the absolute timestamps |

> [!TIP]
> Use `with_tos_start` when the **reference point** of the experiment changes (re-zeroing to when gas flow started rather than when logging did). Use `set_tos_start` when the elapsed times are right but the **wall clock** they were anchored to was wrong.

```python
# Re-zero all three datasets to the moment reaction gas hit the reactor.
t_reaction = pd.Timestamp("2026-04-21 15:12:30", tz="Europe/Amsterdam")
lv, ms, ir = (d.with_tos_start(t_reaction) for d in (lv_raw, ms_raw, ir_raw))
# tos == 0 now means the same instant everywhere; timestamps are unchanged.

# Straight off the log book: a naive time is read in the data's own timezone.
ir = ir.with_tos_start("2026-04-21 15:12:30")

# Nudge the origin 90 s later (equivalently: shift every tos down by 90 s).
ir = ir.move_tos_start_by(90)          # seconds
ir = ir.move_tos_start_by("1h30min")   # or any pandas.Timedelta / string
```

> [!WARNING]
> **Mind the sign:** moving the origin **later** makes every `tos` value **smaller**. Pass a negative `delta` to move the origin earlier. `XRDData` stores absolute timestamps as a coordinate instead and has no such family.

### Cutting a window by wall clock

The same four classes crop either way, and the two always agree because the absolute form converts its bounds and delegates:

```
select_timestamp_range(start, end) ──(bounds minus tos_start)──► select_tos_range(min_s, max_s)
        absolute wall clock                                            elapsed seconds
```

Bounds are inclusive and either may be `None` for an open end. They may be a `pandas.Timestamp`, a `datetime`, a `numpy.datetime64` or any string pandas can parse.

```python
# "From when reaction gas was switched in until I went home."
ir = ir_raw.select_timestamp_range("2026-04-21 15:12:30", "2026-04-21 18:00:00")

# Same window on all three instruments, no seconds arithmetic in sight.
t0 = pd.Timestamp("2026-04-21 15:12:30", tz="Europe/Amsterdam")
lv, ms, ir = (d.select_timestamp_range(t0, t0 + pd.Timedelta(hours=3))
              for d in (lv_raw, ms_raw, ir_raw))
```

> [!NOTE]
> A **timezone-naive bound** is read as wall-clock time **in the timezone of `tos_start`**, not as UTC: write the time you read off the log book and it means what you think it means. Without a `tos_start` the method raises.
>
> An **empty window** logs a warning naming the range the data cover and returns an empty object, so the rest of a pipeline simply has nothing left to do. Pass `empty="raise"` to stop with a `ValueError` instead.

---

## Immutable transformations: every method returns a new object

No processing method mutates the object it is called on. Every method returns a *new* instance, so the raw data is always still there to compare against, and steps chain into one readable expression.

```
ir_raw ──select_tos_range──► (new) ──correct_baseline──► ir
  │                                                       │
  └── unchanged, still the raw data                       └── processed
```

```python
ir = (
    ir_raw
    .select_tos_range(0, 6 * 3600)
    .correct_baseline(anchor_range_cm=(2600, 2500),
                      control_points_cm=[3450, 3100, 2720, 1750, 1230])
)

ms = ms_raw.select_tos_range(0, 6 * 3600).correct_traces().mask_overloaded()
lv = lv_raw.select_tos_range(0, 6 * 3600)
```

| ✅ do | ❌ don't |
|---|---|
| `ir = ir_raw.normalise_max()` | `ir_raw.normalise_max()` and expect `ir_raw` to change |
| `*_raw` for the freshly loaded object, a plain name for the processed one | reuse one name for raw and processed data |

---

## Pipelines: write the processing once, run it on every run

A `Pipeline` is a list of steps, each a method name plus its keyword arguments. It applies to any data class, maps over a dict or list, is plain JSON, and is the inverse of the history:

```
                     Pipeline.from_history(ir)
        ┌──────────────────────────────────────────────┐
        │                                              ▼
   ir.history  ◄──── pipeline(ir_raw) ────  Pipeline ([step, step, ...])
   (on the data)                              │   ▲
                                      to_json │   │ from_json
                                              ▼   │
                                          pipeline.json
                                    (next to the processed data)
```

"Do to this run what I did to that one" is one line:

```python
from lab_data_parser import Pipeline

drifts = Pipeline([
    ("select_tos_range", {"min_s": 0, "max_s": 6 * 3600}),
    ("correct_baseline", {"anchor_range_cm": (2600, 2500), "control_points_cm": [3450, 2720, 1750]}),
    ("select_wavenumber_range", {"min_cm": 1000, "max_cm": 3900}),
    "normalise_max",
], name="drifts standard")

ir = drifts(ir_raw)                                   # one object; every step lands in ir.history
runs = drifts.map({"run_1": ir_1, "run_2": ir_2})     # several, keys kept
regions = Pipeline(["to_cps", ("subtract_background", {"method": "shirley"})]).map(ldp.XPSData.from_vamas(path))

drifts.to_json(folder / "pipeline.json")              # next to the processed data
same = Pipeline.from_json(folder / "pipeline.json")
replay = Pipeline.from_history(ir)                    # the steps that made ir, minus the constructor
stage = Pipeline.from_history(ir, since="from_netcdf")  # only what this processing stage did
```

> [!NOTE]
> A step whose argument was an array or another data object (`with_background(ir_bg)`) is kept in the history only as a summary, so `from_history` refuses it by name and you add that step by hand. Pipelines are immutable: `append` and `+` return new ones.

---

## Read once, cache as NetCDF

Parsing hundreds of `.spa` files is slow. Parse and pre-process once, save to NetCDF, then load the NetCDF on every later run. Metadata, backgrounds, coordinates and the processing history all survive the round trip. Files are NetCDF4 (HDF5), written through `h5netcdf`.

```
first run:   raw files ──parse──► ir_raw ──to_netcdf──► ir.nc          (slow, once)
later runs:                        ir.nc ──from_netcdf──► ir_raw        (fast)
```

```python
# First run: parse raw files, assign background, save.
ir_raw = (
    ldp.IRData.from_omnic_spa(dir_spa, tos_start=tos_start)
    .with_background(ldp.IRData.from_omnic_spa(bg_file, tos_start=tos_start))
)
ir_raw.to_netcdf(cache_path)

# Every subsequent run: fast load.
ir_raw = ldp.SpectroscopyData.from_netcdf(cache_path)
```

The same pattern applies to `XPSData`, `MSData`, `ProcessData`, `GCData` and `PhysisorptionData`.

### Where the NetCDF file goes: never next to the raw files

`lab_data_parser` only reads and writes; where a file belongs is up to you. The group's recommendation is three data stages per experiments folder:

```
experiments/
├── 01_raw/<rig>/<run folder>/                    🔒 what came from the machine, read-only
│   ├── omnic/   ms/   process/
├── 02_processed/<project>/<run folder>/          ✏️ anything this package has touched
│   ├── 01_loaded/   ir.nc  ms.nc  process.nc          numbered steps, run folder named as in 01_raw
│   └── 02_baseline/ ir.nc  pipeline.json
└── 03_plot/<project>/<figure>/                   📊 the data behind one figure
```

> [!WARNING]
> **Nothing is saved into `01_raw`.** A cache written into the raw `omnic/` folder is a derived file in the wrong place.

---

## Species naming conventions

Every setup writes its species differently. `lab_data_parser.naming` maps all spellings onto one canonical name, so data from different instruments can be compared, merged and handed to models without a lookup table in every notebook:

```
GC method        "Methanol"  ─┐
mass-flow ctrl   "CH3OH"     ─┼──► rename_species() ──►  "MeOH"
spreadsheet      "methanol"  ─┘
```

A convention is a human-readable JSON file. The standard one, `src/lab_data_parser/naming/species/naming_species_standard.json`, uses short canonical names (`CO2`, `CO`, `H2`, `MeOH`, `H2O`, `CH4`, `DME`, `MF`, `EtOH`, `PrOH`, `Ar`, `N2`, `He`, ...):

```json
"MeOH": {"name": "methanol", "formula": "CH3OH", "aliases": ["CH4O"]}
```

The key, `name`, `formula` and every alias all resolve to the key. Matching ignores case, spaces, hyphens, underscores and dots and reads subscript digits as digits, so `ch4`, `CH₄`, `Methane` and `Methan` are all `CH4`.

```python
from lab_data_parser.naming import rename_species, SpeciesConvention

rename_species(["Methanol", "ch4", "CO₂", "1-propanol"])   # ['MeOH', 'CH4', 'CO2', 'PrOH']

# your own convention: a JSON path, an already read dict, or a SpeciesConvention
rename_species("C1", "path/to/my_convention.json")
rename_species("C1", {"CH4": ["C1", "methane"]})              # flat form {canonical: [aliases]}

# or the standard plus your setup's own spellings
box2_names = SpeciesConvention.standard().extend({"CH4": ["C1"]})
```

| ✅ do | ❌ don't |
|---|---|
| add a spelling to `naming_species_standard.json` | map spellings by hand in a notebook |
| rename explicitly with `rename_species()` | expect a parser to rename on read (it never does) |

> [!NOTE]
> Names the convention does not know are kept unchanged with a warning (`unknown="raise"` or `"none"` to change that). A convention in which two species claim the same spelling is refused when it is loaded. `GCData` (peak table and amounts) and `ProcessData` (the `species` coordinate of its channels) have an immutable `rename_species(convention=None)`; without a convention it uses the standard one.
