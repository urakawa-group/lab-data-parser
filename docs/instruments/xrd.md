# XRD: `XRDData`

`XRDData` wraps an `xarray.DataArray` with the 2θ angle in degrees throughout. Layouts: `(angle,)` for a single diffractogram and `(scan, angle)` for a series, with optional `tos` and `timestamp` coordinates that every processing step keeps.

- **Constructors**: `from_bruker_xy` (Bruker D8 Advance-ECO, the DIFFRAC.EVA `.xy` export with its header line), `from_e1290` (the same two columns without the header; kept for old notebooks, the name is historical)
- **Accessors**: `angle`, cached `angle_rad`, `theta_deg`, `theta_rad`; `d_spacing(wavelength_angstrom)` and `q_vector(wavelength_angstrom)` via Bragg's law (Cu Kα₁ is 1.5406 Å); `values`, `ndim`, `shape`, `timestamps`, `metadata`
- **Processing**: `sort`, `select_angle_range`, `smooth_savgol`, `smooth_gaussian` (sigma in degrees), `smooth_moving`
- **Analysis**: `fit_reflection(two_theta_deg, window_deg, lineshape)` (one pseudo-Voigt, Gaussian or Lorentzian line from `lab_data_parser.kernels` plus a linear background; returns a `ReflectionFit`), `scherrer_size(two_theta_deg, fwhm_deg, instrumental_fwhm_deg=...)` (crystallite size in nm; the instrumental width is subtracted in quadrature, the wavelength comes from the file's anode and falls back to 1.5406 Å)

```python
xrd = ldp.XRDData.from_bruker_xy(xy_file)                 # anode, operator, time per step in xrd.metadata
fit = xrd.fit_reflection(25.3, window_deg=1.5)           # anatase (101)
size_nm = xrd.scherrer_size(fit.position_deg, fit.fwhm_deg, instrumental_fwhm_deg=0.08)
```

**Reference cards** (`lab_data_parser.xrd.pdf_card`): ICDD PDF cards exported as tab-separated text are read by `ReferenceCard.from_file` (or `read_pdf_card` for the plain dict). The card number and phase come from the file name (`PDF 78-2486_TiO2-Anatase.txt`). `two_theta(wavelength_angstrom)` recomputes the line positions from the d-spacings for another wavelength, `strongest(n)` picks the strongest lines and `select_two_theta_range` cuts a window, which is what you need to mark reference lines in a plot.

**Bruker DIFFRAC.EVA** (`lab_data_parser.xrd.bruker.read_xy`): one header line of `Key: "value"` pairs and two columns 2θ / counts. The anode gives the Kα₁ wavelength (`ANODE_WAVELENGTH_ANGSTROM`), which is stored in the attributes next to `source_file` and `anode`.

---

See also: [examples/xrd.ipynb](../../examples/xrd.ipynb); the [instruments overview](README.md).
