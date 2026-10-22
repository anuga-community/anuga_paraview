"""Model time as elapsed time, or as the date and time."""

import numpy as np

from anuga_paraview.web.clock import Clock, elapsed

HOURLY = np.arange(0, 48 * 3600 + 1, 3600.0)
# 2024-05-16 00:00 UTC
MAY_16 = 1715817600


def test_short_runs_are_in_seconds():
    clock = Clock(np.linspace(0, 2, 21), {'starttime': 0})
    assert clock.label(5) == '0.5 s'
    values, title = clock.axis()
    assert title == 'Time (s)' and values[5] == 0.5


def test_runs_of_an_hour_or_two_are_charted_in_minutes():
    clock = Clock(np.linspace(0, 5400, 10), {})
    assert clock.label(9) == '1:30:00'
    values, title = clock.axis()
    assert title == 'Time (min)' and values[9] == 90


def test_long_runs_are_in_hours_past_24():
    clock = Clock(HOURLY, {})
    assert clock.label(38) == '38:00:00'
    values, title = clock.axis()
    assert title == 'Time (h)' and values[38] == 38
    assert elapsed(3725.4, 1e5) == '1:02:05'


def test_a_dated_run_shows_the_date_in_its_time_zone():
    clock = Clock(HOURLY, {'starttime': MAY_16, 'timezone': 'Europe/Rome'})
    assert clock.dated
    assert clock.label(38).startswith('2024-05-17 16:00:00 ')    # CEST, UTC+2
    assert clock.label(38).endswith(' (+38:00:00)')
    values, title = clock.axis()
    assert values[38] == '2024-05-17 16:00:00'
    assert title.startswith('Time (')


def test_fixed_offsets_and_utc():
    clock = Clock(HOURLY, {'starttime': MAY_16, 'timezone': '+10:00'})
    assert clock.label(0).startswith('2024-05-16 10:00:00')
    clock = Clock(HOURLY, {'starttime': np.int32(0), 'timezone': b'UTC'})
    assert not clock.dated and clock.label(1) == '1:00:00'
    clock = Clock(HOURLY, {'starttime': MAY_16, 'timezone': 'UTC'})
    assert clock.label(0) == '2024-05-16 00:00:00 UTC (+0:00:00)'


def test_an_unknown_time_zone_falls_back_to_utc():
    clock = Clock(HOURLY, {'starttime': MAY_16, 'timezone': 'Not/A_Zone'})
    assert clock.label(0).startswith('2024-05-16 00:00:00')


def test_chart_axes_go_as_json():
    # The chart is sent to the browser as JSON, which has no dates.
    import json
    for attrs in ({}, {'starttime': MAY_16, 'timezone': 'Europe/Rome'}):
        json.dumps([float(v) if isinstance(v, np.floating) else v
                    for v in Clock(HOURLY, attrs).axis()[0]])
