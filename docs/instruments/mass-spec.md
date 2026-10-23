# Mass spectrometry: `MSData`

`MSData` wraps an `xarray.Dataset` with one `DataArray` per datablock, named `block_{id}`. `block_0` carries the m/z channels with dims `(cycle, mz)`; auxiliary blocks (pressure, temperature, analog inputs) have their own channel dims `(cycle, ch_N)`, so mixed units never share an axis. The `cycle` dim is shared, `tos` rides along it, and `tos_start` sits in `ds.attrs`. Without a `tos_start` argument, `from_quadstar_asc` takes the start recorded in the file.

- **Constructors**: `from_quadstar_asc` (Pfeiffer Quadstar `.asc`, one file or a directory; a naive `tos_start` is read in the file's timezone), `from_arrays`, `from_netcdf`
- **Accessors**: `block_ids`, `n_blocks`, `channels(block_id)`, `mz` (property), `values`, `unit`, `block_type`, `channel_labels`, `cycle`, `n_cycle`, `tos`, `tos_start`, `timestamps`; `get_trace` (one m/z vs cycle, with optional centred `rolling_window` applied *before* `normalize`), `get_traces`, `get_spectrum`, `get_channel`, `tic`
- **Processing**: `select_tos_range`, `select_timestamp_range`, the four time-origin methods, `mask_overloaded` (detector saturation spikes around 1e38 become NaN), `smooth_trace_rolling`, `correct_traces` (shift negative traces up to zero), `baseline_subtract`. Every step is also logged in `ds.attrs["trace_corrections"]`
- **Export**: `to_csv` (one block), `to_netcdf`

```python
ms_raw = ldp.MSData.from_quadstar_asc(asc_file, tos_start=tos_start)
ms = ms_raw.select_tos_range(0, 6 * 3600).correct_traces().mask_overloaded()
trace_44 = ms.get_trace(44, rolling_window=5, normalize=True)
```

**Quadstar** (`lab_data_parser.massspec.quadstar.read_export`): parses the four blank-line-delimited sections of the export (header, cycle and datablock counts, per-datablock channel definitions, data), builds a timezone-aware `Timestamp` column, renames m/z channels to `m{mass}` and keeps a `column_map` so `MSData` can route every column to its block. Threshold columns are dropped by default (`drop_threshold_cols`).

---

See also: [examples/mass_spec.ipynb](../../examples/mass_spec.ipynb), [examples/drifts_ms_labview.ipynb](../../examples/drifts_ms_labview.ipynb); the [instruments overview](README.md).
