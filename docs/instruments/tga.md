# TGA: `TGAData`

`TGAData` holds parallel `temperature` (K) and `mass` (mg) arrays with an optional `mass_init` and an optional `baseline` kept for provenance after blank subtraction.

- **Constructor**: `from_e2290` (Mettler Toledo TGA E2290 `.txt`; `baseline_path` subtracts a blank on load)
- **Accessors**: `mass_fraction` (raises without `mass_init`), `derivative` (dm/dT), `derivative_fraction`
- **Processing**: `cut_front`, `cut_back`, `correct` (subtract a blank interpolated onto the sample's temperature axis), `smooth` (Savitzky-Golay)

The parser `lab_data_parser.tga.e2290.read_export` splits the file into its five tagged sections (`Curve Name`, `Curve Values`, `Results`, `Sample`, `Method`) and returns the data with the curve name, timestamps, sample name, initial mass and method.

---

See also: [examples/tga.ipynb](../../examples/tga.ipynb); the [instruments overview](README.md).
