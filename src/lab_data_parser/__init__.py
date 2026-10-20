"""lab_data_parser: read and process the data of the Urakawa group's instruments into one consistent form.

One subpackage per technique, one core data class per technique, and the
core classes reachable from the package root: ``ldp.GCData`` is
``ldp.chromatography.GCData``. See the README for the design.
"""

import lab_data_parser.kernels as kernels
import lab_data_parser.spectroscopy as spectroscopy
import lab_data_parser.xrd as xrd
import lab_data_parser.tga as tga
import lab_data_parser.tpr as tpr
import lab_data_parser.massspec as massspec
import lab_data_parser.physisorption as physisorption
import lab_data_parser.logging as logging
import lab_data_parser.labview as labview
import lab_data_parser.chromatography as chromatography
import lab_data_parser.naming as naming
import lab_data_parser.pipeline as pipeline

# The core data containers, also reachable without their subpackage:
# ldp.GCData is ldp.chromatography.GCData. IRData and RamanData are the reader
# namespaces of SpectroscopyData, the one spectroscopy data class.
from lab_data_parser.chromatography import GCData
from lab_data_parser.spectroscopy import IRData, RamanData, SpectroscopyData, XPSData
from lab_data_parser.labview import LVData
from lab_data_parser.massspec import MSData
from lab_data_parser.physisorption import PhysisorptionData
from lab_data_parser.tga import TGAData
from lab_data_parser.tpr import TPRData
from lab_data_parser.xrd import XRDData
from lab_data_parser.naming import SpeciesConvention, rename_species
from lab_data_parser.pipeline import Pipeline, Step

__all__ = [
    # subpackages
    "kernels", "logging", "spectroscopy", "xrd", "tga", "tpr", "massspec", "physisorption",
    "labview", "chromatography", "naming", "pipeline",
    # core data containers and the spectroscopy readers
    "GCData", "IRData", "LVData", "MSData", "PhysisorptionData", "RamanData", "SpectroscopyData",
    "TGAData", "TPRData", "XPSData", "XRDData",
    # naming and pipelines
    "SpeciesConvention", "rename_species", "Pipeline", "Step",
]
