"""ProcessData.from_day_log: the day files of box2-control and box5-control.

Fixtures: ``box2/data`` and ``box2/logs`` are excerpts of real Box 2 days (one
session running over midnight); ``box2/controller`` was written by
box2-control's own CsvWriter and exported to NetCDF by ``box2 export`` (an MFC
with its mode, the setpoint layers, a calibration); ``box5`` was written by
box5-control's DayLog and EventLog (three sessions, one over midnight, a valve
switch, a failed read with its traceback).
"""
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lab_data_parser import ProcessData
from lab_data_parser.processdata.labcontrol import daylog

HERE = Path(__file__).parent
BOX2 = HERE / "box2"
BOX5 = HERE / "box5"
CONTROLLER = BOX2 / "controller" / "2026-10-23_box2.csv"


def test_box2_days_join_into_one_session():
    data = ProcessData.from_day_log(BOX2 / "data")
    assert data.set_up == "box2"
    assert data.n_samples == 240
    assert data.channels == ["PI-200", "PI-201", "PI-202", "PI-900", "PI-901", "TIC-001"]
    # the session runs over midnight: two files, one session, one origin
    assert len(data.sessions) == 1
    assert data.sessions[0]["files"] == ["2026-10-21_box2.csv", "2026-10-22_box2.csv"]
    assert data.tos_start == pd.Timestamp("2026-10-21 22:56:24.605407", tz="Europe/Amsterdam")
    assert np.all(np.diff(data.tos) > 0)
    assert data.ds["unit"].sel(channel="PI-900").item() == "bar(a)"
    assert data.ds["device_unit"].sel(channel="PI-900").item() == "bar(g)"
    assert bool(data.ds["writable"].sel(channel="TIC-001"))
    assert set(data.fields) == {"pv", "sp", "status"}
    assert set(np.unique(data.ds["estop"].values)) == {0}


def test_box2_events_are_found_in_the_logs_folder_with_their_tracebacks():
    data = ProcessData.from_day_log(BOX2 / "data")
    events = data.events
    assert len(events) == 12
    assert list(events.columns) == ["time", "tos", "level", "source", "text", "detail"]
    assert str(events["time"].dt.tz) == "Europe/Amsterdam"
    assert events["time"].is_monotonic_increasing
    assert ProcessData.from_day_log(BOX2 / "data", events=False).events.empty


def test_failed_reading_is_nan_with_its_status():
    data = ProcessData.from_day_log(BOX2 / "data")
    pv = data.get_channel("PI-202")
    status = data.get_channel("PI-202", "status")
    assert np.isnan(pv[status != 0]).all()
    assert data.ds["status"].attrs["flag_meanings"] == "ok warning error idle"


def test_box2_controller_columns_and_calibration():
    data = ProcessData.from_day_log(CONTROLLER)
    assert set(data.fields) == {"pv", "sp", "target", "working", "requested", "owner", "status", "mode"}
    np.testing.assert_allclose(data.get_channel("FIC-500", "target"), 50.0)
    assert np.isnan(data.get_channel("PI-900", "sp")).all()        # an indicator has no setpoint
    owner = data.get_channel("FIC-500", "owner")
    assert owner[:10].tolist() == [2] * 10 and owner[10:].tolist() == [1] * 10   # ramp, then programme
    assert (data.get_channel("PI-900", "owner") == -1).all()
    mode = data.get_channel("FIC-500", "mode")
    assert mode[12] == 8 and mode[0] == 0                           # fully open once, else bus
    assert np.isnan(data.get_channel("FIC-500")[7]) and data.get_channel("FIC-500", "status")[7] == 2
    assert data.ds["state"].values[:5].tolist() == [1] * 5 and data.ds["state"].values[5] == 2
    assert data.ds["estop"].values[15] == 1
    assert data.calibrations[0]["tag"] == "PI-900" and data.calibrations[0]["offset"] == 0.012
    # the channel line's flags would collide with the field 'mode'
    assert bool(data.ds["channel_mode"].sel(channel="FIC-500"))


def test_box2_netcdf_export_reads_the_same(tmp_path):
    csv = ProcessData.from_day_log(CONTROLLER)
    nc = ProcessData.from_day_log(CONTROLLER.with_suffix(".nc"))
    assert nc.channels == csv.channels
    for field in csv.fields:
        np.testing.assert_array_equal(nc.ds[field].values, csv.ds[field].values)
    np.testing.assert_allclose(nc.tos, csv.tos)
    assert nc.calibrations == csv.calibrations
    assert nc.tos_start == csv.tos_start


def test_box2_zarr_store_reads_the_same(tmp_path):
    pytest.importorskip("zarr")
    import xarray as xr

    with xr.open_dataset(CONTROLLER.with_suffix(".nc"), engine="h5netcdf") as handle:
        ds = handle.load()
    from lab_data_parser.history import decode_attrs

    ds.attrs = decode_attrs(dict(ds.attrs))
    for variable in ds.variables.values():
        variable.encoding = {}
    store = tmp_path / "2026-10-23_box2.zarr"
    ds.to_zarr(store, zarr_format=2)
    zarr = ProcessData.from_day_log(store)
    csv = ProcessData.from_day_log(CONTROLLER)
    np.testing.assert_array_equal(zarr.ds["pv"].values, csv.ds["pv"].values)
    assert zarr.sessions[0]["tos_start"] == csv.sessions[0]["tos_start"]


