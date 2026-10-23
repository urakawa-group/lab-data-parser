"""ProcessData processing: resampling, smoothing (NaN channels and the edges), species and channel names."""
import numpy as np
import pandas as pd
import pytest

from lab_data_parser import ProcessData

TOS_START = pd.Timestamp("2026-04-21 14:00:00", tz="Europe/Amsterdam")


def make_process_data():
    tos = np.arange(8) * 30.0
    frame = pd.DataFrame({
        "timestamp": TOS_START + pd.to_timedelta(tos, unit="s"),
        "Reactor T": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0],
        "F1 CO": [np.nan, np.nan, np.nan, np.nan, 1.0, 1.0, 1.0, 1.0],
    })
    return ProcessData.from_dataframe(frame, tos_start=TOS_START,
                                      channel_meta={"F1 CO": {"quantity": "flow", "species": "Kohlenmonoxid"}})


def test_smooth_moving_keeps_the_edges_and_does_not_spread_nan():
    smoothed = make_process_data().smooth_moving(3)
    temperature = smoothed.get_channel("Reactor T")
    np.testing.assert_allclose(temperature[0], 150.0)   # (100 + 200) / 2, not pulled towards zero
    np.testing.assert_allclose(temperature[-1], 750.0)
    co = smoothed.get_channel("F1 CO")
    assert np.isnan(co[:3]).all()                        # windows with no recorded sample stay NaN
    np.testing.assert_allclose(co[3:], 1.0)              # the NaN gap does not eat the first recorded values


def test_resample_skips_nan_samples():
    resampled = make_process_data().resample(120.0, method="mean")
    np.testing.assert_allclose(resampled.get_channel("Reactor T"), [250.0, 650.0])
    co = resampled.get_channel("F1 CO")
    assert np.isnan(co[0]) and co[1] == 1.0
    np.testing.assert_allclose(resampled.tos, [60.0, 180.0])
    assert make_process_data().resample(120.0, method="last").get_channel("Reactor T").tolist() == [400.0, 800.0]


def test_resample_status_is_the_worst_and_idle_only_when_nothing_was_read():
    resampled = make_process_data().resample(120.0)
    assert resampled.get_channel("F1 CO", "status").tolist() == [3, 0]
    assert resampled.get_channel("Reactor T", "status").tolist() == [0, 0]


def test_rename_species_changes_only_the_species_coordinate():
    data = make_process_data()
    renamed = data.rename_species()
    assert renamed.ds["species"].sel(channel="F1 CO").item() == "CO"
    assert data.ds["species"].sel(channel="F1 CO").item() == "Kohlenmonoxid"
    assert renamed.ds["species"].sel(channel="Reactor T").item() == ""
    assert renamed.ds.attrs["species_convention"] == "standard"
    np.testing.assert_array_equal(renamed.ds["pv"].values, data.ds["pv"].values)


def test_select_quantity_and_channels():
    data = make_process_data()
    assert data.select_quantity("flow").channels == ["F1 CO"]
    assert data.select_channels(["F1 CO", "Reactor T"]).channels == ["F1 CO", "Reactor T"]
    with pytest.raises(KeyError):
        data.select_channels(["nope"])
    with pytest.raises(ValueError, match="pressure"):
        data.select_quantity("pressure")


def test_rename_channels_refuses_duplicates():
    with pytest.raises(ValueError, match="duplicate"):
        make_process_data().rename_channels({"F1 CO": "Reactor T"})


def test_to_dataframe_has_one_column_per_channel():
    frame = make_process_data().to_dataframe(with_timestamps=True)
    assert list(frame.columns) == ["timestamp", "Reactor T", "F1 CO"]
    assert frame.index.name == "tos"
