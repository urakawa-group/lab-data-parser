# Instruments

Each technique has one core data class, and one parser module per instrument
or software behind it. Parts of this are specific to the group's set-ups (the
LabVIEW and lab-control logs, the TPR rig); the readers of commercial file
formats (OMNIC, Renishaw WiRe, Quadstar, EZChrom, VAMAS, TriStar, Mettler
Toledo, DIFFRAC.EVA) work anywhere.

| technique | data class | reader | instrument or software | file | page |
|---|---|---|---|---|---|
| infrared (DRIFTS, transmission) | `SpectroscopyData` | `IRData.from_omnic_spa` | Thermo OMNIC | `.spa` (file or folder) | [spectroscopy](spectroscopy.md) |
| Raman | `SpectroscopyData` | `RamanData.from_renishaw_wdf`, `from_renishaw_txt` | Renishaw WiRe | `.wdf`, `.txt` | [spectroscopy](spectroscopy.md) |
| Raman | `SpectroscopyData` | `RamanData.from_btc655n_export` | B&W Tek BTC655N | `.txt` | [spectroscopy](spectroscopy.md) |
| XPS | `XPSData` | `from_vamas`, `from_avantage_avg`, `from_casaxps_export` | Thermo Avantage, CasaXPS | `.vms`, `.avg`, `.txt` | [XPS](xps.md) |
| process data | `ProcessData` | `from_day_log` | box2-control (Box 2), box5-control (Box 5) | `<day>_<set-up>.csv`, `.zarr`, `.nc`, `.log` | [process data](process-data.md) |
| process data | `ProcessData` | `from_labview_b67box5` | LabVIEW `box5_drifts_v02.vi` | `.txt` (file or folder) | [process data](process-data.md) |
| mass spectrometry | `MSData` | `from_quadstar_asc` | Pfeiffer Quadstar | `.asc` | [mass spectrometry](mass-spec.md) |
| gas chromatography | `GCData` | `from_ezchrom_rslt`, `from_ezchrom_rslt_groups` | Agilent OpenLab CDS EZChrom | `.rslt` folders | [chromatography](chromatography.md) |
| XRD | `XRDData` | `from_bruker_xy` | Bruker D8 Advance-ECO, DIFFRAC.EVA | `.xy` | [XRD](xrd.md) |
| XRD reference | `ReferenceCard` | `ReferenceCard.from_file` | ICDD PDF cards | `.txt` | [XRD](xrd.md) |
| TGA | `TGAData` | `from_e2290` | Mettler Toledo TGA E2290 | `.txt` | [TGA](tga.md) |
| TPR | `TPRData` | `from_labview_tcd` | in-house LabVIEW TCD rig | `.txt` | [TPR](tpr.md) |
| N₂ physisorption | `PhysisorptionData` | `from_tristar_xls` | Micromeritics TriStar II 3020 | `.XLS` | [physisorption](physisorption.md) |
| peak shapes | none | `lab_data_parser.kernels` | used by every fit | | [peak shapes](kernels.md) |

## What every class shares

| | time origin (`tos_start`, `select_timestamp_range`) | history | NetCDF | `rename_species` |
|---|---|---|---|---|
| `SpectroscopyData` | ✅ | ✅ | ✅ | |
| `XPSData` | | ✅ | ✅ | |
| `ProcessData` | ✅ | ✅ | ✅ | ✅ (`species` coordinate) |
| `MSData` | ✅ | ✅ | ✅ | |
| `GCData` | ✅ | ✅ | ✅ | ✅ (peak table, amounts) |
| `TPRData` | | ✅ | ✅ | |
| `XRDData` | absolute timestamps as a coordinate | | | |
| `TGAData` | | | | |
| `PhysisorptionData` | | | ✅ | |

The shared columns are one implementation each, see [Mixins](../mixins.md).

## Adding an instrument

1. A parser module next to the others of its technique (or a subfolder per vendor, `chromatography/agilent/`), returning a plain `{"data", "meta"}` dict, reading everything the file offers and interpreting nothing.
2. A `from_*` classmethod on the data class, decorated with `records_step`, keyword-only after the data arguments.
3. A small real file under `tests/` and a test that reads it, old and new variants of the format if both exist.
4. A row in the table above and a section on the technique's page.
