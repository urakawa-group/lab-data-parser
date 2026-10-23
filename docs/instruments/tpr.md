# TPR (temperature-programmed reduction): `TPRData`

`TPRData` wraps an `xarray.Dataset` over `time` in s, with `temperature` in °C
and the detector signals (`tcd_h2`, `tcd_o2`, and `fid` where the rig had one)
in mV. The signals keep the sign of the file: on the in-house rig a reduction
is a *positive* excursion of `tcd_h2`, and `scale(signal, -1)` is the explicit
flip when you need the other sign.

- **Constructors**: `from_labview_tcd` (the export of the LabVIEW TPR rig; both column layouts, with an FID column until 2026-07-13 and with `date` / `time` columns from 2026-07-23), `from_arrays`, `from_netcdf`
- **Accessors**: `time`, `temperature`, `signals`, `n_points`, `sample_name`, `sample_weight_mg`, `start_time`, `comment`, `timestamps`, `get_signal`, `integrate(signal, min_s, max_s)`, `heating_rate()`
- **Processing (immutable, recorded)**: `select_time_range`, `select_temperature_range`, `smooth_moving`, `scale`, `per_gram` (divides by the sample weight), `subtract_baseline(signal, "linear" | "constant", time_window_s=... or anchor_points_s=...)`; every subtracted baseline accumulates in `<signal>_baseline`
- **Export**: `to_dataframe`, `to_netcdf`

```python
tpr_raw = ldp.TPRData.from_labview_tcd(txt_file)
tpr = (
    tpr_raw
    .subtract_baseline("tcd_h2", "linear", anchor_points_s=[600, 4200])   # before and after the peak
    .per_gram("tcd_h2")
)
consumption = tpr.integrate("tcd_h2")      # mV s g^-1
```

The TCD is not calibrated for H₂, so a consumption is an area in mV s g⁻¹ and
compares runs on the same rig, not absolute amounts. The parser
(`lab_data_parser.tpr.labview_tcd`, `COLUMN_MAP`) tolerates a decimal comma in the
sample weight and keeps unknown or unnamed columns as further signals with a
warning.

---

See also: [examples/tpr.ipynb](../../examples/tpr.ipynb); the [instruments overview](README.md).
