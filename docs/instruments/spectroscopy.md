# Spectroscopy: one `SpectroscopyData` for infrared and Raman

An IR band and a Raman band of the same vibration sit at the same wavenumber;
the techniques differ in selection rules and in how the signal is recorded,
not in what the axis means. So there is exactly one data class,
`SpectroscopyData` (`lab_data_parser.spectroscopy.core`), and no subclasses.
`ds["data"]` runs over `wavenumber` in m⁻¹ (for Raman, the Raman shift, Stokes
positive) as `(wavenumber,)`, `(scan, wavenumber)` with `tos`, or a map
`(y, x, wavenumber)`, with an optional `background` and `baseline`.
`ds.attrs["technique"]` says what recorded the data (`'infrared'`, `'raman'`
or absent); it decides nothing but the default `data_type` and a CSV label.
The raw metadata of the source file is the separate field `metadata`.

**`IRData` and `RamanData` are the readers, not classes of their own.**
`IRData.from_omnic_spa(...)` and `RamanData.from_renishaw_wdf(...)` both
return a `SpectroscopyData`; neither can be instantiated. Use them to create
data and `SpectroscopyData` for everything else, `isinstance` checks and the
generic constructors (`from_netcdf`, `from_arrays`, `from_xarray`,
`from_spectrochempy`, `from_ramanspy`) included.

```python
ir = ldp.IRData.from_omnic_spa(dir_spa, tos_start=tos_start)       # technique = 'infrared'
raman = ldp.RamanData.from_renishaw_wdf(path_wdf)                    # technique = 'raman'
type(ir) is type(raman) is ldp.SpectroscopyData                      # True
difference = ir.select_by_idx(0) - raman                            # one axis, so they combine
```

**Readers**
- `IRData.from_omnic_spa(path, *, tos_start=..., backend="auto")`: Thermo OMNIC `.spa`, one file or a directory. `backend` is `"auto"` (SpectroChemPy when installed, else the built-in parser), `"spectrochempy"` or `"omnic"`. `data_type` comes from the OMNIC header; an unknown label raises
- `RamanData.from_renishaw_wdf(path)`: Renishaw WiRe `.wdf` (single spectra, series with `tos`, maps); excitation wavelength, acquisition time and the header fields come from the file
- `RamanData.from_renishaw_txt(path, excitation_wavelength_nm)`: WiRe two-column text export
- `RamanData.from_btc655n_export(path)`: B&W Tek BTC655N export; wavelength is converted to the shift with the laser wavelength in the file header
- `IRData.from_arrays(wavenumber_per_cm, values, *, tos, tos_start, data_type)` and `RamanData.from_arrays(shift_per_cm, values, *, excitation_wavelength_nm, data_type, tos, tos_start)`: raw arrays with the technique set; `SpectroscopyData.from_arrays(axis, values, axis_unit=..., technique=...)` is the general form and takes the axis in any spectral unit
- `SpectroscopyData.from_netcdf`, `from_xarray`, `from_spectrochempy`, `from_ramanspy`: the generic constructors, on the data class only

> **One file is just a one-element series.** Reading a single `.spa` gives the same structure as reading a directory: 2-D `(scan, wavenumber)` with one scan and a `tos` coordinate, so `tos_start` applies either way and a one-scan instance is accepted anywhere a single spectrum is expected, e.g. `series.with_background(background_from_one_file)`. Every argument after the path is keyword-only, so `from_omnic_spa(dir, filename)` raises instead of multiplying the axis by a string; join the path yourself.

**The axis in any unit.** The axis is stored once, as a wavenumber in m⁻¹
(the Raman shift for Raman), and read in whatever unit the question is asked
in: `axis("um")`, `axis("eV")`, `axis("kJ mol^-1")`, `axis("THz")`, ...
(`axis_label(unit)` gives the matching `quantity / unit` plot label).
`from_arrays(axis, values, axis_unit="nm")` accepts an axis in any of these
units, and `select_axis_range(2.5, 25, "um")` cuts a window in one. The unit
model is that of the IR-bands atlas: wavenumber (`m^-1`, `cm^-1`, ...),
wavelength (`m`, `um`, `nm`, `A`), frequency (`Hz` to `THz`), photon energy
per photon (`J`, `meV`, `eV`, `keV`, `MeV`) and per mole (`J mol^-1`,
`kJ mol^-1`, `cal mol^-1`, `kcal mol^-1`); common spellings (`cm-1`,
`kJ/mol`, `µm`, `Å`) are understood. For a Raman shift the wavenumber,
frequency and energy units read the shift itself (`raman shift / meV`), the
wavelength units read the scattered light (`1 / (excitation - shift)`), which
is what a spectrometer's wavelength axis shows and needs the excitation
wavelength. The full table is `lab_data_parser.spectroscopy.units`.

