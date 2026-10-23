"""The core data containers are reachable from the package root, as the same objects as in their subpackages."""
import lab_data_parser as ldp


def test_core_classes_at_the_top_level():
    assert ldp.GCData is ldp.chromatography.GCData
    assert ldp.IRData is ldp.spectroscopy.infrared.IRData
    assert ldp.ProcessData is ldp.processdata.ProcessData
    assert ldp.MSData is ldp.massspec.MSData
    assert ldp.PhysisorptionData is ldp.physisorption.PhysisorptionData
    assert ldp.RamanData is ldp.spectroscopy.raman.RamanData
    assert ldp.TGAData is ldp.tga.TGAData
    assert ldp.TPRData is ldp.tpr.TPRData
    assert ldp.XRDData is ldp.xrd.XRDData
    assert ldp.XPSData is ldp.spectroscopy.xps.XPSData
    assert ldp.rename_species is ldp.naming.rename_species


def test_from_import():
    from lab_data_parser import GCData, ProcessData, rename_species  # noqa: F401
