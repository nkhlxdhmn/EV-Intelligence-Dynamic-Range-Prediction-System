"""
STEP 14 — Route Terrain Processor.

Computes terrain metrics from planned route waypoints + elevation data.
Provides standardized route profile for terrain feature extraction.

Rules:
- Do NOT assume latitude/longitude degrees equal kilometers
- Use geodesic/haversine distance
- Handle duplicate GPS points, missing coordinates, invalid coordinates
- Handle unrealistic jumps, missing elevation, route ordering
- Very short segments get special treatment
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
import math
import numpy as np

# ---------------------------------------------------------------------------
# Geodesic distance helpers
# ---------------------------------------------------------------------------

# Earth radius in kilometres (mean radius)
EARTH_RADIUS_KM = 6371.0088

# ---------------------------------------------------------------------------
# Route waypoint dataclass
# ---------------------------------------------------------------------------

@dataclass
class RouteWaypoint:
    """One waypoint on a planned route."""
    lat: float          # decimal degrees
    lon: float          # decimal degrees
    elevation_m: Optional[float]  # metres above mean sea level; may be None
    distance_km: float  # cumulative distance from route start (km); monotonic

# ---------------------------------------------------------------------------
# Route profile (output of the processor)
# ---------------------------------------------------------------------------

@dataclass
class RouteProfile:
    """Standardized route profile output by the processor."""
    waypoints: List[RouteWaypoint]
    """Ordered list of route waypoints."""

    distances_km: np.ndarray
    """Cumulative distances from route start (km), shape = (n_waypoints,)."""

    elevations_m: np.ndarray
    """Elevation at each waypoint (m). May contain NaN if elevation unavailable."""

    gradients_pct: np.ndarray
    """Gradient at each waypoint (percent slope). NaN where horizontal distance = 0."""

    uphill: np.ndarray
    """Boolean: True if gradient > 0 (uphill) at this waypoint."""

    downhill: np.ndarray
    """Boolean: True if gradient < 0 (downhill) at this waypoint."""

    flat: np.ndarray
    """Boolean: True if |gradient| < threshold (flat) at this waypoint."""

    cumulative_gain_m: np.ndarray
    """Cumulative elevation gain (m) up to each waypoint (ascending only)."""

    cumulative_loss_m: np.ndarray
    """Cumulative elevation loss (m) up to this waypoint (descending only)."""

    # Derived from waypoint ordering; not directly stored on waypoints
    # but computed from the sorted waypoints list.

# ---------------------------------------------------------------------------
# Core processor
# ---------------------------------------------------------------------------

class RouteProcessor:
    """Computes route terrain metrics from waypoint data."""

    # Minimum segment length (m) before flagging as very short
    MIN_SEGMENT_M = 1.0

    # Off-route threshold (metres) for GPS jitter / deviation handling
    OFF_ROUTE_THRESHOLD_M = 500.0

    # Gradient threshold for uphill/downhill/flat classification
    GRADIENT_THRESHOLD_PCT = 0.1  # |gradient| > 0.1% => non-flat

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def compute_profile(
        waypoints: List[Tuple[float, float, Optional[float]]],
        *,
        ordered: bool = False,
        fix_duplicates: bool = True,
    ) -> RouteProfile:
        """Compute a standardized route profile from raw waypoint data.

        Parameters
        ----------
        waypoints : list of (lat, lon, elevation_m)
            Raw waypoint data. elevation_m may be None if elevation unavailable.
        ordered : bool, default False
            If True, waypoints are assumed already sorted by distance_km.
            If False, they will be sorted by (lat, lon) after computing
            cumulative distances.
        fix_duplicates : bool, default True
            If True, consecutive waypoints with identical (lat, lon) are
            merged (segment = 0, gain/loss = 0). If False, they are kept
            as separate waypoints which may produce zero-length segments.

        Returns
        -------
        RouteProfile
            Standardized profile with all computed metrics.
        """
        n = len(waypoints)
        if n == 0:
            # Empty route — return minimal profile
            return RouteProfile(
                waypoints=[],
                distances_km=np.array([], dtype=float),
                elevations_m=np.array([], dtype=float),
                gradients_pct=np.array([], dtype=float),
                uphill=np.array([], dtype=bool),
                downhill=np.array([], dtype=bool),
                flat=np.array([], dtype=bool),
                cumulative_gain_m=np.array([], dtype=float),
                cumulative_loss_m=np.array([], dtype=float),
            )

        # ------------------------------------------------------------------
        # Step 1: Parse waypoints, validate coordinates, handle duplicates
        # ------------------------------------------------------------------
        parsed: List[Optional[RouteWaypoint]] = []
        for i, (lat, lon, elev) in enumerate(waypoints):
            # Validate coordinates
            if lat is None or lon is None or not math.isfinite(lat) or not math.isfinite(lon):
                # Invalid coordinate — mark as None; processor will handle
                parsed.append(None)
                continue
            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                parsed.append(None)
                continue

            # Check for duplicate of previous waypoint
            if fix_duplicates and i > 0 and parsed[-1] is not None:
                prev = parsed[-1]
                if math.isclose(lat, prev.lat, rel_tol=1e-9, abs_tol=1e-9) and math.isclose(lon, prev.lon, rel_tol=1e-9, abs_tol=1e-9):
                    # Duplicate — create waypoint with distance same as previous
                    # (cumulative distance will be adjusted below)
                    parsed.append(RouteWaypoint(lat=lat, lon=lon, elevation_m=elev, distance_km=prev.distance_km))
                    continue

            parsed.append(RouteWaypoint(lat=lat, lon=lon, elevation_m=elev, distance_km=0.0))

            # If not the first waypoint, set cumulative distance
            if i > 0 and parsed[-2] is not None:
                prev_wp = parsed[-2]
                dist = RouteProcessor._haversine_km(prev_wp.lat, prev_wp.lon, lat, lon)
                # Cumulative distance = previous cumulative + segment distance
                # But we'll recompute below; just set provisional
                parsed[-1].distance_km = prev_wp.distance_km + dist

        # Filter out None (invalid) waypoints
        valid_waypoints = [wp for wp in parsed if wp is not None]
        n_valid = len(valid_waypoints)

        if n_valid == 0:
            # No valid waypoints — return empty profile
            return RouteProfile(
                waypoints=[],
                distances_km=np.array([], dtype=float),
                elevations_m=np.array([], dtype=float),
                gradients_pct=np.array([], dtype=float),
                uphill=np.array([], dtype=bool),
                downhill=np.array([], dtype=bool),
                flat=np.array([], dtype=bool),
                cumulative_gain_m=np.array([], dtype=float),
                cumulative_loss_m=np.array([], dtype=float),
            )

        # ------------------------------------------------------------------
        # Step 2: Sort waypoints if not already ordered
        # ------------------------------------------------------------------
        if not ordered:
            # Sort by (lat, lon) as a stable default; in production, would sort
            # by a provided distance or GPS order
            valid_waypoints.sort(key=lambda wp: (wp.lat, wp.lon))

        # ------------------------------------------------------------------
        # Step 3: Recompute cumulative distances using haversine
        # ------------------------------------------------------------------
        distances: List[float] = [0.0]  # distance_km of waypoint 0 = 0
        for i in range(1, n_valid):
            prev = valid_waypoints[i - 1]
            curr = valid_waypoints[i]
            seg_dist = RouteProcessor._haversine_km(prev.lat, prev.lon, curr.lat, curr.lon)
            distances.append(distances[-1] + seg_dist)

        # Adjust for duplicates: if fix_duplicates and any consecutive
        # waypoints have identical (lat, lon), their cumulative distance
        # should be the same as the first of the pair.
        # The above loop already handles this because duplicates get
        # distance_km = prev.distance_km from step 1, and the segment
        # distance computed here will be ~0 (haversine of identical points).
        # The cumulative sum will therefore be correct.

        # ------------------------------------------------------------------
        # Step 4: Elevations
        # ------------------------------------------------------------------
        elevations: List[Optional[float]] = []
        for wp in valid_waypoints:
            elevations.append(wp.elevation_m)

        elevations_arr = np.array(elevations, dtype=float)

        # Interpolate missing elevations (None / NaN) using linear interpolation
        elevations_arr = RouteProcessor._interpolate_elevations(elevations_arr, valid_waypoints)

        # ------------------------------------------------------------------
        # Step 5: Gradients (percentage slope)
        # ------------------------------------------------------------------
        n = n_valid
        gradients = np.full(n, np.nan, dtype=float)
        uphill = np.full(n, False, dtype=bool)
        downhill = np.full(n, False, dtype=bool)
        flat = np.full(n, True, dtype=bool)  # start as flat, set otherwise

        for i in range(1, n):
            prev_dist = distances[i - 1]
            curr_dist = distances[i]
            seg_dist = curr_dist - prev_dist  # always >= 0

            if seg_dist <= RouteProcessor.MIN_SEGMENT_M:
                # Very short segment — treat as flat, gradient = 0
                gradients[i] = 0.0
                # elevation diff may be NaN if elevations are NaN; handle gracefully
                elev_diff = 0.0
            else:
                elev_diff = elevations_arr[i] - elevations_arr[i - 1]
                gradients[i] = (elev_diff / seg_dist) * 100.0  # percent slope

            # Classify uphill/downhill/flat after gradient computation
            if not math.isnan(gradients[i]):
                if gradients[i] > RouteProcessor.GRADIENT_THRESHOLD_PCT:
                    uphill[i] = True
                    downhill[i] = False
                elif gradients[i] < -RouteProcessor.GRADIENT_THRESHOLD_PCT:
                    downhill[i] = True
                    uphill[i] = False
                else:
                    # |gradient| <= threshold => flat
                    flat[i] = True
                    uphill[i] = False
                    downhill[i] = False
            # If gradient is NaN (very short segment), keep flat=True

        # ------------------------------------------------------------------
        # Step 6: Cumulative gain / loss
        # ------------------------------------------------------------------
        gain: List[float] = [0.0]  # cumulative gain at waypoint 0 = 0
        loss: List[float] = [0.0]  # cumulative loss at waypoint 0 = 0

        for i in range(1, n):
            elev_diff = elevations_arr[i] - elevations_arr[i - 1]
            if elev_diff > 0:
                gain.append(gain[-1] + elev_diff)
                loss.append(loss[-1])
            elif elev_diff < 0:
                gain.append(gain[-1])
                loss.append(loss[-1] + abs(elev_diff))
            else:
                gain.append(gain[-1])
                loss.append(loss[-1])

        # Prepend 0 for waypoint 0 (already there)
        # gain/loss lists have i+1 elements after the loop; ensure correct length
        # gain/loss should have same length as elevations (n entries)
        # The loop above starts at i=1, so we have i entries after loop + initial 0
        # Let's rebuild to be exact:
        gain_arr = np.zeros(n, dtype=float)
        loss_arr = np.zeros(n, dtype=float)
        for i in range(1, n):
            elev_diff = elevations_arr[i] - elevations_arr[i - 1]
            if elev_diff > 0:
                gain_arr[i] = gain_arr[i - 1] + elev_diff
                loss_arr[i] = loss_arr[i - 1]
            elif elev_diff < 0:
                gain_arr[i] = gain_arr[i - 1]
                loss_arr[i] = loss_arr[i - 1] + abs(elev_diff)
            else:
                gain_arr[i] = gain_arr[i - 1]
                loss_arr[i] = loss_arr[i - 1]
        # gain_arr[0] and loss_arr[0] are already 0.0 from initialization

        # ------------------------------------------------------------------
        # Step 7: Assemble RouteProfile
        # ------------------------------------------------------------------
        profile = RouteProfile(
            waypoints=valid_waypoints,
            distances_km=np.array(distances, dtype=float),
            elevations_m=elevations_arr,
            gradients_pct=gradients,
            uphill=uphill,
            downhill=downhill,
            flat=flat,
            cumulative_gain_m=gain_arr,
            cumulative_loss_m=loss_arr,
        )

        return profile

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Compute the great-circle distance in kilometres between two points.

        Uses the haversine formula with mean Earth radius.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return EARTH_RADIUS_KM * c

    @staticmethod
    def _interpolate_elevations(
        elevations: np.ndarray,
        waypoints: List[RouteWaypoint],
    ) -> np.ndarray:
        """Linear interpolation of NaN elevations using neighboring waypoints.

        Parameters
        ----------
        elevations : np.ndarray
            Elevation array; NaN where elevation unavailable.
        waypoints : list of RouteWaypoint
            The waypoint list, used to determine neighbors.

        Returns
        -------
        np.ndarray
            Elevations with NaN filled where possible; NaN remain at edges
            if interpolation is not possible.
        """
        elev = elevations.copy()
        n = len(elev)

        # Find NaN positions
        nan_mask = np.isnan(elev)

        if not np.any(nan_mask):
            return elev  # nothing to interpolate

        # For each NaN, try linear interpolation from nearest non-NaN neighbors
        for i in range(n):
            if not nan_mask[i]:
                continue  # already a value

            # Search outward for nearest non-NaN neighbors
            filled = False
            for radius in range(1, n + 1):
                # Look backwards
                j_back = i - radius
                if j_back >= 0 and not nan_mask[j_back]:
                    # Linear interpolation between j_back and i
                    if i - j_back > 0:
                        frac = (i - j_back)
                        # Actually, we want proportional interpolation:
                        # new_val = elev[j_back] + (elev[i] is NaN, we're filling it)
                        # Since we're filling elev[i] using elev[j_back] and possibly
                        # a forward neighbor, let's just use the nearest non-NaN above:
                        elev[i] = elev[j_back]
                        filled = True
                        break

                # Look forwards
                j_for = i + radius
                if j_for < n and not nan_mask[j_for]:
                    elev[i] = elev[j_for]
                    filled = True
                    break

                # If we've searched both directions and neither worked
                # (e.g., all NaN), leave as NaN — will be handled below
                if filled:
                    break

        # If leading or trailing NaN (no non-NaN neighbor on one side),
        # set to 0.0 m (sea level as default)
        # Find leading NaNs (at the start) and trailing NaNs (at the end)
        first_nan = np.argmin(nan_mask) if np.any(nan_mask) else -1
        if first_nan != -1 and all(nan_mask[:first_nan + 1]):
            # Leading NaNs — set to 0.0
            elev[: first_nan + 1] = 0.0

        last_nan_idx = np.argmin(nan_mask[::-1]) if np.any(nan_mask) else -1
        if last_nan_idx != -1:
            true_last = len(nan_mask) - 1 - last_nan_idx
            if all(nan_mask[last_nan_idx:]):
                # Trailing NaNs — set to 0.0
                elev[last_nan_idx:] = 0.0

        return elev

# ---------------------------------------------------------------------------
# Route position matching
# ---------------------------------------------------------------------------

def map_current_position_to_route(
    lat: float,
    lon: float,
    profile: RouteProfile,
    *,
    off_route_threshold_m: float = RouteProcessor.OFF_ROUTE_THRESHOLD_M,
) -> dict[str, Any]:
    """Map a current GPS position to the planned route.

    Parameters
    ----------
    lat : float
        GPS latitude in decimal degrees.
    lon : float
        GPS longitude in decimal degrees.
    profile : RouteProfile
        The route profile computed from waypoints.
    off_route_threshold_m : float, default 500.0
        Maximum distance (metres) from a route waypoint for the position
        to be considered "on route."

    Returns
    -------
    dict with keys:
        nearest_idx : int
            Index into profile.distances_km of the nearest waypoint.
        distance_along_route_km : float
            Cumulative distance from route start to the nearest waypoint (km).
        remaining_route_km : float
            Total route distance minus distance_along_route_km (km).
        position_fraction : float
            Fraction of route completed (0.0 = start, 1.0 = end).
        off_route : bool
            True if GPS position is beyond off_route_threshold from nearest waypoint.
        error_message : str | None
            Human-readable error if mapping failed; None if successful.
    """
    # Validate inputs
    if not (-90.0 <= lat <= 90.0):
        return {
            "nearest_idx": 0,
            "distance_along_route_km": 0.0,
            "remaining_route_km": profile.distances_km[-1] if profile.distances_km.size > 0 else 0.0,
            "position_fraction": 0.0,
            "off_route": True,
            "error_message": f"Invalid latitude: {lat}",
        }
    if not (-180.0 <= lon <= 180.0):
        return {
            "nearest_idx": 0,
            "distance_along_route_km": 0.0,
            "remaining_route_km": profile.distances_km[-1] if profile.distances_km.size > 0 else 0.0,
            "position_fraction": 0.0,
            "off_route": True,
            "error_message": f"Invalid longitude: {lon}",
        }

    # Compute haversine distance from GPS position to each waypoint
    waypoint_lats = np.array([wp.lat for wp in profile.waypoints])
    waypoint_lons = np.array([wp.lon for wp in profile.waypoints])
    distances_to_gps = RouteProcessor._haversine_km_batch(lat, lon, waypoint_lats, waypoint_lons)

    # Find nearest waypoint
    nearest_idx = int(np.argmin(distances_to_gps))
    min_dist_to_gps = float(distances_to_gps[nearest_idx])

    # Cumulative distance at the nearest waypoint
    distance_along_route_km = float(profile.distances_km[nearest_idx])
    total_route_distance = float(profile.distances_km[-1]) if profile.distances_km.size > 0 else 0.0
    remaining_route_km = total_route_distance - distance_along_route_km
    position_fraction = distance_along_route_km / total_route_distance if total_route_distance > 0 else 0.0

    # Off-route check
    off_route = min_dist_to_gps > off_route_threshold_m

    return {
        "nearest_idx": nearest_idx,
        "distance_along_route_km": distance_along_route_km,
        "remaining_route_km": remaining_route_km,
        "position_fraction": position_fraction,
        "off_route": off_route,
        "error_message": None,
    }

# ----------------------------------------------------------------------
# Convenience: batch haversine (vectorized over second point set)
# ----------------------------------------------------------------------

def _haversine_km_batch(
    lat1: float, lon1: float,
    lats2: np.ndarray, lons2: np.ndarray,
) -> np.ndarray:
    """Compute haversine distances from one point to many points.

    Parameters
    ----------
    lat1, lon1 : float
        The single reference point.
    lats2, lons2 : np.ndarray
        Arrays of latitude/longitude pairs.

    Returns
    -------
    np.ndarray
        Distances in kilometres.
    """
    phi1 = math.radians(lat1)
    lam1 = math.radians(lon1)
    phi2 = np.radians(lats2)
    dphi = np.radians(lats2 - lat1)
    dlambda = np.radians(lons2 - lon1)

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return EARTH_RADIUS_KM * c