def test_box5_everything_the_log_holds():
    data = ProcessData.from_day_log(BOX5 / "data")
    assert data.set_up == "box5"
    assert set(data.fields) == {"pv", "sp", "device_pv", "device_sp", "status"}
    assert data.channels_of("flow", species="He") == ["F1-1-He", "F2-1-He"]
    he = "F1-1-He"
    np.testing.assert_allclose(data.get_channel(he, "device_pv"), 20.0)
    np.testing.assert_allclose(data.get_channel(he), 20.0 * 1.123)   # PV is the device's figure times the factor
    assert data.ds["factor"].sel(channel=he).item() == 1.123
    assert data.ds["feed"].sel(channel="F2-5-Ar").item() == 2
    assert [s["session"] for s in data.sessions] == [1, 2, 3]
    assert data.sessions[2]["files"] == ["2026-10-23_box5.csv", "2026-10-24_box5.csv"]
    assert np.unique(data.ds["session"].values, return_counts=True)[1].tolist() == [120, 30, 40]


def test_box5_valve_switch_lines_up_with_the_valve():
    data = ProcessData.from_day_log(BOX5 / "data")
    switches = data.switches
    assert len(switches) == 1
    switch = switches.iloc[0]
    assert switch["kind"] == "observed" and switch["feed_before"] == 1 and switch["feed_after"] == 2
    assert switch["tos"] == 60.0 and pd.isna(switch["sent"])
    assert switch["confirmed"] == switch["time"]
    valve = data.get_channel("Valve")
    assert valve[data.tos < 60].max() == 1 and valve[(data.tos >= 60) & (data.tos < 120)].min() == 2


def test_box5_failed_read_and_its_traceback():
    data = ProcessData.from_day_log(BOX5 / "data")
    at = int(np.flatnonzero(data.tos == 30.0)[0])
    assert np.isnan(data.get_channel("F2-5-Ar")[at])
    assert data.get_channel("F2-5-Ar", "status")[at] == 2
    error = data.events[data.events["level"] == "ERROR"].iloc[0]
    assert error["text"] == "F2-5-Ar read failed" and error["tos"] == 30.0
    assert error["detail"].startswith("Traceback") and "TimeoutError" in error["detail"]


def test_selection_cuts_events_and_switches_too():
    data = ProcessData.from_day_log(BOX5 / "data")
    window = data.select_tos_range(50, 70)
    assert window.n_samples == 21
    assert len(window.switches) == 1 and len(window.events) == 1
    assert len(data.select_tos_range(0, 40).switches) == 0
    second = data.select_session(2)
    assert second.n_samples == 30 and [s["session"] for s in second.sessions] == [2]
    assert second.events["text"].tolist() == ["connected: reading every device, nothing written", "disconnected"]


def test_netcdf_round_trip_keeps_everything(tmp_path):
    data = ProcessData.from_day_log(BOX5 / "data").select_tos_range(0, 200)
    data.to_netcdf(tmp_path / "process.nc")
    back = ProcessData.from_netcdf(tmp_path / "process.nc")
    assert back.channels == data.channels and back.fields == data.fields
    pd.testing.assert_frame_equal(back.events, data.events)
    pd.testing.assert_frame_equal(back.switches, data.switches)
    assert back.sessions == data.sessions
    assert back.tos_start == data.tos_start
    assert [h["step"] for h in back.history] == ["from_day_log", "select_tos_range", "from_netcdf"]


def test_unknown_column_is_skipped_with_a_warning_or_kept(tmp_path, caplog):
    text = CONTROLLER.read_text(encoding="utf-8-sig").splitlines()
    head = next(i for i, line in enumerate(text) if line.startswith("time (UTC)"))
    text[head] += ",PI-900 drift / bar(a)"
    text = [line + ",0.5" if line[:4].isdigit() else line for line in text]
    path = tmp_path / "2026-10-23_box2.csv"
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    data = ProcessData.from_day_log(path)
    assert "drift" not in data.fields
    assert "PI-900 drift / bar(a)" in caplog.text
    kept = ProcessData.from_day_log(path, keep_unknown=True)
    np.testing.assert_allclose(kept.get_channel("PI-900", "drift"), 0.5)


def test_a_newer_format_version_is_refused(tmp_path):
    path = tmp_path / "2026-10-23_box2.csv"
    path.write_text(CONTROLLER.read_text(encoding="utf-8-sig").replace("version 1", "version 2", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="version 2"):
        ProcessData.from_day_log(path)


def test_a_shared_folder_needs_the_set_up(tmp_path):
    for source in [*(BOX2 / "data").glob("*.csv"), *(BOX5 / "data").glob("*.csv")]:
        shutil.copy(source, tmp_path / source.name)
    with pytest.raises(ValueError, match="set_up"):
        ProcessData.from_day_log(tmp_path)
    assert ProcessData.from_day_log(tmp_path, set_up="box5", events=False).set_up == "box5"


def test_explicit_tos_start_is_read_in_the_logs_timezone():
    data = ProcessData.from_day_log(BOX5 / "data", tos_start="2026-10-23 09:01:00")
    assert data.tos_start == pd.Timestamp("2026-10-23 09:01:00", tz="Europe/Amsterdam")
    assert data.switches.iloc[0]["tos"] == 0.0


def test_reader_options_are_keyword_only():
    with pytest.raises(TypeError):
        ProcessData.from_day_log(BOX5 / "data", "box5")


def test_find_day_files_orders_days_and_skips_switch_tables():
    files = daylog.find_day_files(BOX5 / "data")
    assert [f.name for f in files] == ["2026-10-23_box5.csv", "2026-10-24_box5.csv"]