**Accessors**
- Axis: `axis(unit)`, `axis_label(unit)`; `wavenumber` (m⁻¹), `wavenumber_per_cm`; Raman names `shift`, `shift_per_cm`; cached shortcuts `wavelength`, `wavelength_nm`, `wavelength_mum`, `frequency`, `energy`, `energy_eV`, `energy_kJ_per_mol`
- Scattered light (needs the excitation wavelength): `excitation_wavelength_nm`, `excitation_wavenumber`, `excitation_wavenumber_per_cm`, `scattered_wavenumber`, `scattered_wavenumber_per_cm`, `scattered_wavelength_nm`, `scattered_frequency`
- Data: `values`, `ndim`, `shape`, `n_spectral`, `data_type`, `values_label`, `da`, `is_map`, `technique`, `metadata`
- Time: `tos`, `tos_start`, `timestamps`
- Background and baseline: `has_background`, `background`, `background_data_type`, `has_baseline`, `baseline`, `data_unbaselined`
- Scans: `get_scan`, `get_scan_by_tos`, `get_scan_by_tos_average`, `get_id_by_tos`, `get_evolution`, `get_map_spectrum`, `get_baseline_scan`, `get_baseline_by_tos`

Every `data_type` records the physical representation:

| `data_type` | Description |
|---|---|
| `single_beam` | raw detector signal |
| `absorbance` | −log₁₀(T); default for OMNIC transmission data |
| `transmittance` | I_sample / I_background |
| `reflectance` | I_sample / I_background (reflection experiment) |
| `log_1_r` | −log₁₀(R); pseudo-absorbance for DRIFTS/ATR |
| `kubelka_munk` | (1−R)² / (2R) |
| `intensity`, `counts`, `counts_per_second`, `arbitrary` | emission and scattering (Raman) |

