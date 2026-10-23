# Gas chromatography: `GCData`

`GCData` is the vendor-independent container for gas chromatography: the chromatograms of a series of injections together with their analysis (integrated peaks and amounts per species).

| what | dims | notes |
|---|---|---|
| one chromatogram variable per detector (`fid`, `tcd`) | `(injection, retention_time_<detector>)` | detector units (`pA`, `25 µV`), retention time in s |
| `peak_*` variables (the peak table) | `(peak,)` | injection, detector, species, retention / start / end time in s, height, area |
| `amount`, `area`, `height` | `(injection, species)` | one entry per species and the detector it was quantified on |

The `injection` dimension is always there, with length 1 for a single measurement, and `tos` runs along it. Every detector has its own retention time axis. Injections that differ in run length are padded with `NaN`; injections whose sampling interval differs are never resampled: `group_injections` splits them and `from_ezchrom_rslt_groups` returns one `GCData` per group. The analysis is whatever produced it, named in `attrs["analysis_source"]`.

- **Constructors**: `from_ezchrom_rslt` (one or more Agilent OpenLab EZChrom `.rslt` folders into one series in time order), `from_ezchrom_rslt_groups`, `from_injections` (the common records every vendor converter produces; `to_injections` gives them back), `from_arrays`, `from_netcdf`
- **Accessors**: `detectors`, `n_injections`, `injection`, `sample_names`, `get_unit`, `get_retention_time`, `tos`, `tos_start`, `timestamps`, `get_chromatogram(detector, injection=None)`, `get_peaks()`, `get_amounts(detector=None, quantity="amount")`, `get_evolution(species, detector=None)`
- **Processing**: `select_by_idx`, `select_tos_range`, `select_timestamp_range`, `select_retention_time_range`, the four time-origin methods, `merge` (along the injection axis), `rename_species`
- **Export**: `to_netcdf` (raw counts are packed as int32 with their scale factor, lossless and half the size), `to_dataframe(detector)`

```python
gc_raw = ldp.GCData.from_ezchrom_rslt(sorted(gc_dir.glob("0*/*.rslt")))
gc = gc_raw.rename_species()                     # Methanol -> MeOH, ...
tcd = gc.get_chromatogram("tcd")                 # (injection, retention time)
co = gc.get_evolution("CO", detector="tcd")      # amount vs injection, with tos
```

**Agilent OpenLab CDS EZChrom** (`lab_data_parser.chromatography.agilent.ezchrom`) reads the vendor files directly, without OpenLab or any Agilent library: `.dat` (an OLE2 / Compound File Binary container; `read_dat` returns both detector traces as raw ADC counts with their scale factor and unit, plus the instrument method XML, setup text, audit trail and summary information), `.acaml` / `.acam_` (ACAML 1.5 XML; `read_acaml` returns every peak, the species amounts and the calibration curves), `.macaml` (`read_method_acaml`), `.rst` and `.cfg` (`read_container_strings`). `read_result_set` reads a whole `.rslt` folder and `to_injections` converts it into the common records (SI units, detectors named from the method: `Front Signal (FID)` becomes `fid`). Verified against the AIA netCDF export of the same 120 traces (largest relative deviation 5.8e-8).

---

See also: [examples/gc.ipynb](../../examples/gc.ipynb); the [instruments overview](README.md).
