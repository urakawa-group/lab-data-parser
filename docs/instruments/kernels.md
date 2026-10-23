# Peak shapes: `lab_data_parser.kernels`

Peak shapes are not specific to a technique, so they live in one top-level
module, `lab_data_parser.kernels` (`ldp.kernels`), and every fit imports them
from there: the XRD reflection fit (`xrd/analysis.py`), the XPS peak fit
(`spectroscopy/xps/fitting.py`), and mock spectra in the tests. The module
holds shapes only, nothing that fits; a new shape goes here, never into a
technique module.

Two families, told apart by the scale parameter:

| family | functions | scale parameter | used for |
|---|---|---|---|
| **height-scaled** | `gaussian`, `lorentzian`, `pseudo_voigt` | `f(x, center, fwhm, height)`; `pseudo_voigt_area(fwhm, height, eta)` gives the area of a pseudo-Voigt | the XRD reflection fit, mock spectra |
| **area-scaled** | `gaussian_lorentzian_product` (CasaXPS `GL(m)`), `gaussian_lorentzian_sum` (`SGL(m)`, the area-scaled pseudo-Voigt), `lorentzian_asymmetric` (`LA(a,b,n)`), `voigt`, `exponentially_modified_gaussian`, `log_normal` | `area` | XPS peaks, GC peaks, size distributions |

Every `fwhm` is the true full width at half maximum of the curve, and every
`area` is exact.

## Pseudo-Voigt and the Lorentzian fraction

`pseudo_voigt` and `gaussian_lorentzian_sum` mix a Gaussian and a
Lorentzian of the same FWHM (`pseudo_voigt_area` takes the same fraction). The mixing fraction `eta` is
**height-weighted** by default, as CasaXPS's `SGL` defines it.
`fraction="area"` reads it as the share of the area instead, the convention
of the diffraction literature. `eta_to_area_fraction` and
`eta_to_height_fraction` convert between the two, and
`ReflectionFit.eta_area` reports both for an XRD fit.

```python
from lab_data_parser import kernels

y = kernels.pseudo_voigt(x, center=25.3, fwhm=0.4, height=1000.0, eta=0.5)                  # height-weighted eta
y = kernels.pseudo_voigt(x, center=25.3, fwhm=0.4, height=1000.0, eta=0.5, fraction="area")   # eta as area share
area = kernels.pseudo_voigt_area(fwhm=0.4, height=1000.0, eta=0.5)
y = kernels.gaussian_lorentzian_sum(x, center=284.8, fwhm=1.1, area=area, lorentzian_fraction=0.3)  # SGL(30)
```

## The real Voigt

`voigt(x, center, gaussian_fwhm, lorentzian_fwhm, area)` is the convolution
itself (scipy's `voigt_profile`, area-scaled, two widths). `voigt_fwhm` gives
its FWHM (Olivero-Longbothum), and `voigt_to_pseudo_voigt` the pseudo-Voigt
that approximates it (Thompson-Cox-Hastings), returning `(fwhm, eta)` in
either convention.

## CasaXPS lineshapes

`Lineshape` and `parse_lineshape` read the CasaXPS notation: `GL(30)`,
`SGL(30)`, `LA(1.53,243)`, `LA(1.53,2.1,243)`. For `GL` the shape parameter is
derived from the true FWHM, so the `fwhm` argument is the number CasaXPS
prints in its component table (checked against CasaXPS exports on
2026-10-18: GL(30) reproduced to 0.3 % of the peak height). For `LA(a, b, n)`
the Gaussian FWHM is `w · n / gaussian_width_scale` with scale 500, our own
mapping, since CasaXPS does not publish one. CasaXPS's one-number `LA(50)` is
refused: its manual gives no formula, and the curves it draws are no member of
the LA family. See [XPS](xps.md) for the fit itself.

## Asymmetric distributions

- `exponentially_modified_gaussian(x, center, gaussian_fwhm, tau, area)`: a Gaussian convolved with an exponential, the tailing GC peak. `tau < 0` fronts, `tau = 0` is the Gaussian. `center` is the Gaussian centre, not the maximum. Checked against `scipy.stats.exponnorm` and stable far into both tails.
- `log_normal(x, median, sigma_ln, area)`: size distributions; checked against `scipy.stats.lognorm`.

---

See also: [XRD](xrd.md), [XPS](xps.md); the [instruments overview](README.md).
