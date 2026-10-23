# Conventions

The rules the code follows, so that names, units and figures read the same in
every class. They are the user-facing summary of [`CONTRIBUTING.md`](../CONTRIBUTING.md),
which holds the full contract and the reasons behind each rule.

## Names

- **Full words, no abbreviations**: `relative_pressure`, not `p_rel`; `quantity_adsorbed`, not `q`; `temperature`, not `temp`. The names of techniques stay as they are (`BET`, `BJH`, `XRD`, `IR`, `MS`, `TGA`), because that is what the methods are called.
- **The unit goes into the name** where it is not obvious: `min_s`, `position_eV`, `sample_weight_mg`, `wavelength_angstrom`, `two_theta_deg`.
- **A chemical species is a *species***: in variables, dimensions, columns and docstrings (`species`, `peak_species`, `rename_species`). Never *component*, which in the lab also means a part of a setup, and not *compound* either, which survives only where a vendor format uses it.
- **Fitted XPS lines are *peaks*** (`peak_name`, `peak_position_eV`), never components.
- **Species names are kept as the instrument wrote them** on read. Renaming is an explicit `rename_species()` step (see [Concepts](concepts.md#species-naming-conventions)).

## Method names

| prefix | meaning | example |
|---|---|---|
| `from_*` | constructor, the only way to build an object; everything after the data arguments is keyword-only | `IRData.from_omnic_spa(path, tos_start=...)` |
| `select_*` | cut out a range; returns a new object | `select_tos_range`, `select_angle_range` |
| `with_*` | set something *and* recalculate what has to change so the physics is preserved | `with_background` recomputes the values, `with_tos_start` keeps the timestamps |
| `set_*` | force-assign, recalculate nothing | `set_tos_start`, `set_background` |
| `del_*` | remove, leave the data alone | `del_background`, `del_tos_start` |
| `get_*` | read something out; no new object, not recorded | `get_trace`, `get_chromatogram` |
| `to_*` | export or convert | `to_netcdf`, `to_dataframe`, `to_single_beam` |

Joining two datasets has three names, never mixed up:

- **extend** joins along the energy-related axis (wavenumber, Raman shift, 2θ, m/z), i.e. widens the spectral range.
- **merge** joins along the *other* axis (scan, time, injection), i.e. appends more scans of the same range (`SpectroscopyData.merge`, `GCData.merge`).
- **vstack** stacks already 2-D data along a new, additional dimension.

A `method` argument that is handed to xarray's `.sel` offers exactly `"nearest"`, `"pad"` and `"backfill"`. Linear interpolation is a different operation (`.interp`), never one of those options.

## Behaviour

- **Immutable.** Every processing method returns a new object; the input is untouched.
- **Recorded.** Every `from_*` and every processing method lands in the object's history (classes listed in [Concepts](concepts.md#processing-history-and-logging-every-object-knows-how-it-was-made)).
- **Empty windows warn.** A `select_*_range` that holds no sample logs a warning naming the range of the data and returns an empty object; `empty="raise"` stops instead. It never silently returns everything.
- **Parsers read, they do not interpret.** No normalising, renaming or unit guessing on read. An unknown column is skipped (or kept) with a warning, never a hard failure.
- **Time from the instrument.** `tos` in seconds plus one `tos_start`; times come from what the instrument recorded inside the file, never from a file name. A timezone-naive time is read as wall-clock time in the data's own timezone.
- **Nothing is written next to the raw files.**

## Units and axes

Data is stored in SI units, with convenience properties for the usual lab units.

| class | stored axis | unit |
|---|---|---|
| `SpectroscopyData` | `wavenumber` (for Raman the shift, Stokes positive) | m⁻¹; `axis(unit)` reads any other unit |
| `XPSData` | `binding_energy`, ascending | eV |
| `XRDData` | `angle` (2θ) | degrees |
| `TGAData` | temperature, mass | K, mg |
| `TPRData` | `time`; `temperature` and signals along it | s; °C and mV, as the rig writes them |
| `ProcessData`, `MSData`, `GCData` | `tos` | s; `ProcessData` values in the stored unit of their quantity (`bar(a)`, `degC`, `mLn/min`) |

## Text and figures

These apply to comments, docstrings, printed output and every figure.

- **No em dashes.** Use a comma, colon, full stop or a new sentence. En dashes in numeric ranges are fine (`780–900 cm⁻¹`).
- **Lowercase** axis labels, tick labels and legend entries; capitals only in titles, proper nouns and where grammar asks for them.
- **Axis labels are `quantity / unit`**: `time / s`, `temperature / K`. A dimensionless quantity gets an en dash: `fraction / –`.
- **Units in power notation**, not slashes: `m^2 s^-1`, `mol m^-3 s^-1`, `mV s g^-1`.
- **Chemistry in mhchem** (`$\ce{CO2}$`) wherever math renders (notes, LaTeX). Code and plot labels stay plain text, since matplotlib has no mhchem.
- **Fonts**: Source Sans 3 for all figure and slide text, Source Serif 4 for print maths and body text.

## Code

- NumPy/SciPy-style docstrings on every public class, method, function and property.
- Optional backends (SpectroChemPy, RamanSPy, `requests`) are imported inside the function that needs them, never at module level.
- A new core class is re-exported at the package root in the same change.
- A new reader comes with a small real file under `tests/` and a test that reads it.