**Processing (all immutable, all recorded)**
- Selection: `sort`, `select_by_idx`, `select_by_tos`, `select_wavenumber_range`, `select_shift_range`, `select_axis_range` (any unit), `select_wavenumber_index_range`, `select_tos_range`, `select_timestamp_range`, `select_scan_id_range`, `mask_wavenumber_ranges` (NaN inside a window, axis kept), `drop_scans`, `drop_spike_scans` (Hampel test along time, see `find_spike_scans`)
- Time origin: `with_tos_start`, `set_tos_start`, `del_tos_start`, `move_tos_start_by`
- Background: `with_background` (set, or switch and recalculate), `with_background_scan`, `with_background_by_tos`, `set_background` (no recalculation), `del_background`. The background is always stored as `single_beam`
- Conversions: `to_single_beam`, `to_transmittance`, `to_absorbance` (transmission side), `to_reflectance`, `to_log_1_r`, `to_kubelka_munk` (reflection side); `absorbance` to `reflectance` is allowed because OMNIC labels DRIFTS data as absorbance
- Baseline: `correct_offset`, `correct_pchip`, `correct_baseline`, `reapply_baseline`, `correct_drift` (slow drift over the cycles of a modulation experiment), `unbaseline`, `del_baseline`. The subtracted curve accumulates in `ds["baseline"]`, so the pre-correction spectrum is never lost; a stored baseline is dropped, with a warning, when it stops being valid (type conversion, background switch, `+`/`-`)
- Smoothing: `smooth_savgol`, `smooth_gaussian` (sigma in cm⁻¹), `smooth_moving`
- Averaging: `average_scans`, `average_scans_by_tos`
- Normalisation: `normalise_max`, `normalise_integral`, `normalise_reference`, `normalise_reference_scan`, `normalise_reference_by_tos`, `normalise_value_range`, `normalise_value`
- Merging: `merge`, `SpectroscopyData.merge_all` (scan axis, see below)
- Arithmetic: `+`, `-` between compatible objects (the left operand's attributes win)
- Signal quality: `snr_windows`, `snr_noise_window`, `snr_der`, `snr_repeat`, `snr_psd`; Gram-Schmidt: `get_gram_schmidt`, `get_gram_schmidt_scan`, `get_gram_schmidt_by_tos`
- On a map the steps that work spectrum by spectrum apply; those that need a scan axis raise

**Export and bridges**
- `to_netcdf` / `from_netcdf`: round trip of data, background, baseline, coordinates, metadata and history
- `to_csv`: axis-indexed CSV, one column per scan; not for maps
- `to_spectrochempy` / `from_spectrochempy`: SpectroChemPy `NDDataset` (values, wavenumber in cm⁻¹ as `x`, `tos` as `y` with the timestamps as labels, attributes in `nd.meta`, history in `nd.history`)
- `to_ramanspy` / `from_ramanspy`: RamanSPy `Spectrum`, `SpectralContainer` or `SpectralImage`

Both libraries are optional and imported only when called; neither carries the background or the baseline.

## Merging two measurements

When a run has to be interrupted (the spectrometer is restarted mid-experiment and a *second* background is recorded) the experiment ends up split across two files. `merge` joins them back into one along the scan (time) axis. Nomenclature used throughout the repo: **merge** joins along the scan/time axis, **extend** would join along the energy axis (wavenumber), and **vstack** would stack 2-D data along a new dimension.

The merge happens on `single_beam` data, because that is the only representation in which two segments recorded against *different* backgrounds are comparable. Absorbance (or transmittance, log(1/R), ...) segments are converted with `to_single_beam()`, merged, and converted back against the one surviving background, which re-references the second segment to the background that survived. Two segments that already share a background skip the round trip.

| | |
|---|---|
| **data_type** | Preserved. Background-referenced data is rebased through single beam, so the second segment's values are recomputed against the surviving background. The round trip drops any stored baseline, with a warning. `convert_to_single_beam=False` raises instead. A segment without a background is merged as recorded, with a warning; `ds.attrs["merge_log"]` records which of the three happened under `rebasing`. |
| **order** | Segments are ordered by the *absolute* time of their first scan, not by `tos`. The earlier one is the *first* segment. |
| **`tos` / `tos_start`** | The merged data keeps the first segment's `tos_start`; the later segment's `tos` is shifted by the difference between the two origins, so `timestamps` stays continuous across the join. |
| **background** | Exactly one survives, by default the first segment's, i.e. the one recorded *before* the experiment. |
| **baseline** | Kept only if *both* segments carry one, otherwise dropped with a warning. |
| **scan ids** | Renumbered `0 ... n-1`; a JSON record of the operation (gap, overlap, what was kept) is appended to `ds.attrs["merge_log"]`. |

Overrides: `keep_background` (`"first"` / `"last"` / `"none"`, or an explicit array / 1-D `SpectroscopyData`), `order` (`"auto"` / `"given"`), `sort`, `tos_offset_seconds` (relate two time axes explicitly; the way to merge segments without absolute timestamps), `on_overlap` (`"warn"` / `"raise"` / `"ignore"` / `"trim"`), `wavenumber` (`"strict"` or `"interp"` onto the first segment's grid over the common range) and `convert_to_single_beam`. 1-D operands are promoted to a single scan; maps cannot be merged.

**No hand-recorded restart time is needed.** Every `.spa` carries the moment it was recorded, so both segments already sit on the instrument clock. Pass the **same** `tos_start` to both reads (or none at all), and `merge` orders by `tos_start + tos`, i.e. by when the scans actually happened. Never invent a `tos_start` for the second segment by hand: that replaces a measured time with a guess, and is exactly how the two halves end up on top of each other.

```python
tos_start = pd.Timestamp("2026-07-23 10:00:00", tz="Europe/Amsterdam")   # one origin, both reads
part_1 = ldp.IRData.from_omnic_spa(dir_before_restart, tos_start=tos_start)
part_2 = ldp.IRData.from_omnic_spa(dir_after_restart, tos_start=tos_start)

ir_raw = part_1.merge(part_2)
# INFO Joining segments: first ends 2026-07-23 10:23:08+02:00,
#      second starts 2026-07-23 10:43:52+02:00 (gap 1244.0s).

# Any number of files, in any order; the chronology decides:
ir_raw = ldp.SpectroscopyData.merge_all([part_2, part_1, part_3])
```

## Typical DRIFTS workflow

```python
from pathlib import Path
import pandas as pd
import lab_data_parser as ldp

dir_omnic = Path("path/to/omnic")
bg_file = dir_omnic / "Background_2026-04-21.spa"
cache_path = Path("path/to/02_processed/<project>/<run folder>/01_loaded/ir.nc")   # not inside the raw folder
tos_start = pd.Timestamp("2026-04-21 14:42:00", tz="Europe/Amsterdam")

# First run: parse the raw .spa files, assign the background, save.
ir_raw = (
    ldp.IRData.from_omnic_spa(dir_omnic / "02_Reaction", tos_start=tos_start)
    .with_background(ldp.IRData.from_omnic_spa(bg_file, tos_start=tos_start))
)
ir_raw.to_netcdf(cache_path)

# Subsequent runs: fast load.
ir_raw = ldp.SpectroscopyData.from_netcdf(cache_path)

# Processing chain.
ir = (
    ir_raw
    .select_tos_range(0, 6 * 3600)
    .correct_baseline((2600, 2500), [3450, 3100, 2720, 2600, 2500, 2150, 1750, 1230, 800])
    .select_wavenumber_range(1000, 3900)
)

# Inspect the baseline correction itself.
spectrum_uncorrected = ir.unbaseline().get_scan_by_tos(3600)
baseline_curve = ir.get_baseline_by_tos(3600)
# spectrum_uncorrected - baseline_curve == ir.get_scan_by_tos(3600)

spectrum = ir.get_scan_by_tos_average(100 * 60, number_of_scans=10)      # averaged scan at 100 min
evolution = ir.get_evolution(1600)                                       # band intensity over time
ir_temps = ir.average_scans_by_tos(target_tos=[66 * 60, 126 * 60, 186 * 60], time_window=10 * 60,
                                   direction="backward")
snr = ir.snr_windows(signal_range_cm=(1500, 1750), noise_range_cm=(1800, 1900))
```

## The file readers behind the namespaces

`lab_data_parser.spectroscopy.infrared.omnic`:
- `read_spa`: one `.spa` file, a directory or an iterable of paths; returns `x`, `v` (always 2-D, one row per file), `tos` and the header metadata. Supports local paths and HTTP(S) URLs (needs `requests`)
- `read_spa_datetime`: only the acquisition timestamp of a file (a few bytes, cheap enough for thousands of files)
- `resolve_spa_files`: the files a path names, ordered by `Spectrum Index N` or, when the names carry no unique index, by the recorded acquisition time

> **Time comes from inside the file, never from the filename.** OMNIC names its exports `Spectrum Index 412 at 0,90 Hours.spa`, but those hours are rounded to two decimals (0.01 h = **36 s**) and restart at zero every time a new series is started. Both readers take the per-scan acquisition timestamp recorded inside each `.spa`. The filename hours survive only as a last-resort fallback, with a warning.

`lab_data_parser.spectroscopy.infrared.spectrochempy` is the SpectroChemPy-backed alternative, used by default when the library is installed: `read_spa` has the same arguments and returned dict, and `read_nddataset` turns any `NDDataset` into that dict. `read_spa` is a stripped-down version of SpectroChemPy's parser [^1], kept because the library's import time is long; for processing beyond reading, SpectroChemPy itself is worth a look.

`lab_data_parser.spectroscopy.raman.renishaw`: `read_export_wdf` (full binary WDF block reader: `WDF1`, `XLST`, `DATA`, `ORGN`, `WMAP`; returns a `WDFResult` dataclass), `wdf_metadata` (its header as a JSON-safe dict) and `read_export_txt`. The WDF reader is a dependency-free implementation drawing on SpectroChemPy, py-wdf-reader (T. Tian, MIT, DOI:10.5281/zenodo.495477) and gwyddion's renishaw.c.

`lab_data_parser.spectroscopy.raman.btc655n`: `read_export` for the semicolon-delimited `.txt` export (x-keys `Pixel`, `Wavelength`, `Wavenumber`, `Raman Shift`; y-keys `Dark`, `Reference`, `Raw data #1`, `Dark Subtracted #1`, `%TR #1`, `Absorbance #1`, `Irradiance (lumen) #1`).

`lab_data_parser.spectroscopy.infrared.modulation`: modulation excitation (MES) helpers on the folded cycles: `fold_cycles`, `average_cycles` (recorded), `demodulate`, `phase_of_maximum`. The steps that return a new spectrum are methods of `SpectroscopyData` and land in its history: `mask_wavenumber_ranges`, `find_spike_scans` / `drop_spike_scans`, `drop_scans`, `correct_drift`.

---

See also: [examples/infrared_drifts.ipynb](../../examples/infrared_drifts.ipynb), [examples/raman.ipynb](../../examples/raman.ipynb), [examples/drifts_ms_labview.ipynb](../../examples/drifts_ms_labview.ipynb); the [instruments overview](README.md).

[^1]: Travert, A., & Fernandez, C. (2025). *SpectroChemPy* (Version 0.8.4) [Computer software]. Laboratoire Catalyse and Spectrochemistry (LCS), Normandie Université/CNRS. https://github.com/spectrochempy/spectrochempy (CeCILL-B licence)
