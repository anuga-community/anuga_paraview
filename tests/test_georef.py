"""Projected coordinates and latitude and longitude of picked points."""

import pytest

from anuga_paraview.web.georef import GRS80, WGS84, Georeference, utm_system, utm_to_lonlat

# Points checked against pyproj (EPSG code -> geographic CRS), to 1e-9 degrees.
REFERENCE = [
    # epsg, easting, northing, longitude, latitude
    (32755, 333000.0, 8100000.0, 145.42975617135343, -17.178700901558877),
    (32632, 255000.0, 4910000.0, 5.928568383300302, 44.30195531664375),
    (7856, 334000.0, 6252000.0, 151.20551468692597, -33.85926170543747),
    (25832, 740000.0, 4900000.0, 12.004250411064698, 44.21371593862746),
    (32660, 734954.3397465665, 6409539.544631172, -179.04943592693294, 57.76622347325492),
]


@pytest.mark.parametrize('epsg, easting, northing, lon, lat', REFERENCE)
def test_utm_to_lonlat_matches_pyproj(epsg, easting, northing, lon, lat):
    zone, southern, _, ellipsoid = utm_system(epsg)
    got = utm_to_lonlat(easting, northing, zone, southern, ellipsoid)
    assert got == pytest.approx((lon, lat), abs=1e-9)


def test_utm_systems():
    assert utm_system(32755) == (55, True, 'WGS 84', WGS84)
    assert utm_system(32601)[:2] == (1, False)
    assert utm_system(7856) == (56, True, 'GDA2020', GRS80)
    assert utm_system(28356)[:3] == (56, True, 'GDA94')
    assert utm_system(20255)[:3] == (55, True, 'AGD66')
    assert utm_system(25832)[:3] == (32, False, 'ETRS89')
    assert utm_system(4326) is None


def test_the_epsg_attribute_comes_first():
    for epsg in (7856, '7856', 'EPSG:7856', b'EPSG:7856'):
        georef = Georeference({'epsg': epsg, 'zone': -1})
        assert (georef.epsg, georef.zone, georef.southern) == (7856, 56, True)
    assert Georeference({'epsg': 7856}).system_name() == 'EPSG:7856, GDA2020 UTM zone 56S'


def test_zone_and_hemisphere_or_false_northing():
    georef = Georeference({'zone': 32, 'hemisphere': 'northern', 'false_northing': 0})
    assert (georef.epsg, georef.southern) == (32632, False)
    georef = Georeference({'zone': 55, 'false_northing': 10000000})
    assert (georef.epsg, georef.southern) == (32755, True)
    georef = Georeference({'zone': 55, 'false_northing': 0})
    assert (georef.epsg, georef.southern) == (32655, False)


def test_no_projection_still_offsets():
    georef = Georeference({'zone': -1, 'xllcorner': 1000.0, 'yllcorner': 2000.0,
                           'false_northing': 10000000})
    assert georef.zone is None and georef.lonlat(0, 0) is None
    assert georef.projected(1.5, 2.5) == (1001.5, 2002.5)
    assert georef.describe(1.5, 2.5) == ['x = 1001.5, y = 2002.5']


def test_describe_a_point():
    georef = Georeference({'epsg': 32755, 'xllcorner': 333000.0, 'yllcorner': 8100000.0})
    assert georef.describe(0.0, 0.0) == ['E 333000.0, N 8100000.0',
                                         'EPSG:32755, WGS 84 UTM zone 55S',
                                         '17.178701°S, 145.429756°E']
