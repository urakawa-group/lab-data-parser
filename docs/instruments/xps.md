# XPS: `XPSData`

`XPSData` holds one region of an X-ray photoelectron measurement (`XPS Survey`, `C1s Scan`, ...): `data` over `binding_energy` in eV, the source energy in the attributes so the kinetic energy the analyser actually scanned is always recoverable (`E_B = hν − E_K`), and whatever else the file carried: the analyser transmission function (VAMAS), a CasaXPS fit (`peaks`, `background`, `envelope`). A file with several regions reads into a `dict` of them, like the two branches of an isotherm. The readers work on the instrument's own files, so a CasaXPS session is not needed to get at the counts.

- **Readers**: `from_vamas(path, region=None)` (ISO 14976 `.vms`, the raw export of Thermo Avantage and what CasaXPS reads; every region or one), `from_avantage_avg(path)` (the Avantage `.avg` text dump of one region; when the file says the transmission function was removed the values are not raw counts and `data_type` is `arbitrary`), `from_casaxps_export(path)` (the tab-separated export of a fit), `from_arrays`, `from_netcdf`
- **Accessors**: `binding_energy`, `kinetic_energy`, `values`, `n_points`, `data_type` (`counts`, `cps`, `arbitrary`), `region`, `sample`, `species_label`, `source_energy_eV`, `dwell_time_s`, `n_scans`, `acquisition_time`, `transmission`, `background`, `peaks` (a table), `envelope`, `integrate(min_eV, max_eV)`
- **Processing (immutable, recorded)**: `select_binding_energy_range`, `sort`, `shift_binding_energy(delta_eV)` and `calibrate_binding_energy(reference_eV, measured_eV)` (charge correction, the cumulative shift stays in the attributes), `to_cps` / `to_counts` (through dwell time and scans), `smooth_savgol`, `normalise_max`, `subtract_background("shirley" | "linear", min_eV, max_eV)` (the subtracted curve is kept as `background`)
- **Export**: `to_netcdf` / `from_netcdf`, `to_dataframe`

```python
regions = ldp.XPSData.from_vamas(path_vms)                 # {"C1s Scan": XPSData, "O1s Scan": ..., "XPS Survey": ...}
c1s = (
    regions["C1s Scan"]
    .to_cps()
    .calibrate_binding_energy(284.8, measured_eV=285.3)   # adventitious carbon
    .subtract_background("shirley", min_eV=282, max_eV=292)
)
area = c1s.integrate(282, 292)
```

The parsers are `lab_data_parser.spectroscopy.xps.vamas.read_vamas` (NORM / REGULAR files; mapping and depth profiles raise `NotImplementedError` rather than reading wrong), `avantage.read_avg` and `casaxps.read_export`.

## Peak fitting without CasaXPS

`XPSData.fit_peaks` does what CasaXPS did by hand and stores the result the
way a CasaXPS export is stored (`peaks` on top of the background, `envelope`,
the peak coordinates and `attrs["fit"]`), so `peak_table()` reads a fit made
here and an imported one alike. The fit lives in
`lab_data_parser.spectroscopy.xps.fitting`, the lineshapes in `lab_data_parser.kernels`:

- **Lineshapes in CasaXPS notation** (`lab_data_parser.kernels`), parsed by `parse_lineshape`: `GL(m)` (Gaussian-Lorentzian product), `SGL(m)` (sum) and `LA(α, β, n)` (asymmetric Lorentzian convolved with a Gaussian; α acts on the high binding energy side). CasaXPS does not publish how `n` maps onto the Gaussian width, so the mapping used here is our own (`gaussian_width_scale`, 500).
- **`PeakSpec`**: start values, bounds and CasaXPS-style constraints to another peak: `position_offset_from`, `area_ratio_to`, `fwhm_ratio_to` (each fixed, or a `(low, high)` range that is fitted, CasaXPS's `#`), `fwhm_equal_to`.
- **`doublet(...)`** builds both spin-orbit lines at once; `DOUBLETS` holds the nominal splittings and area ratios (Mo 3d 3.13 eV 2:3, Ti 2p 5.7 eV 1:2, Pd 3d 5.26 eV 2:3).
- **`fit_peaks`** on plain arrays: bounded least squares, with standard errors from the Jacobian; `FitResult.bic` decides whether an extra component earns its place.

```python
from lab_data_parser.spectroscopy.xps import DOUBLETS, doublet

mo3d = regions["Mo3d Scan"].to_cps().calibrate_binding_energy(284.8, measured_eV=285.3)
peaks = [
    *doublet("Mo(VI) 3d", 232.6, lineshape="LA(1.53,243)", **DOUBLETS["Mo 3d"]),
    *doublet("Mo(V) 3d", 231.3, lineshape="LA(1.53,243)", **DOUBLETS["Mo 3d"]),
]
fitted = mo3d.fit_peaks(peaks, background="shirley", min_eV=226, max_eV=240)
fitted.peak_table()      # position, FWHM, area, area fraction and their errors
```

The Mo(V) / Mo(VI) split of a broad, charged spectrum is not determined by the
data alone. Fix the chemical shift and tie the widths (`position_offset_from`,
`fwhm_equal_to`), or the share wanders with the choice of lineshape.

---

See also: [examples/xps.ipynb](../../examples/xps.ipynb); the [instruments overview](README.md).
