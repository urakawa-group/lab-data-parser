from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lab_data_parser import ProcessData
from lab_data_parser.processdata import BOX5_CONTROL_TAGS
from lab_data_parser.processdata.labview.b67box5 import read

OLD_HEADER = (
    "timestamp\tReactor T PV\tAnalytic P PV\tVent P PV\t"
    "F1 He PV\tF1 H2 PV\tF1 CO2 PV\tF2 He PV\tF2 H2 PV\tF2 CO2 PV\tF2 Ar PV\tFeed"
)
# 'F1 CO PV' was added to the export in 2026-07.
NEW_HEADER = (
    "timestamp\tReactor T PV\tAnalytic P PV\tVent P PV\t"
    "F1 He PV\tF1 H2 PV\tF1 CO2 PV\tF1 CO PV\tF2 He PV\tF2 H2 PV\tF2 CO2 PV\tF2 Ar PV\tFeed"
)


def write_log(directory, name, header, n_rows=3, minute=30):
    """Write a synthetic tab-separated LabView log with comma decimals."""
    n_channels = header.count("\t")
    lines = [header]
    for i in range(n_rows):
        values = "\t".join(f"{j + i},500" for j in range(n_channels))
        lines.append(f"23-7-2026 16:{minute}:{i:02d}\t{values}")
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_read_old_format(tmp_path):
    path = write_log(tmp_path, "2026-07-23_16-30-00.txt", OLD_HEADER)
    lv = ProcessData.from_labview_b67box5(path)

    assert "F1 CO2" in lv.channels
    assert "F1 CO" not in lv.channels
    assert lv.n_samples == 3
    assert lv.ds["pv"].dtype == np.float64
    np.testing.assert_allclose(lv.get_channel("Reactor T"), [0.5, 1.5, 2.5])


def test_read_new_format(tmp_path):
    path = write_log(tmp_path, "2026-07-23_16-30-00.txt", NEW_HEADER)
    lv = ProcessData.from_labview_b67box5(path)

    assert "F1 CO" in lv.channels
    channel = lv.ds.sel(channel="F1 CO")
    assert channel["species"].item() == "CO"
    assert channel["feed"].item() == 1
    assert channel["unit"].item() == "mLn/min"
    assert channel["column"].item() == "F1 CO PV"


def test_read_directory_mixing_both_formats(tmp_path):
    write_log(tmp_path, "2026-07-23_16-30-00.txt", OLD_HEADER, minute=30)
    write_log(tmp_path, "2026-07-23_16-40-00.txt", NEW_HEADER, minute=40)

    lv = ProcessData.from_labview_b67box5(tmp_path)

    assert lv.n_samples == 6
    assert "F1 CO" in lv.channels
    # The old file did not record the channel -> NaN (idle) over its rows only.
    assert np.isnan(lv.get_channel("F1 CO")).sum() == 3
    assert (lv.get_channel("F1 CO", "status") == 3).sum() == 3
    assert not np.isnan(lv.get_channel("Reactor T")).any()
    # one session per file, i.e. per LabVIEW start
    assert lv.ds["session"].values.tolist() == [1, 1, 1, 2, 2, 2]
    assert [s["files"] for s in lv.sessions] == [["2026-07-23_16-30-00.txt"], ["2026-07-23_16-40-00.txt"]]


def test_unknown_channel_is_skipped(tmp_path):
    path = write_log(tmp_path, "2026-07-23_16-30-00.txt", NEW_HEADER + "\tF3 Brand New PV")
    lv = ProcessData.from_labview_b67box5(path)

    assert "F3 Brand New" not in lv.channels
    assert "F1 CO" in lv.channels


def test_unknown_channel_can_be_kept(tmp_path):
    path = write_log(tmp_path, "2026-07-23_16-30-00.txt", NEW_HEADER + "\tF3 Brand New PV")
    lv = ProcessData.from_labview_b67box5(path, keep_unknown_channels=True)

    assert "F3 Brand New" in lv.channels
    assert lv.ds["quantity"].sel(channel="F3 Brand New").item() == ""


def test_the_record_holds_utc_times_and_no_time_channel(tmp_path):
    path = write_log(tmp_path, "2026-07-23_16-30-00.txt", NEW_HEADER)
    record = read(path)

    tags = [c["tag"] for c in record["data"]["channels"]]
    assert "timestamp" not in tags and "session" not in tags
    assert record["data"]["time"][0] == np.datetime64("2026-07-23T14:30:00")  # 16:30 CEST
    assert record["data"]["fields"]["pv"].shape == (3, len(tags))


def test_empty_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="No .txt"):
        ProcessData.from_labview_b67box5(tmp_path)


def test_netcdf_roundtrip_of_a_directory_read(tmp_path):
    """A directory read: the sessions of both files survive NetCDF."""
    logs = tmp_path / "logs"
    logs.mkdir()
    write_log(logs, "2026-07-23_16-30-00.txt", OLD_HEADER, minute=30)
    write_log(logs, "2026-07-23_16-40-00.txt", NEW_HEADER, minute=40)
    lv = ProcessData.from_labview_b67box5(logs)
    target = tmp_path / "lv.nc"
    lv.to_netcdf(target)
    back = ProcessData.from_netcdf(target)
    assert back.channels == lv.channels
    np.testing.assert_allclose(back.get_channel(lv.channels[0]), lv.get_channel(lv.channels[0]))
    assert back.sessions == lv.sessions


REAL_EXPORT_DIR = Path(__file__).parent / "b67box5"


def test_real_export_directory():
    """Three consecutive exports of one run (excerpt), read as one directory."""
    lv = ProcessData.from_labview_b67box5(REAL_EXPORT_DIR)
    assert lv.n_samples == 139 + 7 + 120
    assert lv.channels[:3] == ["Reactor T", "Analytic P", "Vent P"]
    assert np.all(np.diff(lv.tos) > 0)
    assert lv.tos_start == pd.Timestamp("2026-03-26 15:15:03", tz="Europe/Amsterdam")
    assert lv.timestamps[-1] == pd.Timestamp("2026-03-26 15:37:15", tz="Europe/Amsterdam")
    np.testing.assert_allclose(lv.get_channel("Reactor T")[:3], 36.111)  # comma decimals
    assert len(lv.sessions) == 3


def test_labview_names_onto_box5_control_tags():
    lv = ProcessData.from_labview_b67box5(REAL_EXPORT_DIR).rename_channels(BOX5_CONTROL_TAGS)
    assert lv.channels == ["Cell T", "BPR Analytic", "BPR Vent", "F1-1-He", "F1-2-H2", "F1-3-CO2",
                           "F2-1-He", "F2-2-H2", "F2-3-CO2", "F2-5-Ar", "Valve"]
    assert lv.ds["former_tag"].sel(channel="Valve").item() == "Feed"
    assert lv.history[-1]["step"] == "rename_channels"


def test_scale_corrects_the_argon_factor_of_labview_v02():
    lv = ProcessData.from_labview_b67box5(REAL_EXPORT_DIR)
    fixed = lv.scale("F2 Ar", 1.149 / 1.123)
    np.testing.assert_allclose(fixed.get_channel("F2 Ar"), lv.get_channel("F2 Ar") * 1.149 / 1.123)
    np.testing.assert_array_equal(fixed.get_channel("F2 He"), lv.get_channel("F2 He"))


def test_reader_options_are_keyword_only():
    with pytest.raises(TypeError):
        ProcessData.from_labview_b67box5(REAL_EXPORT_DIR, None)
