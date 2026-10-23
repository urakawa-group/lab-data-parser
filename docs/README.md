# Documentation

The [README](../README.md) says what the package is for and how to start.
These pages hold the detail.

## The ideas

| page | what it covers |
|---|---|
| [Concepts](concepts.md) | how the package is layered, the processing history, `tos_start`, immutability, pipelines, the NetCDF cache, species names |
| [Mixins](mixins.md) | how behaviour is shared between the data classes: the time origin, the history, the topical mixins of `SpectroscopyData`, and how to write a new one |
| [Conventions](conventions.md) | names, method prefixes, units, text and figure style |

## The instruments

[Instruments overview](instruments/README.md): one table of every data class,
its readers and file formats, and a page per instrument:

| page | data class | instruments and software |
|---|---|---|
| [Spectroscopy](instruments/spectroscopy.md) | `SpectroscopyData` (`IRData`, `RamanData` readers) | Thermo OMNIC, Renishaw WiRe, B&W Tek BTC655N |
| [XPS](instruments/xps.md) | `XPSData` | Thermo Avantage, VAMAS, CasaXPS |
| [Process data](instruments/process-data.md) | `ProcessData` | box2-control, box5-control, LabVIEW (Box 5) |
| [Mass spectrometry](instruments/mass-spec.md) | `MSData` | Pfeiffer Quadstar |
| [Gas chromatography](instruments/chromatography.md) | `GCData` | Agilent OpenLab EZChrom |
| [XRD](instruments/xrd.md) | `XRDData` | Bruker D8 Advance-ECO (DIFFRAC.EVA), ICDD cards |
| [TGA](instruments/tga.md) | `TGAData` | Mettler Toledo TGA E2290 |
| [TPR](instruments/tpr.md) | `TPRData` | the in-house LabVIEW TCD rig |
| [Physisorption](instruments/physisorption.md) | `PhysisorptionData` | Micromeritics TriStar II 3020 |
| [Peak shapes](instruments/kernels.md) | `lab_data_parser.kernels` | used by every fit |

## Worked examples

| page | what it shows |
|---|---|
| [DRIFTS in Box 5](examples/drifts-box5.md) | OMNIC spectra, the Quadstar MS and the process data of one operando run on one clock; valve switches for modulation excitation |
| [High pressure in Box 2](examples/high-pressure-box2.md) | the day files of box2-control: pressures, setpoints, events, sessions over midnight, storage |

The notebooks in [`examples/`](../examples/) show every reader on the test
files; see [`examples/README.md`](../examples/README.md).
