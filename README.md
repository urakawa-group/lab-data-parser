# Urakawa Group Data Parser

Helper functions to read and process data from the instruments of the Urakawa
group at TU Delft. The package gets experimental data out of raw instrument
files with as little lost as possible and hands it over in one consistent form,
with as much metadata as the files offer. It does not model or plot; that is
left to the analysis code built on top of it.

![Scientific Data Processing Pipeline](docs/static/data-processing.png)

> [!WARNING]
> This repo is under active development and the API still changes.

> [!NOTE]
> The package reads data and produces no scientific result of its own, so AI
> was used heavily to write and curate it. Every reader is checked against
> real files from the lab (the fixtures under `tests/`).

---

## The philosophy

**Read everything, interpret nothing.** A reader keeps what the instrument
wrote: its names, its units, its raw counts next to the scaled values, and
every piece of metadata in the file, also what nobody has asked for yet. It
does not normalise, rename or guess. Instrument exports change over the
years, so an unknown column is skipped with a warning and old and new files
read side by side; nothing fails on a file it can partly read.

**One class per technique, and they all read alike.** Infrared and Raman are
one `SpectroscopyData`; the process data of a set-up is one `ProcessData`,
whether LabVIEW or the new lab-control software recorded it; mass spectra,
chromatograms, XPS regions, diffractograms each have theirs. They share their
verbs: `select_tos_range`, `with_tos_start`, `merge`, `rename_species`,
`to_netcdf` mean the same thing on every class, so once one is known, the
others follow.

**One clock.** Every time-resolved instrument stores elapsed seconds plus one
origin, `tos_start`, with its timezone. Give the spectra, the mass
spectrometer and the process log the same origin, and one value of `tos` is
the same moment in all of them. Times come from what the instrument recorded,
never from a file name.

**Nothing is lost on the way.** No method changes the object it is called
on; each returns a new one, so the raw data is always still there to compare
against. Every step is written into the object's own history, which travels
with it into the NetCDF cache, and a processing chain can be replayed on the
next run as a pipeline. Nothing is ever written next to the raw files.

**Written once.** Behaviour that several classes need, such as the time
origin or the history, is one implementation shared as a *mixin*, so a fix
reaches every class at once and the clocks of two instruments can never drift
apart. [Mixins](docs/mixins.md) explains how.

---

## What it reads

| technique | data class | instruments and software |
|---|---|---|
| [infrared and Raman](docs/instruments/spectroscopy.md) | `SpectroscopyData` | Thermo OMNIC, Renishaw WiRe, B&W Tek BTC655N |
| [XPS](docs/instruments/xps.md) | `XPSData` | Thermo Avantage, VAMAS, CasaXPS |
| [process data](docs/instruments/process-data.md) | `ProcessData` | box2-control (Box 2), box5-control (Box 5), LabVIEW |
| [mass spectrometry](docs/instruments/mass-spec.md) | `MSData` | Pfeiffer Quadstar |
| [gas chromatography](docs/instruments/chromatography.md) | `GCData` | Agilent OpenLab EZChrom |
| [XRD](docs/instruments/xrd.md) | `XRDData` | Bruker D8 Advance-ECO, ICDD cards |
| [TGA](docs/instruments/tga.md) | `TGAData` | Mettler Toledo TGA E2290 |
| [TPR](docs/instruments/tpr.md) | `TPRData` | the in-house LabVIEW TCD rig |
| [N₂ physisorption](docs/instruments/physisorption.md) | `PhysisorptionData` | Micromeritics TriStar II 3020 |

The full table, with readers and file types: [instruments](docs/instruments/README.md).

---

## How to start

