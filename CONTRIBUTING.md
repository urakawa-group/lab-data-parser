# Contributing

The contract for everyone who changes this repository, people and coding
assistants alike: how to run it, the conventions, and the architecture with
the reasons behind it. The pages under `docs/` are the user-facing summary;
this file is the rule.

## Commands

```bash
# Set up the environment (runtime deps, the optional backends and the dev tools)
uv sync --group dev

# Install in editable mode into an existing environment
uv pip install -e .

# Run all tests
pytest

# Run a single test file
pytest tests/spectroscopy/raman/test_raman_data.py

# Run a single test by name
pytest tests/spectroscopy/raman/test_raman_data.py::test_function_name

# Build the wheel and sdist (what the group installs)
uv build
```

The project uses `uv` for dependency management. The lockfile is `uv.lock`; add
new dependencies via `uv add <package>`. SpectroChemPy, RamanSPy, `requests`
and `zarr` are optional extras (`lab_data_parser[spectrochempy]`, `[ramanspy]`,
`[url]`, `[zarr]`, `[all]`); import them lazily inside the function that needs
them, never at module level.

## Documentation layout, and what mirrors this file

- `README.md`: introduction, the philosophy (no code beyond a first snippet), how to start (git and uv, a downloaded copy, JupyterLab), and links. Keep it short; detail goes into `docs/`.
- `docs/concepts.md`: the layers, history, `tos_start`, immutability, pipelines, the NetCDF cache, species names.
- `docs/mixins.md`: the mixin design in detail (contract, hooks, `records_step`, the topical mixins of `SpectroscopyData`, how to add one).
- `docs/conventions.md`: the user-facing summary of the rules below (docstrings, naming, method prefixes, units, text and plot style).
- `docs/instruments/<technique>.md`: one page per data class (layout, readers, accessors, processing, export, parsers), plus `docs/instruments/README.md`, the overview table.
- `docs/examples/`: worked examples on real files (`drifts-box5.md`, `high-pressure-box2.md`); their code is run before it is written down, and their figures are in `docs/static/`.

When a rule here changes, change `docs/conventions.md` (or `docs/mixins.md`)
in the same edit; when a class gains or changes a public method, update its
instrument page. The docs are the summary; this file stays the contract.

## Docstrings

All public classes, methods, functions, and properties must have a NumPy/SciPy-style docstring:

```python
def example(param1: int, param2: str = "default") -> list:
    """Short one-line summary.

    Optional extended description (only when non-obvious).

    Parameters
    ----------
    param1 : int
        Description of param1.
    param2 : str, optional
        Description of param2 (default is "default").

    Returns
    -------
    list
        Description of the return value.

    Raises
    ------
    ValueError
        When and why this is raised.
    """
```

Rules:
- One-line summary on the opening `"""` line.
- Skip the `Parameters` section for zero-argument methods/properties.
- Skip the `Returns` section for `None`-returning methods.
- `Raises` only when the function actually raises.
- Private helpers (leading `_`) do not need docstrings.

## Naming

Use full, unabbreviated names for fields, columns, properties, and variables:
`relative_pressure`, not `p_rel`; `quantity_adsorbed`, not `q`; `temperature`,
not `temp`; `wavenumber_to_si_factor`, not `wavenumber_2SI_factor`. Established
names of the technique or method itself are fine to keep as-is (`BET`, `BJH`,
`XRD`, `IR`, `MS`, `TGA`): these are not abbreviations of a longer phrase, they
are what the method is actually called.

### Species, not components

A chemical species is always called **species**: in variables, dims, coords,
columns, record keys and docstrings (`species`, `species_name`,
`species_detector`, `peak_species`, `rename_species`). Never **component**,
which in this lab also means a mechanical part of a setup (and stays correct
for mathematical components, e.g. quadrature components). Not **compound**
either: that is the vendor's word, kept only where a vendor format names it
(the ACAML `Compound` tags, the Compound File Binary container).

Species names follow a naming convention, see *Species naming conventions*
below. Parsers keep the names exactly as the instrument wrote them; renaming
is an explicit `rename_species()` step, never done silently on read.

### Combining two datasets

Three different operations, three different names, never mixed up:

- **extend**: joining along the energy-related axis (wavenumber, Raman shift, 2θ, m/z), i.e. widening the spectral range.
- **merge**: joining along the *other* axis (scan/time), i.e. appending more scans of the same spectral range. `SpectroscopyData.merge` / `merge_all`, `GCData.merge`.
- **vstack**: taking already 2-D data and stacking it along a *new*, additional dimension.

### Selection methods

A `method` argument that is handed to `xarray`'s `.sel` offers exactly what
`.sel` has: `"nearest"`, `"pad"`, `"backfill"`. Never advertise `"linear"`
there; linear interpolation is `.interp`, a different operation, and gets its
own method if it is ever needed.

## Text & plot style conventions

Applies to code comments, docstrings, printed/repr output, and figures (titles, axis labels, tick labels, legends, annotations). The same rule set is summarised in `docs/conventions.md`; keep the two in sync if this changes.

