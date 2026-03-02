import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)


BASE_LIST_URL = "https://www.skiresort.info/ski-resorts/british-columbia/sorted/slope-length/"
PAGE_URL_TEMPLATE = "https://www.skiresort.info/ski-resorts/british-columbia/page/{page}/sorted/slope-length/"


@dataclass
class ResortRecord:
    id: str
    name: str
    region: str
    district: Optional[str]
    elevation_difference_m: Optional[int]
    elevation_base_m: Optional[int]
    elevation_top_m: Optional[int]
    total_slope_km: Optional[float]
    blue_slope_km: Optional[float]
    red_slope_km: Optional[float]
    black_slope_km: Optional[float]
    lifts_count: Optional[int]
    lifts_and_features: List[str]
    day_pass: Optional[str]
    source_url: str
    last_updated: str


def slugify(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return value or "resort"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _extract_int(text: str) -> Optional[int]:
    match = re.search(r"(-?\d+)", text.replace(",", ""))
    return int(match.group(1)) if match else None


def _extract_float_km(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*km", text.lower())
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


class BCResortAggregator:
    def __init__(self, cache_path: str = "data/bc_resorts_cache.json") -> None:
        self.cache_file = Path(cache_path)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

    def _fetch_html(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=25)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as exc:
            LOGGER.warning("Failed to fetch %s: %s", url, exc)
            return None

    def _parse_resort_item(self, item) -> Optional[ResortRecord]:
        heading_link = item.select_one("a.h3")
        if heading_link is None:
            return None

        raw_name = _clean_text(heading_link.get_text(" ", strip=True))
        name = re.sub(r"^\d+\.\s*", "", raw_name)
        source_url = heading_link.get("href", "").strip() or BASE_LIST_URL

        breadcrumbs = [_clean_text(a.get_text(" ", strip=True)) for a in item.select(".sub-breadcrumb a")]
        # Expected: North America > Canada > British Columbia > Region > District
        region = breadcrumbs[3] if len(breadcrumbs) >= 4 else "British Columbia"
        district = breadcrumbs[4] if len(breadcrumbs) >= 5 else None

        elevation_difference_m = None
        elevation_base_m = None
        elevation_top_m = None
        total_slope_km = None
        blue_slope_km = None
        red_slope_km = None
        black_slope_km = None
        lifts_count = None
        lifts_and_features: List[str] = []
        day_pass = None

        for row in item.select("table.info-table tr"):
            row_text = _clean_text(row.get_text(" ", strip=True))
            if not row_text:
                continue
            icon = row.select_one("i")
            icon_classes = set(icon.get("class", [])) if icon else set()

            if "icon-uE002-height" in icon_classes:
                nums = [int(m) for m in re.findall(r"(\d+)\s*m", row_text)]
                if nums:
                    elevation_difference_m = nums[0]
                if len(nums) >= 3:
                    elevation_base_m = nums[1]
                    elevation_top_m = nums[2]
                continue

            if "icon-uE004-skirun" in icon_classes:
                slopes = [_clean_text(s.get_text(" ", strip=True)) for s in row.select(".slopeinfoitem")]
                if slopes:
                    total_slope_km = _extract_float_km(slopes[0])
                if len(slopes) >= 2:
                    blue_slope_km = _extract_float_km(slopes[1])
                if len(slopes) >= 3:
                    red_slope_km = _extract_float_km(slopes[2])
                if len(slopes) >= 4:
                    black_slope_km = _extract_float_km(slopes[3])
                continue

            if "icon-uE001-skipass" in icon_classes:
                day_pass = row_text
                continue

            if row.select_one(".lift-icon-small"):
                li_values = [_clean_text(li.get_text(" ", strip=True)) for li in row.select("li")]
                li_values = [v for v in li_values if v]
                lifts_and_features = li_values
                for entry in li_values:
                    if "ski lift" in entry.lower():
                        lifts_count = _extract_int(entry)
                        break
                continue

        now = datetime.now(timezone.utc).isoformat()
        return ResortRecord(
            id=slugify(name),
            name=name,
            region=region,
            district=district,
            elevation_difference_m=elevation_difference_m,
            elevation_base_m=elevation_base_m,
            elevation_top_m=elevation_top_m,
            total_slope_km=total_slope_km,
            blue_slope_km=blue_slope_km,
            red_slope_km=red_slope_km,
            black_slope_km=black_slope_km,
            lifts_count=lifts_count,
            lifts_and_features=lifts_and_features,
            day_pass=day_pass,
            source_url=source_url,
            last_updated=now,
        )

    def _collect_from_skiresort_info(self) -> List[ResortRecord]:
        pages = [BASE_LIST_URL, PAGE_URL_TEMPLATE.format(page=2)]
        records: List[ResortRecord] = []
        seen = set()

        for url in pages:
            soup = self._fetch_html(url)
            if soup is None:
                continue
            items = soup.select(".resort-list-item")
            for item in items:
                rec = self._parse_resort_item(item)
                if rec is None or rec.id in seen:
                    continue
                seen.add(rec.id)
                records.append(rec)

        records.sort(key=lambda r: r.name.lower())
        return records

    def _write_cache(self, records: List[ResortRecord]) -> None:
        payload = [asdict(rec) for rec in records]
        with self.cache_file.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    def _read_cache(self) -> List[ResortRecord]:
        if not self.cache_file.exists():
            return []
        try:
            with self.cache_file.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            return [ResortRecord(**row) for row in payload]
        except Exception as exc:
            LOGGER.warning("Cache read failed, ignoring stale cache: %s", exc)
            return []

    def collect(self, refresh: bool = False) -> List[ResortRecord]:
        if not refresh:
            cached = self._read_cache()
            if cached:
                return cached

        records = self._collect_from_skiresort_info()
        if records:
            self._write_cache(records)
            return records

        return self._read_cache()

    def get_by_id(self, resort_id: str, refresh: bool = False) -> Optional[ResortRecord]:
        for record in self.collect(refresh=refresh):
            if record.id == resort_id:
                return record
        return None
