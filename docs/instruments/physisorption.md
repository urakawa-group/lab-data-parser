# Physisorption (N₂ physisorption, BET): `PhysisorptionData`

`PhysisorptionData` is the container for a single isotherm *branch*: relative pressure versus quantity adsorbed (cm³ g⁻¹ STP), wrapped like a single spectrum. A reading that produces both branches returns two instances. The BET fit is modelled directly alongside the curve it was derived from; everything else an instrument reports (t-Plot, BJH, sample log) is preserved verbatim under `.report`.

- **Constructors**: `from_tristar_xls` (Micromeritics TriStar II 3020 multi-report `.XLS`; returns a dict with `"adsorption"` / `"desorption"`), `from_arrays`, `from_netcdf`
- **Accessors**: `relative_pressure`, `values`, `n_points`, `bet`, `surface_area_bet` (m² g⁻¹), `report`, `header`, `sample_name`, `sample_mass_g`; `get_quantity_adsorbed(target_relative_pressure, method, tolerance)`
- **Export**: `to_netcdf`

```python
branches = ldp.PhysisorptionData.from_tristar_xls(xls_file)
adsorption = branches["adsorption"]
adsorption.surface_area_bet                     # BET surface area in m^2 g^-1
adsorption.report["analyses"]["t_plot"]         # everything else MicroActive reported
```

**TriStar II 3020** (`lab_data_parser.physisorption.tristar.read_export`): parses a MicroActive "print selected reports to Excel" export, where every report is its own block of columns separated by a `"|"` divider, with a generic state machine for `key: value` rows, notes and one data table per block. The report labels change capitalisation between exports ("BET Surface Area" in 2026-07, "BET surface area" earlier), so every lookup goes through `tristar.scalar`, which ignores case.

---

See also: [examples/physisorption.ipynb](../../examples/physisorption.ipynb); the [instruments overview](README.md).
