"""Where an .sww file's local coordinates are on the ground.

ANUGA stores x and y relative to (xllcorner, yllcorner), in a projected
coordinate system named by the global attributes.  The system is resolved
as anuga_viewer does: the ``epsg`` attribute if there is one (an integer or
"EPSG:nnnn" text), else ``zone`` with ``hemisphere``, else ``zone`` with the
sign of ``false_northing`` (older files).  Only UTM-based systems are
recognised; for anything else the coordinates are still offset, but no
system is named and no latitude and longitude are given.
"""

import math

# The ellipsoids, as (semi-major axis, inverse flattening).
WGS84 = (6378137.0, 298.257223563)
GRS80 = (6378137.0, 298.257222101)
ANS = (6378160.0, 298.25)

# UTM-based EPSG codes: first code, last code, the zone of the first code,
# southern hemisphere, datum name, ellipsoid.
UTM_SYSTEMS = [
    (32601, 32660, 1, False, 'WGS 84', WGS84),
    (32701, 32760, 1, True, 'WGS 84', WGS84),
    (7846, 7859, 46, True, 'GDA2020', GRS80),       # MGA2020
    (28348, 28358, 48, True, 'GDA94', GRS80),       # MGA94
    (20348, 20358, 48, True, 'AGD84', ANS),         # AMG84
    (20248, 20258, 48, True, 'AGD66', ANS),         # AMG66
    (25828, 25838, 28, False, 'ETRS89', GRS80),     # ETRS89 / UTM
]


def utm_system(epsg):
    """(zone, southern, datum, ellipsoid) for a UTM-based EPSG code, or None."""
    for first, last, zone, southern, datum, ellipsoid in UTM_SYSTEMS:
        if first <= epsg <= last:
            return zone + epsg - first, southern, datum, ellipsoid
    return None


def _number(value):
    """An attribute as an int, or None: numbers, numeric text, "EPSG:nnnn"."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, str):
        value = value.strip()
        if value.upper().startswith('EPSG:'):
            value = value[5:]
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class Georeference(object):
    """The offset and projection of an .sww file's coordinates."""

    def __init__(self, attrs):
        self.xllcorner = float(attrs.get('xllcorner', 0.0))
        self.yllcorner = float(attrs.get('yllcorner', 0.0))
        self.epsg = self.zone = self.southern = self.datum = self.ellipsoid = None

        epsg = _number(attrs.get('epsg'))
        system = utm_system(epsg) if epsg else None
        if system:
            self.epsg = epsg
            self.zone, self.southern, self.datum, self.ellipsoid = system
            return
        zone = _number(attrs.get('zone'))
        if zone is None or not 1 <= zone <= 60:
            return
        hemisphere = attrs.get('hemisphere')
        if isinstance(hemisphere, bytes):
            hemisphere = hemisphere.decode()
        if hemisphere in ('southern', 'northern'):
            southern = hemisphere == 'southern'
        else:
            false_northing = _number(attrs.get('false_northing'))
            if false_northing is None:
                return
            southern = false_northing > 0
        # Without an EPSG code the datum is unknown: take WGS 84, as ANUGA does.
        self.zone, self.southern, self.datum, self.ellipsoid = zone, southern, 'WGS 84', WGS84
        self.epsg = (32700 if southern else 32600) + zone

    def projected(self, x, y):
        """Projected coordinates (e.g. UTM easting, northing) of a local point."""
        return x + self.xllcorner, y + self.yllcorner

    def lonlat(self, x, y):
        """Longitude and latitude (degrees, on the file's own datum) of a local
        point, or None when the projection is not known."""
        if self.zone is None:
            return None
        easting, northing = self.projected(x, y)
        return utm_to_lonlat(easting, northing, self.zone, self.southern, self.ellipsoid)

    def system_name(self):
        """e.g. "EPSG:32755, UTM zone 55S", or '' when not known."""
        if self.zone is None:
            return ''
        return 'EPSG:%d, %s UTM zone %d%s' % (self.epsg, self.datum, self.zone,
                                               'S' if self.southern else 'N')

    def describe(self, x, y):
        """Where a local point is, as lines of text: its projected
        coordinates, then when known the system and its latitude and
        longitude."""
        easting, northing = self.projected(x, y)
        if self.zone is None:
            return ['x = %.1f, y = %.1f' % (easting, northing)]
        lon, lat = self.lonlat(x, y)
        return ['E %.1f, N %.1f' % (easting, northing),
                self.system_name(),
                '%.6f°%s, %.6f°%s' % (abs(lat), 'S' if lat < 0 else 'N',
                                      abs(lon), 'W' if lon < 0 else 'E')]


def utm_to_lonlat(easting, northing, zone, southern, ellipsoid=WGS84):
    """Longitude and latitude in degrees of a UTM point.

    Krüger's series to the sixth order in n (Karney 2011), accurate to well
    under a millimetre within a zone."""
    a, inverse_flattening = ellipsoid
    f = 1.0 / inverse_flattening
    n = f / (2.0 - f)
    big_a = a / (1.0 + n) * (1.0 + n ** 2 / 4.0 + n ** 4 / 64.0 + n ** 6 / 256.0)
    beta = [
        n / 2.0 - 2.0 * n ** 2 / 3.0 + 37.0 * n ** 3 / 96.0 - n ** 4 / 360.0
        - 81.0 * n ** 5 / 512.0 + 96199.0 * n ** 6 / 604800.0,
        n ** 2 / 48.0 + n ** 3 / 15.0 - 437.0 * n ** 4 / 1440.0 + 46.0 * n ** 5 / 105.0
        - 1118711.0 * n ** 6 / 3870720.0,
        17.0 * n ** 3 / 480.0 - 37.0 * n ** 4 / 840.0 - 209.0 * n ** 5 / 4480.0
        + 5569.0 * n ** 6 / 90720.0,
        4397.0 * n ** 4 / 161280.0 - 11.0 * n ** 5 / 504.0 - 830251.0 * n ** 6 / 7257600.0,
        4583.0 * n ** 5 / 161280.0 - 108847.0 * n ** 6 / 3991680.0,
        20648693.0 * n ** 6 / 638668800.0,
    ]
    k0 = 0.9996
    xi = (northing - (10000000.0 if southern else 0.0)) / (k0 * big_a)
    eta = (easting - 500000.0) / (k0 * big_a)
    xi1, eta1 = xi, eta
    for j, b in enumerate(beta, 1):
        xi1 -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta1 -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    chi = math.asin(math.sin(xi1) / math.cosh(eta1))
    lon = math.radians(6 * zone - 183) + math.atan2(math.sinh(eta1), math.cos(xi1))

    # Conformal latitude chi to geodetic latitude phi, by Newton's method.
    e = math.sqrt(f * (2.0 - f))
    tau1 = math.tan(chi)
    tau = tau1
    for _ in range(5):
        sigma = math.sinh(e * math.atanh(e * tau / math.sqrt(1.0 + tau ** 2)))
        tau1_of_tau = tau * math.sqrt(1.0 + sigma ** 2) - sigma * math.sqrt(1.0 + tau ** 2)
        derivative = ((1.0 - e ** 2) * math.sqrt(1.0 + tau1_of_tau ** 2) * math.sqrt(1.0 + tau ** 2)
                      / ((1.0 + (1.0 - e ** 2) * tau ** 2)))
        tau -= (tau1_of_tau - tau1) / derivative
    lon = (math.degrees(lon) + 180.0) % 360.0 - 180.0     # zones 1 and 60 cross 180°
    return lon, math.degrees(math.atan(tau))