You need Python 3.13 or newer. The package lives on GitHub at
[urakawa-group/lab-data-parser](https://github.com/urakawa-group/lab-data-parser);
if the repository is not visible to you, ask for access (see *Contact*).

We recommend [uv](https://docs.astral.sh/uv/) to manage Python and the
dependencies: it installs the right Python by itself, and the lockfile
(`uv.lock`) gives everyone the same versions. Install it once:

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### With git and uv (to follow the development)

```bash
git clone https://github.com/urakawa-group/lab-data-parser.git
cd lab-data-parser
uv sync                   # the package and its runtime dependencies, in .venv
uv sync --group dev       # plus pytest, matplotlib, Jupyter's kernel and the optional backends
uv run pytest             # check that everything works
```

`git pull` followed by `uv sync` brings you to the newest version. To use the
package from another project, add it there as a path dependency:
`uv add --editable ../lab-data-parser`.

### Without git (just download the code)

On the GitHub page, **Code → Download ZIP**, unzip it, and in that folder run
`uv sync` as above. Without uv, a plain virtual environment works too:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows; on macOS and Linux: source .venv/bin/activate
pip install .                     # or pip install ".[all]" for the optional backends
```

The optional extras are `spectrochempy` (the SpectroChemPy backend for OMNIC
files), `ramanspy`, `url` (reading `.spa` files from a web address), `zarr`
(the Zarr day stores of box2-control) and `all`. A downloaded copy does not
update itself: download it again for a newer version.

### In JupyterLab

From the repository folder, start JupyterLab inside the project's environment:

```bash
uv sync --group dev
uv run --with jupyterlab jupyter lab
```

Or, to use an existing JupyterLab (Anaconda, the TU Delft hub), register the
project's environment as a kernel once and pick **lab-data-parser** in
*Kernel → Change kernel*:

```bash
uv run python -m ipykernel install --user --name lab-data-parser
```

In a notebook whose kernel you cannot choose, install the package into that
kernel directly: `%pip install -e path/to/lab-data-parser`.

The worked examples are notebooks in [`examples/`](examples/); open them from
that folder, their paths are relative to it.

### First lines

```python
import pandas as pd
import lab_data_parser as ldp

tos_start = pd.Timestamp("2026-04-21 14:42:00", tz="Europe/Amsterdam")

ir = ldp.IRData.from_omnic_spa("01_raw/box5/run/omnic", tos_start=tos_start)          # a SpectroscopyData
ms = ldp.MSData.from_quadstar_asc("01_raw/box5/run/ms/run.asc", tos_start=tos_start)
process = ldp.ProcessData.from_day_log("01_raw/box5/data", tos_start=tos_start)

ir_window = ir.select_tos_range(0, 6 * 3600).correct_baseline((2600, 2500), [3450, 2720, 1750])
print(ir_window.format_history())        # every step, with its arguments
```

---

## Documentation

| | |
|---|---|
| [Concepts](docs/concepts.md) | how the package is layered, the history, `tos_start`, immutability, pipelines, the NetCDF cache, species names |
| [Mixins](docs/mixins.md) | how behaviour is shared between the classes, in detail |
| [Conventions](docs/conventions.md) | names, method prefixes, units, text and figure style |
| [Instruments](docs/instruments/README.md) | one page per data class: layout, readers, accessors, processing, the file formats |
| [Example: DRIFTS in Box 5](docs/examples/drifts-box5.md) | spectra, MS and process data of one operando run on one clock |
| [Example: high pressure in Box 2](docs/examples/high-pressure-box2.md) | the day files of box2-control: pressures, setpoints, events, storage |
| [Notebooks](examples/README.md) | every reader on real files |

## Development

The contract every contribution follows, with the reasons behind each rule,
is [`CONTRIBUTING.md`](CONTRIBUTING.md), for people and coding assistants alike, and
[Conventions](docs/conventions.md) is its summary. Tests run against real
exports under `tests/`, and a new reader comes with a small real file and a
test that reads it. `uv build` produces the wheel and sdist; the version is in
`pyproject.toml` and is recorded in every history entry. Open work is tracked
as GitHub issues.

## Contact and access

The package is maintained within the [Urakawa Group](https://github.com/urakawa-group)
at TU Delft. For access to the organization or questions about the package,
contact Julius Sommer or Manoj Coppens, or open an issue in this repository.

## License

MIT, see [`LICENSE`](LICENSE).
