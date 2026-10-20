"""X-ray photoelectron spectroscopy: :class:`XPSData` and the readers of the Thermo instrument's files.

``vamas`` reads the ISO 14976 ``.vms`` export (the raw counts, what CasaXPS
reads), ``avantage`` the Thermo Avantage ``.avg`` text dump, ``casaxps`` the
tab-separated export of a CasaXPS fit. ``XPSData.from_vamas``,
``from_avantage_avg`` and ``from_casaxps_export`` build the data class from
them. ``fitting`` holds the CasaXPS-style peak fit; its lineshapes are the
kernels of :mod:`lab_data_parser.kernels`.
"""

import lab_data_parser.spectroscopy.xps.avantage as avantage
import lab_data_parser.spectroscopy.xps.casaxps as casaxps
import lab_data_parser.spectroscopy.xps.vamas as vamas
from lab_data_parser.spectroscopy.xps.core import XPSData

__all__ = ["fitting", "PeakSpec", "doublet", "DOUBLETS", "parse_lineshape", "fit_peaks", "XPSData", "avantage", "casaxps", "vamas"]
from lab_data_parser.spectroscopy.xps import fitting
from lab_data_parser.spectroscopy.xps.fitting import PeakSpec, doublet, DOUBLETS, fit_peaks
from lab_data_parser.kernels import parse_lineshape
