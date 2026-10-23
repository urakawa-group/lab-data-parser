# Examples

One short notebook per technique, plus one that combines three instruments.
Run them from this folder (`uv sync --group dev`, then open them in Jupyter or
VS Code); every path is relative to it.

| notebook | what it shows | data |
|---|---|---|
| [`infrared_drifts.ipynb`](infrared_drifts.ipynb) | OMNIC `.spa` series, axis units, baseline and smoothing, band evolution, NetCDF round trip | `../tests/spectroscopy/infrared/` |
| [`raman.ipynb`](raman.ipynb) | Renishaw `.wdf` and `.txt`, B&W Tek BTC655N, comparing instruments on the Raman shift | `../tests/spectroscopy/raman/` |
| [`mass_spec.ipynb`](mass_spec.ipynb) | Quadstar `.asc`, trace corrections, m/z traces, auxiliary pressure block, wall-clock window | `../tests/massspec/` |
| [`process_data.ipynb`](process_data.ipynb) | `ProcessData`: box2-control and box5-control day logs (setpoint layers, events, valve switches), the LabVIEW log of Box 5 on box5-control's tags | `../tests/processdata/`, `data/drifts_run/labview/` |
| [`gc.ipynb`](gc.ipynb) | Agilent OpenLab EZChrom `.rslt`, chromatograms, peak table, amounts per species | `../tests/chromatography/agilent/` |
| [`xps.ipynb`](xps.ipynb) | VAMAS regions, charge correction, Mo 3d doublet fit, Avantage and CasaXPS readers | `../tests/spectroscopy/xps/` |
| [`xrd.ipynb`](xrd.ipynb) | Bruker `.xy`, ICDD reference cards, reflection fit and Scherrer size | `../tests/xrd/` |
| [`tga.ipynb`](tga.ipynb) | Mettler Toledo E2290, blank subtraction, mass loss and dm/dT | `../tests/tga/e2290/` |
| [`tpr.ipynb`](tpr.ipynb) | LabVIEW TCD rig, baseline, per gram, integral, heating rate | `../tests/tpr/labview_tcd/` |
| [`physisorption.ipynb`](physisorption.ipynb) | TriStar II 3020 export, isotherm branches, BET, the rest of the report | `../tests/physisorption/tristar/` |
| [`drifts_ms_labview.ipynb`](drifts_ms_labview.ipynb) | DRIFTS, MS and LabVIEW process data on one `tos_start`, `select_timestamp_range`, a processing chain as a `Pipeline` | `data/drifts_run/` |

The single-technique notebooks read the test fixtures under `../tests/`, so
they always run against the files the tests check.

## `data/drifts_run/`

An anonymised excerpt of a real operando DRIFTS / MS / LabVIEW run (about
2.5 MB): 40 OMNIC spectra spread evenly over the reaction step, and the
LabVIEW log and the Quadstar MS export cut to the same six-hour window. Sample,
project and user names were removed from the file headers and the instrument
serial number in the `.spa` files was overwritten; the spectra, times and
process values are unchanged.

| folder | content |
|---|---|
| `omnic/` | `.spa` files, OMNIC's own `Spectrum Index N at H Hours` names |
| `labview/` | three LabVIEW `.txt` exports of the run |
| `ms/` | one Quadstar `.asc` export |

## `data/high_pressure_run/`

Two days of box2-control's day files (`data/`) and event files (`logs/`), a
17-hour session in its DEMO mode (simulated devices, the files exactly as the
rig writes them), used by [the Box 2 example](../docs/examples/high-pressure-box2.md).
Every 10th data row is kept, the event log of the first day starts at the
session, and the home-folder paths in its tracebacks were removed.

The notebooks never write next to these files; anything they save goes to a
temporary folder.
