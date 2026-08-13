"""Coordinates, and the one mistake everybody makes with them.

**PostGIS points are (longitude, latitude). Not (latitude, longitude).**

Everyday speech, phone APIs and Google Maps URLs all say "lat, long". PostGIS, GeoJSON
and the WKT format say the opposite, because they order coordinates as (x, y) and
longitude is the x axis.

Swap them and nothing crashes. Accra is at 5.6 N, 0.2 W; reversed it becomes 0.2 N,
5.6 E — a point in the Gulf of Guinea about 600 km offshore. Every clustering query
still runs, every index still works, and every answer is wrong.

So conversion happens **here and nowhere else**, and it is tested.
"""

from __future__ import annotations

import math
from typing import Final

# Ghana's bounding box, with a small margin. Not a security control — a sanity check.
# A report from Kansas is a bug in the client or a lie, and either way it should not
# silently enter the incident map.
GHANA_MIN_LAT: Final = 4.5
GHANA_MAX_LAT: Final = 11.25
GHANA_MIN_LON: Final = -3.35
GHANA_MAX_LON: Final = 1.25

EARTH_RADIUS_METRES: Final = 6_371_000.0


class CoordinateError(ValueError):
    """Raised for coordinates that are impossible or implausible."""


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise CoordinateError("Latitude and longitude must be finite numbers.")
    if not -90.0 <= latitude <= 90.0:
        raise CoordinateError(f"Latitude {latitude} is outside the range -90 to 90.")
    if not -180.0 <= longitude <= 180.0:
        raise CoordinateError(f"Longitude {longitude} is outside the range -180 to 180.")


def is_within_ghana(latitude: float, longitude: float) -> bool:
    return (
        GHANA_MIN_LAT <= latitude <= GHANA_MAX_LAT
        and GHANA_MIN_LON <= longitude <= GHANA_MAX_LON
    )


def to_wkt_point(latitude: float, longitude: float) -> str:
    """(lat, lon) in -> 'POINT(lon lat)' out.

    The argument order is the human one; the output order is the PostGIS one. Putting
    the swap in a single named function is the whole point of this module.
    """
    validate_coordinates(latitude, longitude)
    return f"POINT({longitude} {latitude})"


def haversine_metres(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in metres.

    PostGIS does this for us in the database. This exists so the clustering rules can
    be property-tested as pure functions with no database at all — which is what makes
    it possible to run thousands of generated cases in seconds.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * math.asin(min(1.0, math.sqrt(a)))