- No em dashes ("—"). Use a comma, colon, period, or separate sentence instead. En dashes in numeric ranges are fine (`780–900 cm⁻¹`).
- Capitalize only in headers/titles, proper nouns, or where otherwise grammatically correct. Axis labels, tick labels, legend entries, and other in-plot text are lowercase by default.
- Axis labels use the format `quantity / unit` (the quantity divided by its unit), e.g. `time / s`, `temperature / K`. If the quantity is dimensionless, use an en dash "–" in place of the unit, e.g. `fraction / –`.
- Units and exponents use power notation, not slashes: `m^2 s^-1`, `mol m^-3 s^-1`, not `m^2/s`, `mol/m^3/s`. Applies in code, plots, printed output, and LaTeX math. In written documents, `\frac{}{}` fraction style is fine in math environments; code and plots still use the power form.
- Chemical species, formulas and reactions use the mhchem `\ce{}` package, always inside math: `$\ce{CO2}$`, `$\ce{Cu^0}$`, `$\ce{Al^3+}$`, `$\ce{CO2 + 3H2 <=> CH3OH + H2O}$`. Applies to Markdown notes and LaTeX documents. Plain text stays only where math cannot render: file names, titles, and code. Plot labels (set 2026-10-18): matplotlib has no mhchem, so a species standing as a name (legend entry, annotation) is written `$\mathsf{CO_2}$`, `$\mathsf{Al^{3+}}$`, `$\mathsf{CO_2 + 3H_2 \rightleftharpoons CH_3OH + H_2O}$`: `\mathsf` resolves to Source Sans 3, so the formula matches the words beside it. A species as the subscript of a quantity stays `\mathrm` (`$S_\mathrm{MeOH}$`, `$E_\mathrm{a}$`) to match the maths symbol it hangs on. Not `$\mathrm{CO_2}$` for a bare species: on print presets that comes out in Source Serif 4, a serif formula in sans text.
- Fonts: two open families, Source Sans 3 and Source Serif 4. Source Sans 3 is used for all figure and slide text, with hierarchy by size and weight, never a second sans. Maths matches the body text it sits beside: Source Serif 4 in print figures and documents, Source Sans 3 italic on slides. Words and units upright, quantities italic. Matplotlib uses mathtext, not usetex. Slides use Source Sans 3 (embedded in the pptx) instead of Segoe UI. LaTeX documents: LuaLaTeX, Source Serif 4 body, Source Sans 3 headings and captions, unicode-math with Source Serif 4 letters over STIX Two Math symbols.
- Citing a paper where the reference stands alone, on a slide or in a source line on a figure (set 2026-10-18; not for running text, where the document's own citation style applies, numbered or a short author-year form, and the bibliography follows that same style): `<first author> et al. (<group lead>), <journal abbreviation> <year>`, e.g. `Vico van Berkel et al. (Urakawa), J. Catal. 2024`. The bracket names the professor or well-known name behind the paper, usually the last author, and is dropped when the first author is that name (`Urakawa et al., J. Phys. Chem. C 2019`). Two authors: `Maeder & Zilian, Chemom. Intell. Lab. Syst. 1988`; one: `Noda, Appl. Spectrosc. 1993`. Journal abbreviations as Zotero gives them (ISO 4, with dots).

## Architecture

**lab-data-parser** (`lab_data_parser`) is a data-parsing library for experimental equipment used in catalysis research (Urakawa group, TU Delft). It is under active development and the API changes frequently.

### Module layout

Each instrument type lives in its own subpackage under `src/lab_data_parser/`:

| Subpackage | Core class | Backing store |
|---|---|---|
| `processdata` | `ProcessData`, the operational data of a set-up (LabVIEW, box2-control, box5-control) | `xr.Dataset` |
| `xrd` | `XRDData` | `xr.DataArray` |
| `spectroscopy` | `SpectroscopyData`, the one class for IR and Raman; `IRData` (`infrared/readers.py`) and `RamanData` (`raman/readers.py`) are reader namespaces, not classes; `XPSData` (`xps/core.py`) for photoelectron spectra | `xr.Dataset` |
| `tga` | `TGAData` | two NumPy arrays |
| `tpr` | `TPRData` | `xr.Dataset` |
| `massspec` | `MSData` | `xr.Dataset` |
| `physisorption` | `PhysisorptionData` | `xr.DataArray` |
| `chromatography` | `GCData` | `xr.Dataset` |
| `kernels` | *(module, no data class)*; the peak shapes every fit uses, see *Kernels* below | none |
| `naming` | *(no data class)*; `species` conventions and `rename_species` | JSON files |
| `pipeline` | *(no data class)*; `Pipeline` and `Step` | JSON files |

Every subpackage follows the same structure:
- `core.py`: the Pydantic `BaseModel` wrapper class
- one parser module per instrument/software (e.g. `renishaw.py`, `omnic.py`, `quadstar.py`)

### Core design patterns

**Pydantic `BaseModel` wrappers.** All core classes subclass `pydantic.BaseModel`. The xarray object is stored as a field; field validators handle construction-time checks and never edit the object they are given (copy, then assign attributes).

**Core classes are re-exported at the package root.** `ldp.GCData is ldp.chromatography.GCData`, and the same for every core class plus `IRData` / `RamanData` (the spectroscopy readers), `rename_species` / `SpeciesConvention` and `Pipeline` / `Step`. A new core class gets its line in `lab_data_parser/__init__.py` (and in `tests/test_top_level_imports.py`) in the same change.

**Shared behaviour lives in mixins, never in copies.** A mixin is a plain
class with methods and no fields, inherited next to `BaseModel`
(`class ProcessData(TimeOriginMixin, HistoryMixin, BaseModel)`). Two exist across
classes: `TimeOriginMixin` (`_time.py`, needs `ds`, `tos`, `_new(ds)`,
`select_tos_range` from its host) and `HistoryMixin` (`history.py`, needs
`ds`). `SpectroscopyData` also uses mixins to split itself by topic (see
*Spectroscopy layout*; the whole design is in `docs/mixins.md`). A host adapts a mixin through its hooks (e.g.
`_tos_start_raw`, `_with_tos_start`), never by overriding or copying the
public methods. When a second class needs a behaviour that one class already
has, move it into a mixin rather than duplicating it.

**Immutable processing API.** Every processing method (smoothing, baseline correction, normalization, selection) returns a *new* instance rather than mutating `self`. Use chaining: `ir.normalise_max().smooth_savgol()`.

**Classmethod constructors, not `__init__`.** Data is always loaded via a `from_*` classmethod (e.g. `RamanData.from_renishaw_wdf`, `MSData.from_quadstar_asc`). Each classmethod calls the corresponding parser, then passes the parsed dict into the model. Everything after the data arguments is keyword-only.

**Parser convention.** Parser modules expose one or more functions that return a plain dict with at minimum a `"data"` key (an xarray object or dict of arrays) and a `"meta"` key (a dict of provenance metadata). Parsers do not return model instances and do not interpret (no normalising on read). A parser module never sets the level of its logger; `lab_data_parser.logging.setup_logger` owns that.

**Cached properties for derived quantities.** Expensive conversions (wavelength and energy axes, XRD d-spacing, MS trace indexing) are implemented as `@cached_property` so they are computed once and reused.

**`with_` / `set_` / `del_` mean specific things.** `with_X` applies X *and* recalculates whatever else must change so the physical meaning of the data is preserved (`with_background` recomputes the values; `with_tos_start` rebases `tos` so the absolute timestamps survive). `set_X` force-assigns X and recalculates nothing. `del_X` removes X and leaves the data alone. Keep this trio consistent when adding new state to a class.

**One time origin, four operations, one implementation.** Every class with a `tos_start` (`ProcessData`, `SpectroscopyData`, `MSData`, `GCData`) inherits `lab_data_parser._time.TimeOriginMixin`: the `tos_start` and `timestamps` properties, `with_tos_start` / `set_tos_start` / `del_tos_start` / `move_tos_start_by(delta)` and `select_timestamp_range`. `move_tos_start_by` is defined as `with_tos_start(tos_start + delta)`, so a *later* origin means *smaller* `tos` values. A timezone-naive `tos_start` handed to any of them is read as wall-clock time in the timezone of the current origin (`_to_timestamp(value, reference)`), never as UTC and never by dropping the zone. The origin is stored as a string through `_time.encode_tos_start` / `decode_tos_start` only: ISO 8601 plus the IANA zone in brackets (`2026-04-21T14:42:00+02:00[Europe/Amsterdam]`, RFC 9557), because the offset alone loses daylight saving and a winter run read with a summer origin would show `+02:00` timestamps. Plain ISO strings (older files, fixed offsets) still decode. Without a `tos_start` argument a reader takes the start recorded in the file (`ProcessData`: the first session's start, `MSData`). A host class provides `ds`, `tos`, `_new(ds)` and `select_tos_range`; a host that keeps the origin elsewhere too overrides the hooks `_tos_start_raw` and `_with_tos_start`; better, keep other time-based state in absolute UTC (as `ProcessData` keeps its events and switches) so no hook is needed. Never copy these methods into a class. `XRDData` stores absolute timestamps as a coordinate instead.

**Two ways to cut a time window.** The same four classes expose `select_tos_range(min_s, max_s)` (elapsed seconds) and `select_timestamp_range(start, end)` (absolute wall clock: `pd.Timestamp`, `datetime`, `np.datetime64` or a parseable string). The absolute form converts its bounds against `tos_start` and delegates to the elapsed form, so the two never drift apart; it raises if no `tos_start` is set. A timezone-naive bound is read as wall-clock time *in the origin's timezone*, because the timestamps in the log book are local. A window that contains no sample logs a warning naming the data's range and returns the empty selection (`lab_data_parser._selection.window_mask`), so a pipeline simply has nothing left to do; `empty="raise"` turns that into a `ValueError`. It never silently returns everything. Keep this pair, and the `empty` argument, consistent when adding another time-anchored class.

**Time comes from the instrument, not from the filename.** OMNIC's `... at 0,90 Hours.spa` names are rounded to 0.01 h (36 s) and restart at zero for every new series, so a filename-derived `tos` silently stacks two measurements on top of each other. Both `.spa` readers take the per-scan acquisition timestamp recorded inside the file (`omnic.read_spa_datetime`), and `omnic.resolve_spa_files` orders a directory by that timestamp whenever the file names carry no unique spectrum index. The WDF reader takes `acq_time` and the per-spectrum times of the ORGN block. The same rule applies to any parser: prefer a recorded absolute time over anything reconstructed from a name or an index.

**A library's row order is not your file order.** SpectroChemPy's `read_omnic(*files)` returns the spectra sorted by file name *as text* (`Index 10` before `Index 2`), whatever order the files were given in; `spectrochempy.read_spa` reads the order back from the file-name labels of `nd.y` (`_scp_row_order`) and puts the rows into file order before pairing them with the timestamps. Any bridge that hands several files to a library must check the order it got back; a test with mixed one- and two-digit indices (`test_backend_keeps_file_order_when_text_and_numeric_order_differ`) is the pattern.
Two guards make the mispairing impossible to carry: `SpectroscopyData._build_ds` stores every series sorted by `tos` (only `merge(sort=False)` opts out, because it keeps its blocks on purpose), and the SpectroChemPy backend re-reads the first, middle and last file with the built-in parser and raises if a row is not the spectrum its file holds (`_verify_rows_against_files`). A new reader that takes several spectra from one library call gets the same two guards.

**Instrument exports drift over time.** The same setup gains or renames a column between runs (e.g. the LabVIEW log of b67 box 5 gained `F1 CO PV` in 2026-07; box5-control is still under construction and adds fields). A parser must read old *and* new files, and a directory may hold both: concatenate on the union of the columns and leave NaN where a file did not record a channel. An unrecognised column is skipped with a warning naming it, never a hard failure, and never silently carried through as un-parsed strings. Processing that follows (`ProcessData.resample`, `smooth_moving`) skips NaN samples instead of spreading them.

### Spectral axis conventions

Each module stores its primary axis in SI units; convenience properties expose common alternative units:

- **Spectroscopy**: the `wavenumber` coordinate in m⁻¹, stored once; `axis(unit)` reads it in any unit of `spectroscopy/units.py` (wavenumber, wavelength, frequency, photon energy per photon or per mole, the unit model of the IR-bands atlas) and `from_arrays(axis, values, axis_unit=...)` takes it in any. For Raman the stored value is the shift (Stokes positive), `.shift` / `.shift_per_cm` are its names; wavenumber, frequency and energy units read the shift, wavelength units read the scattered light and need `excitation_wavelength_nm`. A new unit goes into the table in `units.py`, never into a property
- **XPS**: the `binding_energy` coordinate in eV, ascending; `kinetic_energy` is derived from `source_energy_eV` (`E_B = hν - E_K`, no work function term, Thermo's convention) and never stored
- **XRD**: `angle` coordinate in degrees (2θ); `.d_spacing(wavelength)` and `.q_vector(wavelength)` take the wavelength in Å (Cu Kα₁ is 1.5406 Å)
- **TGA**: temperature in K, mass in mg; `.mass_fraction` normalises to `mass_init` and raises without one

### Processing history

Every public method of a core class that returns a new object, and every
`from_*` constructor, is decorated with `lab_data_parser.history.records_step`. It
appends `{"step", "parameters", "time", "version"}` to `ds.attrs["history"]`
of the result, never of the input, and only for the outermost call (a step
calling other recorded steps shows up once). A new processing method gets the
decorator in the same change; a getter does not. A caller that builds its
result from recorded steps but should be recorded as one (e.g.
`GCData.from_ezchrom_rslt_groups`) uses `suppress_recording()` and
`append_history()`. The `history` property and `format_history()` come from
`history.HistoryMixin` (reads `ds.attrs`); a class that keeps attributes
outside `ds` as well defines `_with_history`. The history is plain JSON data;
`to_netcdf` must write it (`encode_attrs` / `decode_attrs`, prefix `json:`),
and a new class with `to_netcdf` gets a round-trip test of it in
`tests/test_history.py`. `SpectroscopyData`, `XPSData`, `GCData`, `MSData`,
`ProcessData` and `TPRData` record; `XRDData`, `TGAData` and `PhysisorptionData` do not yet.

### Pipelines

`lab_data_parser.pipeline.Pipeline` is a list of `Step`s (method name plus
keyword arguments) that applies to any data object: `pipeline(ir)`,
`pipeline.map(regions)`. It is JSON (`to_json` / `from_json`) and it is the
inverse of the history: `Pipeline.from_history(processed)` returns the steps
that made an object, ready to run on the next one. Keep the two consistent:
a step is replayable exactly when its recorded arguments are plain values,
so a method whose argument is an array or a data object (`with_background`)
is recorded as a summary and `from_history` refuses it by name. Store the
pipeline JSON next to the processed data, in the same numbered step folder.

### NetCDF

Every `to_netcdf` writes NetCDF4 through `h5netcdf`, with the engine pinned
(`engine="h5netcdf"`), so the files do not depend on what else is installed.
Nested attributes, booleans, `None` and non-ASCII text are JSON-encoded with
`history.encode_attr` / `decode_attr` (the one codec; no class keeps its own)
so they survive regardless of the backend. A reader loads the file into
memory and closes it (`with xr.open_dataset(...) as handle: handle.load()`),
because a lazy handle keeps the file locked on Windows. Never leave
`scale_factor` as a variable attribute: xarray's CF decoder multiplies the
data by it on reload (`GCData` packs raw counts as int32 with it in the
*encoding* and stores it as `counts_scale_factor` otherwise).

### Spectroscopy layout

IR and Raman are one class, `SpectroscopyData` in `spectroscopy/core.py`,
and there are no subclasses. It owns the axis (always the `wavenumber` dim
in m⁻¹), every processing step, the background and `data_type` conversions,
the Raman names (`shift`, `select_shift_range`, the excitation wavelength and
the scattered-light axes), NetCDF, and the library bridges (`to_spectrochempy`
/ `from_spectrochempy`, `to_ramanspy` / `from_ramanspy`). `ds.attrs["technique"]`
(`'infrared'`, `'raman'` or absent) records what measured the data; it
decides nothing but the default `data_type` (`single_beam`, `intensity`) and
the label of a CSV column. `metadata` is a field for whatever the reader
found in the file, kept JSON-safe so `to_netcdf` stores it.

The class is composed of mixins, one module per topic, so a method is found
by what it does: `_axis.py` (axis in every unit, Raman names, getters),
`_selection.py` (cutting by axis, scan, tos, scan id), `_background.py`
(background and `data_type` conversions), `_baseline.py`, `_signal.py`
(smoothing, averaging, normalisation, Gram-Schmidt, SNR), `_merge.py`,
`_io.py` (NetCDF, CSV, SpectroChemPy, RamanSPy), plus the shared
`TimeOriginMixin` and `HistoryMixin`. `core.py` keeps the fields, the
validators, `_new`, `from_arrays`, `_build_ds`, the operators and `__repr__`;
`_common.py` holds the constants the mixins share (`DataType`,
`BACKGROUND_REFERENCED_TYPES`, the OMNIC label map). A mixin is a plain
class that never imports `SpectroscopyData` (it uses
`_common._is_spectroscopy_data` for type checks and `"SpectroscopyData"`
string annotations); a new method goes into the module of its topic, or a
new module if none fits, never into `core.py`.

`IRData` (`spectroscopy/infrared/readers.py`) and `RamanData`
(`spectroscopy/raman/readers.py`) are *reader namespaces*: plain classes that
cannot be instantiated, whose `from_*` classmethods (`from_omnic_spa`,
`from_renishaw_wdf`, `from_btc655n_export`, `from_arrays`) return a
`SpectroscopyData` with the technique set. The generic constructors
(`from_netcdf`, `from_xarray`, `from_spectrochempy`, `from_ramanspy`) live on
`SpectroscopyData` only, and so do `isinstance` checks. A new file reader
goes into the namespace of its technique and builds its result with
`SpectroscopyData.from_arrays(..., axis_unit=..., technique=...)` or
`SpectroscopyData._build_ds`; a new processing step goes into
`SpectroscopyData`, uses `self._new(ds=...)` to keep the metadata, and
`self._carry_auxiliary` / `self._slice_auxiliary_to` to carry the background
and map coordinates. `merge` rebases only `BACKGROUND_REFERENCED_TYPES` and
refuses maps. There are no compatibility shims: the old import paths
`lab_data_parser.infrared|raman|xps` are gone, `from_scp` is `from_spectrochempy`,
and `IRData(ds=...)` is `SpectroscopyData(ds=...)`. When the API changes,
update the downstream code that uses it instead of keeping an alias here.

`XPSData` (`spectroscopy/xps/core.py`) is its own class: one region of one
sample, `data` over `binding_energy`, optional `transmission`, `background`,
`envelope` and the 2-D `peaks` of a CasaXPS fit, the acquisition parameters
in the attrs. Its readers are classmethods (`from_vamas` returns a dict of
regions or one, `from_avantage_avg`, `from_casaxps_export`) over the parser
modules `xps/vamas.py` (ISO 14976, NORM/REGULAR only, raises
`NotImplementedError` for the rest), `xps/avantage.py` and `xps/casaxps.py`.
Fitted peaks are called **peaks** (`peak_name`, `peak_position_eV`), never
components. The real files of the Thermo instrument live under
`tests/spectroscopy/xps/{vamas,avantage}/`.

### MS block structure

`MSData` wraps an `xr.Dataset` with a shared `cycle` dimension. `block_0` holds m/z channels (`cycle × mz`); additional datablocks hold auxiliary sensors (`cycle × ch_N`). Trace corrections are also logged in `ds.attrs["trace_corrections"]`, next to the general history. `get_trace` smooths (rolling mean) before it normalises, so a normalised trace peaks at 1. `mz` is a property (the m/z grid of block 0); `channels(block_id)` stays a method because it takes the block.

### Background and merging

`SpectroscopyData` keeps the background as a separate 1-D `single_beam` variable (`ds["background"]`), never folded into the data, so `data_type` conversions and background switches are reversible. `merge` (scan axis) leans on exactly that: two measurements are only comparable across a spectrometer restart in raw detector units, so background-dependent segments are converted with `to_single_beam()`, merged, and converted back against the surviving background (`convert_to_single_beam=False` refuses instead; segments already sharing a background skip the round trip). It keeps exactly one background (the pre-experiment one, i.e. the chronologically first segment's), orders segments by absolute timestamp rather than by `tos`, and rebases the later segment's `tos` onto the first's `tos_start`.

### Chromatography layout

`GCData` (`chromatography/core.py`) is the vendor-independent core class, one
subpackage per vendor holds the parsers (`chromatography/agilent/ezchrom.py`).
The contract between them is the list of common *injection records*
(`GCData.from_injections` documents the keys); each vendor module has a
`to_injections()` that produces them, so a new vendor never touches the core.

- The `injection` dim is always present (length 1 for a single measurement); `tos` runs along it.
- Every detector has its own `retention_time_<detector>` dim, even when the axes are identical, so one code path covers instruments that sample detectors differently. That name is the dataset's business: `get_chromatogram` hands out one detector, where there is nothing to distinguish, so every detector comes out as the same object, named `chromatogram` with dims `(injection, retention_time)` and the detector in `attrs["detector"]` (which the dataset variables carry too, so the NetCDF keeps it).
- Different run lengths are padded with NaN. A different sampling interval within one detector is never resampled: `group_injections` splits such records and `from_injections` raises, pointing there.
- The analysis (peak table along `peak`, amounts along `(injection, species)`) is one per object and named in `attrs["analysis_source"]`. An own integration returns a new object; the vendor's stays on the original.
- Which folders a reader was given is resolved by the vendor module, not the core: `ezchrom.find_result_sets` takes one `.rslt` folder, several, or a folder holding them (searched recursively if it holds none directly), and sorts them by name unless `sort=False`. A path that is not a directory, and a searched folder with no result set, raise `FileNotFoundError` rather than reading zero injections.

### Species naming conventions

`lab_data_parser.naming.species` maps the spellings of a species onto one canonical
name. A convention is human-readable JSON; the standard one,
`naming/species/naming_species_standard.json`, uses short canonical names
(`CO2`, `MeOH`, `EtOH`, `PrOH`, ...). Matching ignores case, spaces, hyphens,
underscores and dots and reads subscript digits as digits; a convention where
two species claim one spelling is refused on load. Every function taking a
convention accepts `None` (the standard), a JSON path, an already read dict
(full form, or the flat `{canonical: [aliases]}` form), or a
`SpeciesConvention`. Add a spelling to `naming_species_standard.json` rather than mapping it
in a notebook.

### Process data layout

`ProcessData` (`processdata/core.py`; `LVData` before 2026-10-23, gone without
an alias) is the operational data of a set-up, whatever ran it. One
`xr.Dataset`: dims `tos` and `channel` (the tag: ISA-5.1 for Box 2,
`PI-900`; LabVIEW's names for Box 5, `F1-1-He`); along `channel` the
coordinates `quantity`, `unit`, `kind`, `species`, `device`, `description`
plus every other scalar of the channel's header line (a name colliding with a
variable gets `channel_`); along `tos` x `channel` the fields `pv` (always),
`sp`, `device_pv`, `device_sp`, `target`, `working`, `requested` (floats),
`status`, `owner`, `mode` (int8 codes with CF `flag_values` /
`flag_meanings`, the codes of box2-control's `core/datalog.py`); along `tos`
the coordinate `session` and the variables `state`, `estop`; along `event`
and `switch` the event log and the valve switches, in **absolute UTC** so the
origin operations never touch them (their `tos` is computed when asked for).
Everything else is in `ds.attrs` only: no second `metadata` dict.

Parsers return the record `{"data": {"time" (UTC), "channels", "fields",
"rows"}, "meta", "events", "switches"}` and `build_dataset` turns it into the
Dataset, so a reader for another program never touches the class.
`processdata/labcontrol/daylog.py` reads the lab day-file layout of
box2-control and box5-control (CSV, Zarr, NetCDF, the `.log` event files): it
matches every column to a tag of the `# channel:` lines and a word of
`FIELDS`, skips an unknown field with a warning (`keep_unknown=True` keeps a
numeric one), refuses a `# format:` version above `SUPPORTED_VERSION`, numbers
sessions once across files by their `tos_start`, and computes `tos` from
`time (UTC)`, never from the file's `tos / s`. The layout is the software's
(`docs/data-format.md` in its repository), shared as a written spec and never
as code: lab-data-parser does not import the control software and the control
software does not import lab-data-parser. Its test fixtures under
`tests/processdata/box2` and `box5` were written by the software's own writers.
`processdata/labview/b67box5.py` reads the LabVIEW log (one session per file);
its `CHANNEL_META` writes units in the day-file notation, and
`BOX5_CONTROL_TAGS` maps its names onto box5-control's for `rename_channels`.
LabVIEW v02 logged `F2 Ar` with F1-He's factor (2.3 % low): `scale` corrects
it, nothing does so silently.

### Physisorption isotherm shape

`PhysisorptionData` wraps a *single* isotherm branch, one `xr.DataArray` named `quantity_adsorbed`, dims `("relative_pressure",)`, exactly like a single spectrum or XRD pattern elsewhere in this repo. There is no "branch" concept baked into the type: a reading that produces both adsorption and desorption (e.g. `from_tristar_xls`) returns a `dict[str, PhysisorptionData]` with keys `"adsorption"`/`"desorption"` instead of one dual-branch object. The BET fit (conventionally derived from the adsorption branch) is modelled directly as `.attrs["bet"]`, since every physisorption instrument and analysis method agrees on it. Everything else a parser extracts (t-Plot, BJH, sample log, instrument header) is preserved verbatim under `.attrs["report"]` (JSON-encoded so both survive NetCDF round-trips) rather than given dedicated properties. Parser modules (e.g. `tristar.py`) should still extract as much as the source format offers; the core class only grows new typed accessors when one is actually needed. The report labels change capitalisation between exports ("BET Surface Area" in 2026-07, "BET surface area" earlier), so every lookup goes through `tristar.scalar`, which ignores case; `sample_name`, `sample_mass_g` and `header` are the accessors that exist.

### XRD readers and crystallite size

`XRDData` reads the Bruker D8 Advance-ECO through `from_bruker_xy` (parser
`xrd/bruker.py`, `read_xy`): the DIFFRAC.EVA `.xy` export, one header line
of `Key: "value"` pairs (operator, anode, scan type, time per step) and two
columns 2θ / counts. The header goes into `metadata`; `wavelength_angstrom`
(Kα1 of the anode, `ANODE_WAVELENGTH_ANGSTROM`), `source_file` and `anode`
go into `da.attrs`. `from_e1290` / `read_xy_e1290` read the same file
without its header (kept for older notebooks; "E1290" is a misnomer, the
test fixture is a DIFFRAC.EVA export). ICDD reference cards exported
as tab-separated text are read by `xrd/pdf_card.py` (`read_pdf_card`,
`ReferenceCard`): columns `d_spacing_angstrom, two_theta_deg, intensity, h,
k, l, comment`, card number and phase parsed from the file name;
`two_theta(wavelength)` recomputes the card's 2θ from the d-spacings,
`strongest(n)` picks lines. `xrd/analysis.py` holds the pure functions
`fit_reflection` (its lines are `kernels.pseudo_voigt` and friends) (one line plus linear background,
`scipy.optimize.curve_fit`, returns a `ReflectionFit`) and `scherrer`
(instrumental width subtracted in quadrature); `XRDData.fit_reflection` and
`XRDData.scherrer_size` wrap them, the latter taking the wavelength from
`da.attrs` and falling back to 1.5406 Å. Mind that one reference
folder in the lab holds a `PDF 76-1807_MoO2.txt` that is byte-identical to the anatase
card: it is not an MoO2 card.

### TPR layout

`TPRData` (`tpr/core.py`) wraps an `xr.Dataset` over `time` in s with
`temperature` in °C and the detector signals (`tcd_h2`, `tcd_o2`, `fid`
when present) in mV, with the file's sign: on the in-house rig a reduction
is a *positive* excursion of `tcd_h2`, and `scale(signal, -1)` is the
explicit flip. `tpr/labview_tcd.py` reads the rig's LabVIEW export;
`COLUMN_MAP` maps the two export layouts (with an FID column until
2026-07-13, with `date`/`time` columns from 2026-07-23), the sample weight
tolerates a decimal comma, unknown or unnamed columns are kept with a
warning. Baselines accumulate in `<signal>_baseline`; `per_gram`,
`integrate`, `heating_rate` and the two selections follow the conventions
of the other classes. The TCD is not calibrated for H2, so a consumption is
an area in mV s g^-1.

### Kernels

`kernels.py` (top level, technique-neutral, `ldp.kernels`) holds every simple
peak shape, and nothing that fits. Two families, told apart by the scale
parameter: **height-scaled** `gaussian`, `lorentzian`, `pseudo_voigt`
(`f(x, center, fwhm, height)`, plus `pseudo_voigt_area`), used by the XRD
reflection fit and for mock spectra; **area-scaled** CasaXPS shapes
`gaussian_lorentzian_product` (`GL(m)`), `gaussian_lorentzian_sum` (`SGL(m)`,
the area-scaled pseudo-Voigt, tested equal to it) and `lorentzian_asymmetric`
(`LA(a,b,n)`), with `Lineshape` and `parse_lineshape` for the notation. Every
`fwhm` is the true FWHM, every `area` exact. The Lorentzian fraction of `pseudo_voigt`, `pseudo_voigt_area` and `gaussian_lorentzian_sum` is height-weighted by default (CasaXPS `SGL`); `fraction="area"` reads it as the area share (diffraction literature), `eta_to_area_fraction` / `eta_to_height_fraction` convert, `ReflectionFit.eta_area` reports both. `voigt(x, center, gaussian_fwhm, lorentzian_fwhm, area)` is the real Voigt (scipy `voigt_profile`, area-scaled, two widths), with `voigt_fwhm` (Olivero-Longbothum) and `voigt_to_pseudo_voigt` (Thompson-Cox-Hastings, returns `(fwhm, eta)` in either convention). Two asymmetric distributions, both area-scaled: `exponentially_modified_gaussian(x, center, gaussian_fwhm, tau, area)` (Gaussian convolved with an exponential, the tailing GC peak; `tau < 0` fronts, `tau = 0` is the Gaussian; checked against `scipy.stats.exponnorm`, stable far into both tails) and `log_normal(x, median, sigma_ln, area)` (size distributions; checked against `scipy.stats.lognorm`). `center` of the EMG is the Gaussian centre, not the maximum. The fits live with their
technique (`xps/fitting.py`, `xrd/analysis.py`) and import from here; a new
shape goes here, never into a technique module. Moved here on 2026-10-18 from
`xps/fitting.py` and `xrd/analysis.py`.

### XPS peak fitting

`spectroscopy/xps/fitting.py` does what CasaXPS did by hand; its lineshapes
are the area-scaled kernels of `kernels.py`. Lineshapes:
`GL(m)` (product), `SGL(m)` (sum) and `LA(a,n)` / `LA(a,b,n)` (asymmetric
Lorentzian convolved with a Gaussian; α acts on the high binding energy side,
the Gaussian FWHM is `w · n / gaussian_width_scale` with scale 500, our own
mapping since CasaXPS does not publish one), parsed from the CasaXPS notation
by `parse_lineshape`. The `fwhm` argument is the **true FWHM** of the curve
for every shape, the number CasaXPS prints in its component table (for GL the
shape parameter F is derived from it); checked against CasaXPS exports on
2026-10-18, GL(30) reproduced to 0.3 % of the peak height. CasaXPS's
one-number `LA(50)` is refused: its manual gives no formula and the curves it
draws are no member of our LA family (closest LA(2,400) / LA(1.5,800), 0.5 %
off). It is not a "50 % Gaussian-Lorentzian" blend, as has been claimed.

`PeakSpec` carries bounds and the CasaXPS constraints: `position_offset_from`,
`area_ratio_to` and `fwhm_ratio_to` each take `(other, value)` (fixed) or
`(other, (low, high))` (the offset or ratio is itself fitted inside the
range, CasaXPS's `#` constraint); `fwhm_equal_to` is the ratio 1. A ranged
area ratio with low ≈ 0 caps a minor component below its main line.
`doublet(...)` builds a spin-orbit pair with the nominal values of `DOUBLETS`
(Mo 3d 3.13 eV 2:3, Ti 2p 5.7 eV 1:2, Pd 3d 5.26 eV 2:3); for Ti 2p give the
2p1/2 a width ratio range, it is 1.4 to 1.9 times broader (Coster-Kronig).
`fit_peaks` on arrays (bounded least squares, standard errors from the
Jacobian, propagated through ranged relations); `FitResult.aic` / `.bic`
decide whether an extra component earns its place (`bic` drop > 10).
`XPSData.subtract_background(..., average_eV=)` averages each Shirley end
point over that energy (CasaXPS's "average width"); `XPSData.fit_peaks`
passes it on, subtracts the background in the window, fits, and stores the
result in the layout of a CasaXPS export (`peaks` on top of the background,
`envelope`, coordinates `peak_name`, `peak_position_eV`, `peak_fwhm_eV`,
`peak_area`, `peak_area_fraction`, `peak_lineshape`, `attrs["fit"]` with
chi-square, AIC, BIC); `peak_table()` reads either source. Fitted peaks are
**peaks**, never components.

The CasaXPS export reader (`casaxps.py`) read only the first peak of a
multi-peak table until 2026-10-18 (a row with four or more cells was taken
for alternating key/value pairs). The `Area` CasaXPS prints is in CPS·eV,
while the curves of the export are counts; fractions are unaffected.

### Logging survives SpectroChemPy

SpectroChemPy closes every logging handler when it first reads a `.spa`
file (it calls `logging.shutdown`). `setup_logger` therefore installs a
`ReopeningFileHandler`, which reopens `lab_data_parser.log` in append mode when
that happens; a plain `FileHandler` in write mode stays silent for the rest
of the run (found 2026-10-18, when every DRIFTS log came out empty).

## Open work

Open work (known warts, planned refactorings, history for XRD/TGA/physisorption)
is tracked as GitHub issues in `urakawa-group/lab-data-parser`.
