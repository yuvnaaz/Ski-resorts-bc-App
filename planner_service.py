import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


LOGGER = logging.getLogger(__name__)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class RidePlanner:
    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.data_dir / "planner_profiles.json"
        self.favorites_file = self.data_dir / "planner_favorites.json"
        self.coords_file = self.data_dir / "resort_coordinates.json"
        self.weather_file = self.data_dir / "weather_cache.json"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BC-Ride-Planner/1.0 (Flask app)"})
        self.coords_cache = self._read_json(self.coords_file, {})
        self.weather_cache = self._read_json(self.weather_file, {})

    def _read_json(self, path: Path, fallback):
        if not path.exists():
            return fallback
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return fallback

    def _write_json(self, path: Path, payload) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    def list_profiles(self) -> List[Dict]:
        return self._read_json(self.profile_file, [])

    def save_profile(self, name: str, preferences: Dict) -> Dict:
        profiles = self.list_profiles()
        filtered = [p for p in profiles if p.get("name") != name]
        payload = {
            "name": name,
            "preferences": preferences,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        filtered.append(payload)
        filtered.sort(key=lambda p: p["name"].lower())
        self._write_json(self.profile_file, filtered)
        return payload

    def list_favorites(self) -> List[Dict]:
        return self._read_json(self.favorites_file, [])

    def save_favorite(self, resort_id: str, note: str = "") -> Dict:
        favorites = self.list_favorites()
        filtered = [f for f in favorites if f.get("resort_id") != resort_id]
        payload = {
            "resort_id": resort_id,
            "note": note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        filtered.append(payload)
        self._write_json(self.favorites_file, filtered)
        return payload

    def _parse_day_pass_cad(self, day_pass: Optional[str]) -> Optional[float]:
        if not day_pass:
            return None
        cad_match = re.search(r"C\$\s*([0-9][0-9.,]*)", day_pass)
        if cad_match:
            return float(cad_match.group(1).replace(",", "."))
        generic = re.search(r"([0-9][0-9.,]*)", day_pass)
        return float(generic.group(1).replace(",", ".")) if generic else None

    def _terrain_mix(self, resort: Dict) -> Tuple[float, float, float]:
        total = resort.get("total_slope_km") or 0
        if total <= 0:
            return (0.34, 0.33, 0.33)
        blue = (resort.get("blue_slope_km") or 0) / total
        red = (resort.get("red_slope_km") or 0) / total
        black = (resort.get("black_slope_km") or 0) / total
        return (blue, red, black)

    def _skill_target(self, skill_level: str) -> Tuple[float, float, float]:
        skill = (skill_level or "intermediate").lower()
        if skill == "beginner":
            return (0.65, 0.30, 0.05)
        if skill == "expert":
            return (0.15, 0.40, 0.45)
        return (0.35, 0.45, 0.20)

    def _terrain_score(self, target_mix: Tuple[float, float, float], resort_mix: Tuple[float, float, float]) -> float:
        diff = abs(target_mix[0] - resort_mix[0]) + abs(target_mix[1] - resort_mix[1]) + abs(target_mix[2] - resort_mix[2])
        return clamp(1 - diff / 2)

    def _estimate_drive(self, user_lat: float, user_lon: float, resort_lat: float, resort_lon: float) -> Tuple[float, float]:
        distance = haversine_km(user_lat, user_lon, resort_lat, resort_lon)
        # Simple BC mountain-road factor
        drive_hours = (distance / 78.0) * 1.23
        return distance, drive_hours

    def _crowd_score(self, crowd_tolerance: str, resort: Dict) -> float:
        lifts = resort.get("lifts_count") or 4
        total = resort.get("total_slope_km") or 20
        capacity_index = clamp((lifts / total) * 3.5)
        tolerance = (crowd_tolerance or "medium").lower()
        if tolerance == "low":
            return capacity_index
        if tolerance == "high":
            return 0.65 + (capacity_index * 0.35)
        return 0.45 + (capacity_index * 0.55)

    def _lookup_coordinates(self, resort: Dict) -> Optional[Tuple[float, float]]:
        resort_id = resort.get("id")
        if resort_id in self.coords_cache:
            row = self.coords_cache[resort_id]
            if row.get("missing"):
                return None
            return float(row["lat"]), float(row["lon"])

        query = f"{resort.get('name', '')} ski resort {resort.get('district') or ''} british columbia canada"
        try:
            response = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "jsonv2", "limit": 1},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            LOGGER.warning("Geocode failed for %s: %s", resort.get("name"), exc)
            self.coords_cache[resort_id] = {"missing": True}
            self._write_json(self.coords_file, self.coords_cache)
            return None

        if not payload:
            self.coords_cache[resort_id] = {"missing": True}
            self._write_json(self.coords_file, self.coords_cache)
            return None
        lat = float(payload[0]["lat"])
        lon = float(payload[0]["lon"])
        self.coords_cache[resort_id] = {"lat": lat, "lon": lon}
        self._write_json(self.coords_file, self.coords_cache)
        return lat, lon

    def _fetch_week_forecast(self, resort_id: str, lat: float, lon: float) -> List[Dict]:
        now = datetime.now(timezone.utc)
        cache_entry = self.weather_cache.get(resort_id)
        if cache_entry:
            cached_at = datetime.fromisoformat(cache_entry["cached_at"])
            if now - cached_at < timedelta(hours=3):
                return cache_entry["windows"]

        try:
            response = self.session.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "temperature_2m,wind_speed_10m,snowfall",
                    "timezone": "auto",
                    "forecast_days": 7,
                },
                timeout=14,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            LOGGER.warning("Forecast fetch failed for %s: %s", resort_id, exc)
            return []

        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        snowfalls = hourly.get("snowfall", [])

        windows: List[Dict] = []
        buckets = {}
        for idx, timestamp in enumerate(times):
            if idx >= len(temps) or idx >= len(winds) or idx >= len(snowfalls):
                continue
            dt = datetime.fromisoformat(timestamp)
            if dt.hour < 8 or dt.hour > 16:
                continue
            segment = "Morning" if dt.hour < 12 else "Afternoon"
            key = (dt.date().isoformat(), segment)
            buckets.setdefault(key, {"temps": [], "winds": [], "snowfalls": []})
            buckets[key]["temps"].append(temps[idx])
            buckets[key]["winds"].append(winds[idx])
            buckets[key]["snowfalls"].append(snowfalls[idx])

        for (date_iso, segment), stats in buckets.items():
            windows.append(
                {
                    "date": date_iso,
                    "segment": segment,
                    "temp_c": round(sum(stats["temps"]) / len(stats["temps"]), 1),
                    "wind_kmh": round(sum(stats["winds"]) / len(stats["winds"]), 1),
                    "snowfall_mm": round(sum(stats["snowfalls"]), 1),
                }
            )

        self.weather_cache[resort_id] = {
            "cached_at": now.isoformat(),
            "windows": windows,
        }
        self._write_json(self.weather_file, self.weather_cache)
        return windows

    def _best_window(
        self,
        resort: Dict,
        powder_pref: int,
        preferred_temp_c: float,
        wind_tolerance_kmh: float,
        coords: Optional[Tuple[float, float]],
    ) -> Dict:
        if coords is None:
            return {"label": "No forecast available", "weather_score": 0.45}
        windows = self._fetch_week_forecast(resort["id"], coords[0], coords[1])
        if not windows:
            return {"label": "No forecast available", "weather_score": 0.45}

        best = None
        best_score = -1.0
        for window in windows:
            snow_score = clamp((window["snowfall_mm"] / 4.0) * (powder_pref / 10.0))
            temp_penalty = abs(window["temp_c"] - preferred_temp_c) / 14.0
            temp_score = clamp(1 - temp_penalty)
            wind_score = clamp(1 - (window["wind_kmh"] / max(10.0, wind_tolerance_kmh)))
            total = (snow_score * 0.45) + (temp_score * 0.35) + (wind_score * 0.20)
            if total > best_score:
                best = window
                best_score = total

        if best is None:
            return {"label": "No forecast available", "weather_score": 0.45}

        day = datetime.fromisoformat(best["date"]).strftime("%A")
        label = f"{day} {best['segment']} ({best['temp_c']}C, wind {best['wind_kmh']} km/h, snowfall {best['snowfall_mm']} mm)"
        return {"label": label, "weather_score": round(clamp(best_score), 3)}

    def recommend(self, resorts: List[Dict], preferences: Dict) -> Dict:
        skill_level = preferences.get("skill_level", "intermediate")
        terrain_pref = preferences.get("terrain_mix", {"blue": 35, "red": 45, "black": 20})
        blue_pref = float(terrain_pref.get("blue", 35))
        red_pref = float(terrain_pref.get("red", 45))
        black_pref = float(terrain_pref.get("black", 20))
        total_pref = max(1.0, blue_pref + red_pref + black_pref)
        target_mix = (blue_pref / total_pref, red_pref / total_pref, black_pref / total_pref)
        skill_mix = self._skill_target(skill_level)
        max_drive_hours = float(preferences.get("max_drive_hours", 5))
        budget_cad = float(preferences.get("budget_cad", 260))
        crowd_tolerance = preferences.get("crowd_tolerance", "medium")
        powder_pref = int(preferences.get("powder_preference", 6))
        preferred_temp_c = float(preferences.get("preferred_temp_c", -5))
        wind_tolerance_kmh = float(preferences.get("wind_tolerance_kmh", 30))
        user_lat = preferences.get("user_lat")
        user_lon = preferences.get("user_lon")
        user_lat = float(user_lat) if user_lat is not None else None
        user_lon = float(user_lon) if user_lon is not None else None
        fuel_cost_per_km = float(preferences.get("fuel_cost_per_km", 0.27))
        geocode_budget = int(preferences.get("geocode_budget", 20))

        candidates = []
        for resort in resorts:
            resort_mix = self._terrain_mix(resort)
            terrain_score = self._terrain_score(target_mix, resort_mix)
            skill_score = self._terrain_score(skill_mix, resort_mix)

            day_pass = self._parse_day_pass_cad(resort.get("day_pass"))
            day_pass = day_pass if day_pass is not None else 130.0

            drive_hours = None
            distance_km = None
            travel_cost = 0.0
            drive_score = 0.55
            if user_lat is not None and user_lon is not None:
                coords = None
                cached = self.coords_cache.get(resort.get("id"))
                if cached and not cached.get("missing"):
                    coords = (float(cached["lat"]), float(cached["lon"]))
                elif geocode_budget > 0:
                    coords = self._lookup_coordinates(resort)
                    geocode_budget -= 1
                if coords is not None:
                    distance_km, drive_hours = self._estimate_drive(user_lat, user_lon, coords[0], coords[1])
                    travel_cost = round(distance_km * 2 * fuel_cost_per_km, 2)
                    drive_score = clamp(1 - (drive_hours / max(0.5, max_drive_hours)))
                    if drive_hours > max_drive_hours:
                        continue
                else:
                    drive_score = 0.25

            total_cost = day_pass + travel_cost
            budget_score = clamp(1 - ((total_cost - budget_cad) / max(50.0, budget_cad)))
            crowd_score = self._crowd_score(crowd_tolerance, resort)

            base_fit = (
                terrain_score * 0.27
                + skill_score * 0.20
                + budget_score * 0.20
                + drive_score * 0.18
                + crowd_score * 0.15
            )

            candidates.append(
                {
                    "resort": resort,
                    "scores": {
                        "terrain": round(terrain_score, 3),
                        "skill": round(skill_score, 3),
                        "budget": round(budget_score, 3),
                        "drive": round(drive_score, 3),
                        "crowd": round(crowd_score, 3),
                    },
                    "fit_base": base_fit,
                    "travel": {
                        "distance_km": round(distance_km, 1) if distance_km is not None else None,
                        "drive_hours": round(drive_hours, 2) if drive_hours is not None else None,
                    },
                    "cost": {
                        "day_pass_cad": round(day_pass, 2),
                        "travel_cad": round(travel_cost, 2),
                        "total_cad": round(total_cost, 2),
                    },
                    "coords": coords,
                }
            )

        if not candidates:
            return {"results": [], "compare_top_3": [], "alert": None}

        candidates.sort(key=lambda x: x["fit_base"], reverse=True)
        for candidate in candidates[:15]:
            window = self._best_window(
                candidate["resort"],
                powder_pref=powder_pref,
                preferred_temp_c=preferred_temp_c,
                wind_tolerance_kmh=wind_tolerance_kmh,
                coords=candidate.get("coords"),
            )
            candidate["scores"]["weather"] = window["weather_score"]
            candidate["best_day_window"] = window["label"]
            final_fit = (candidate["fit_base"] * 0.85) + (window["weather_score"] * 0.15)
            candidate["fit_score"] = round(final_fit * 100, 1)

        for candidate in candidates[15:]:
            candidate["scores"]["weather"] = 0.45
            candidate["best_day_window"] = "Not computed (outside top candidates)"
            final_fit = (candidate["fit_base"] * 0.85) + (0.45 * 0.15)
            candidate["fit_score"] = round(final_fit * 100, 1)

        candidates.sort(key=lambda x: x["fit_score"], reverse=True)
        results = []
        for idx, candidate in enumerate(candidates[:20], start=1):
            reason_pairs = sorted(candidate["scores"].items(), key=lambda kv: kv[1], reverse=True)[:3]
            reason_text = ", ".join([f"{key} fit {round(value * 100)}%" for key, value in reason_pairs])
            results.append(
                {
                    "rank": idx,
                    "resort": candidate["resort"],
                    "fit_score": candidate["fit_score"],
                    "why_top": f"Strong match on {reason_text}.",
                    "best_day_window": candidate["best_day_window"],
                    "estimated_cost": candidate["cost"],
                    "estimated_travel": candidate["travel"],
                    "score_breakdown": candidate["scores"],
                }
            )

        compare_top_3 = [
            {
                "name": row["resort"]["name"],
                "fit_score": row["fit_score"],
                "total_slope_km": row["resort"].get("total_slope_km"),
                "lifts_count": row["resort"].get("lifts_count"),
                "day_pass_cad": row["estimated_cost"]["day_pass_cad"],
                "travel_hours": row["estimated_travel"]["drive_hours"],
                "total_trip_cad": row["estimated_cost"]["total_cad"],
                "best_day_window": row["best_day_window"],
            }
            for row in results[:3]
        ]

        alert = None
        if results:
            top = results[0]
            if top["fit_score"] >= 78 and "No forecast" not in top["best_day_window"]:
                alert = f"Ideal conditions detected: {top['resort']['name']} looks best at {top['best_day_window']}."

        return {
            "results": results,
            "compare_top_3": compare_top_3,
            "alert": alert,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
