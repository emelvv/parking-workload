import logging
import math
import os
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from pathlib import Path

load_dotenv()


_log_path = Path(__file__).resolve().parent / "service.log"
_logger = logging.getLogger("parking_service")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(_log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be a valid integer") from exc


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise RuntimeError(
        f"Environment variable {name} must be a boolean (accepted values: 1/0, true/false, yes/no, on/off)"
    )


def _parse_coordinates_string(value: str, *, raise_for: str) -> Tuple[float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            f"{raise_for} must contain latitude and longitude separated by a comma, e.g. '55.7558, 37.6173'"
        )
    latitude_str, longitude_str = parts
    try:
        latitude = float(latitude_str)
        longitude = float(longitude_str)
    except ValueError as exc:
        raise ValueError(f"{raise_for} must contain valid floating point numbers") from exc
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise ValueError(
            f"{raise_for} must contain latitude in [-90, 90] and longitude in [-180, 180]"
        )
    return latitude, longitude


def _get_env_coordinates(name: str, default: Tuple[float, float]) -> Tuple[float, float]:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return _parse_coordinates_string(value, raise_for=f"Environment variable {name}")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


class Settings(BaseModel):
    dgis_api_key: str = Field(min_length=1)
    default_radius: int = Field(default=600, ge=1, le=40000)
    default_limit: int = Field(default=10, ge=1, le=50)
    center_latitude: float = Field(default=55.7558, ge=-90, le=90)
    center_longitude: float = Field(default=37.6173, ge=-180, le=180)
    auto_price_by_distance: bool = Field(default=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    center_latitude, center_longitude = _get_env_coordinates(
        "CENTER_COORDINATES", (55.7558, 37.6173)
    )
    settings = Settings(
        dgis_api_key=os.getenv("DGIS_API_KEY", ""),
        default_radius=_get_env_int("DEFAULT_RADIUS", 600),
        default_limit=_get_env_int("DEFAULT_LIMIT", 10),
        center_latitude=center_latitude,
        center_longitude=center_longitude,
        auto_price_by_distance=_get_env_bool("AUTO_PRICE_BY_DISTANCE", False),
    )
    if not settings.dgis_api_key:
        raise RuntimeError("Environment variable DGIS_API_KEY must be set")
    return settings


def search_parking_near_coords(
    latitude: float,
    longitude: float,
    api_key: str,
    radius: int,
    limit: int,
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    url = "https://catalog.api.2gis.com/3.0/items"
    params = {
        "key": api_key,
        "type": "parking",
        "point": f"{longitude},{latitude}",
        "radius": radius,
        "page_size": limit,
        "fields": ",".join([
            "items.name",
            "items.address_name",
            "items.point",
            "items.purpose",
            "items.capacity",
            "items.is_paid",
            "items.access",
            "items.access_comment",
            "items.parking",
            "items.parking.congestion",
            "items.parking.tariffs",
            "items.parking.price",
            "items.for_trucks",
            "items.paving_type",
            "items.is_incentive",
            "items.level_count",
            "items.floors",
            "items.contact_groups",
            "items.reviews",
            "items.schedule",
        ]),
    }

    response = requests.get(url, params=params, timeout=10)
    if not response.ok:
        _logger.error(
            "2GIS API error: status=%s, url=%s, response=%s",
            response.status_code,
            response.url,
            response.text,
        )
    response.raise_for_status()
    data = response.json()
    result = data.get("result", {})
    items = result.get("items", [])
    total = result.get("total")
    if total is None:
        try:
            total = int(result.get("total_count"))  # типичный альтернативный ключ
        except (TypeError, ValueError):
            total = None
    return items, total


def get_parking_by_id(
    item_id: str,
    api_key: str,
    fields: Optional[str] = None,
) -> Dict[str, Any]:
    url = "https://catalog.api.2gis.com/3.0/items/byid"
    params = {
        "key": api_key,
        "id": item_id,
    }
    if fields:
        params["fields"] = fields

    response = requests.get(url, params=params, timeout=10)
    if not response.ok:
        _logger.error(
            "2GIS API error (byid): status=%s, url=%s, response=%s",
            response.status_code,
            response.url,
            response.text,
        )
    response.raise_for_status()

    data = response.json()
    result = data.get("result", {})
    items = result.get("items")
    if items:
        return items[0]
    _logger.info("Parking with id=%s not found in 2GIS response", item_id)
    return {}


def _extract_coordinates(item: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    candidates: Iterable[Optional[Dict[str, Any]]] = (
        item.get("point"),
        item.get("geometry"),
        item.get("location"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        lat = candidate.get("lat") or candidate.get("latitude")
        lon = candidate.get("lon") or candidate.get("longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (TypeError, ValueError):
                continue
    return None


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_earth_km * c


def _format_price(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)):
        return f"{value} ₽"
    if isinstance(value, dict):
        amount = value.get("value") or value.get("amount") or value.get("cost")
        currency = value.get("currency") or value.get("currency_code") or "₽"
        unit = value.get("unit") or value.get("period") or value.get("time")
        if amount is not None:
            amount_str = str(amount)
            result = f"{amount_str} {currency}".strip()
            if unit:
                result = f"{result} / {unit}"
            return result
        nested = value.get("items") or value.get("tariffs")
        if nested:
            return _format_price(nested)
    if isinstance(value, list):
        formatted_values = [val for val in (_format_price(item) for item in value) if val]
        if formatted_values:
            return "; ".join(formatted_values)
    return None


def _extract_parking_comment(item: Dict[str, Any], target_id: Optional[str] = None) -> Optional[str]:
    parking_data = item.get("parking")

    candidates: List[Dict[str, Any]] = []
    if isinstance(parking_data, dict):
        candidates.append(parking_data)
        nested = parking_data.get("items")
        if isinstance(nested, list):
            candidates.extend(entry for entry in nested if isinstance(entry, dict))
    elif isinstance(parking_data, list):
        candidates.extend(entry for entry in parking_data if isinstance(entry, dict))

    if target_id is not None:
        for entry in candidates:
            if str(entry.get("id")) == str(target_id) and entry.get("comment"):
                comment = entry.get("comment")
                if isinstance(comment, str) and comment.strip():
                    return comment.strip()

    for entry in candidates:
        comment = entry.get("comment")
        if isinstance(comment, str) and comment.strip():
            return comment.strip()

    comment_generic = item.get("parking_comment")
    if isinstance(comment_generic, str) and comment_generic.strip():
        return comment_generic.strip()

    return None


def _extract_price(item: Dict[str, Any], *, fallback_comment: Optional[str] = None) -> str:
    comment = fallback_comment or _extract_parking_comment(item, target_id=item.get("id"))
    if comment:
        return comment

    parking_info = item.get("parking") or {}
    for candidate in (
        item.get("price"),
        parking_info.get("price"),
        parking_info.get("tariffs"),
        parking_info.get("payment"),
    ):
        formatted = _format_price(candidate)
        if formatted:
            return formatted
    if item.get("is_paid"):
        return "Платная (тариф не указан)"
    return "Бесплатно"


def _extract_spaces(item: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    parking_info = item.get("parking") or {}
    spaces = parking_info.get("spaces") if isinstance(parking_info, dict) else None
    if isinstance(spaces, dict):
        common = spaces.get("common")
        if isinstance(common, dict):
            total = common.get("total")
            free = common.get("free")
            try:
                total_int = int(total) if total is not None else None
            except (TypeError, ValueError):
                total_int = None
            try:
                free_int = int(free) if free is not None else None
            except (TypeError, ValueError):
                free_int = None
            return total_int, free_int
    capacity = item.get("capacity")
    try:
        capacity_int = int(capacity) if capacity is not None else None
    except (TypeError, ValueError):
        try:
            total_value = capacity.get("total") if isinstance(capacity, dict) else None
            capacity_int = int(total_value) if total_value is not None else None
        except (TypeError, ValueError, AttributeError):
            capacity_int = None
    return capacity_int, None


ALLOWED_PURPOSES = {"car"}
EXCLUDED_PURPOSES = {"disabled", "invalid", "resident", "residents"}
ACCESS_KEYWORDS = ("public", "обществен")

# Приблизительные тарифные зоны Москвы: чем ближе к центру, тем выше ставка за час.
DISTANCE_PRICE_BRACKETS: Tuple[Tuple[float, int], ...] = (
    (0.30, 800),   # Исторический центр
    (1.00, 400),   # Прилегающие кварталы
    (3.00, 250),   # Между Садовым и ТТК
    (8.00, 150),   # Внутри МКАД
    (20.0, 100),   # Спальные районы
)
DISTANCE_PRICE_FALLBACK = 70  # За пределами МКАД


def _estimate_price_by_distance(distance_km: float) -> int:
    for threshold, price in DISTANCE_PRICE_BRACKETS:
        if distance_km <= threshold:
            return price
    return DISTANCE_PRICE_FALLBACK


class ParkingResponse(BaseModel):
    name: Optional[str] = Field(None, description="Название парковки")
    coordinates: str = Field(..., description="Координаты парковки в формате 'широта, долгота'")
    purpose: Optional[str] = Field(None, description="Назначение парковки согласно данным 2ГИС")
    capacity: Optional[int] = Field(None, description="Вместимость парковки по данным 2ГИС")
    is_paid: Optional[bool] = Field(None, description="Признак платности парковки")
    price_comment: Optional[str] = Field(None, description="Описание тарифов парковки (как строка)")
    price_per_hour: Optional[int] = Field(
        None, description="Стоимость парковки в час в рублях (при автогенерации)"
    )
    distance_to_request_m: float = Field(..., description="Расстояние от точки запроса до парковки в метрах")
    distance_to_center_km: float = Field(..., description="Расстояние от центра города до парковки в километрах")
    total_spaces: Optional[int] = Field(None, description="Количество парковочных мест по данным загруженности")
    free_spaces: Optional[int] = Field(None, description="Оценка свободных мест, если есть данные")


class NearestParkingResponse(BaseModel):
    total_found: Optional[int] = Field(
        None,
        description="Количество парковок, найденных в ответе 2ГИС",
    )
    parking: ParkingResponse = Field(
        ..., description="Детальная информация о ближайшей парковке"
    )


app = FastAPI(
    title="Parking Finder Service",
    version="1.0.0",
    description="API для поиска ближайших парковок по данным 2ГИС",
    openapi_tags=[
        {
            "name": "Parking",
            "description": "Операции для поиска парковок и получения информации по ним",
        }
    ],
)


def _normalize_purpose_values(purpose_raw: Any) -> List[str]:
    if purpose_raw is None:
        return []
    if isinstance(purpose_raw, list):
        return [str(value).strip().lower() for value in purpose_raw if str(value).strip()]
    return [value.strip().lower() for value in str(purpose_raw).split(",") if value.strip()]


def _fetch_parking_comment(item_id: str, api_key: str) -> Optional[str]:
    try:
        item = get_parking_by_id(
            item_id=item_id,
            api_key=api_key,
            fields="items.parking",
        )
    except requests.RequestException as exc:
        _logger.warning("Не удалось получить тарифы для парковки %s: %s", item_id, exc)
        return None

    if not item:
        return None

    return _extract_parking_comment(item, target_id=item_id)


def _build_parking_response(
    *,
    request_lat: float,
    request_lon: float,
    item: Dict[str, Any],
    settings: Settings,
) -> Optional[Tuple[ParkingResponse, float, Optional[str]]]:
    purpose_values = _normalize_purpose_values(item.get("purpose"))
    if purpose_values:
        if any(value in EXCLUDED_PURPOSES for value in purpose_values):
            return None
        if ALLOWED_PURPOSES and not any(value in ALLOWED_PURPOSES for value in purpose_values):
            return None
    else:
        return None

    if not item.get("is_paid"):
        return None

    access_text = str(item.get("access") or "").lower()
    if not any(keyword in access_text for keyword in ACCESS_KEYWORDS):
        return None

    coords = _extract_coordinates(item)
    if not coords:
        return None
    item_lat, item_lon = coords

    distance_request_km = _haversine_distance(request_lat, request_lon, item_lat, item_lon)
    distance_center_km = _haversine_distance(
        settings.center_latitude,
        settings.center_longitude,
        item_lat,
        item_lon,
    )
    price_comment = _extract_price(item, fallback_comment=item.get("parking_comment"))
    total_spaces, free_spaces = _extract_spaces(item)

    price_per_hour: Optional[int] = None
    if settings.auto_price_by_distance:
        price_per_hour = _estimate_price_by_distance(distance_center_km)
        price_comment = None

    capacity_value = total_spaces
    if capacity_value is None:
        raw_capacity = item.get("capacity")
        try:
            capacity_value = int(raw_capacity) if raw_capacity is not None else None
        except (TypeError, ValueError):
            capacity_value = None

    purpose_original = item.get("purpose")
    if isinstance(purpose_original, list):
        purpose_display = ", ".join(str(value) for value in purpose_original)
    else:
        purpose_display = purpose_original

    parking_response = ParkingResponse(
        name=item.get("name") or "Название не указано",
        coordinates=f"{item_lat:.6f}, {item_lon:.6f}",
        purpose=purpose_display,
        capacity=capacity_value,
        is_paid=item.get("is_paid"),
        price_comment=price_comment,
        price_per_hour=price_per_hour,
        distance_to_request_m=round(distance_request_km * 1000, 2),
        distance_to_center_km=round(distance_center_km, 3),
        total_spaces=total_spaces,
        free_spaces=free_spaces,
    )

    return parking_response, distance_request_km, item.get("id")


@app.get(
    "/parking/nearest",
    response_model=NearestParkingResponse,
    summary="Найти ближайшую парковку",
    response_model_exclude_none=True,
    tags=["Parking"],
)
def get_nearest_parking(
    coordinates: str = Query(
        ...,
        description="Координаты точки запроса в формате '55.741834, 37.630808' (широта, долгота)",
    ),
    radius: Optional[int] = Query(
        None,
        ge=1,
        le=40000,
        description="Радиус поиска в метрах. По умолчанию берётся значение из конфигурации",
    ),
) -> NearestParkingResponse:
    settings = get_settings()
    search_radius = radius or settings.default_radius

    try:
        latitude, longitude = _parse_coordinates_string(coordinates, raise_for="Query parameter 'coordinates'")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total: Optional[int] = None

    try:
        items, total = search_parking_near_coords(
            latitude=latitude,
            longitude=longitude,
            api_key=settings.dgis_api_key,
            radius=search_radius,
            limit=settings.default_limit,
        )
    except requests.RequestException as exc:
        _logger.error("Request to 2GIS failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Ошибка обращения к 2GIS: {exc}") from exc

    enriched_items: List[Tuple[float, ParkingResponse, Optional[str]]] = []
    for item in items:
        result = _build_parking_response(
            request_lat=latitude,
            request_lon=longitude,
            item=item,
            settings=settings,
        )
        if result is None:
            continue
        parking_response, distance_request_km, item_id = result
        enriched_items.append((distance_request_km, parking_response, item_id))

    if not enriched_items:
        _logger.info(
            "No parking found for coordinates=%s with radius=%s",
            coordinates,
            search_radius,
        )
        raise HTTPException(status_code=404, detail="Парковки в заданном радиусе не найдены")

    enriched_items.sort(key=lambda item: item[0])
    _, best_response, best_item_id = enriched_items[0]

    if best_item_id and not settings.auto_price_by_distance:
        comment = _fetch_parking_comment(best_item_id, settings.dgis_api_key)
        if comment:
            best_response = best_response.model_copy(update={"price_comment": comment})

    total_found = total if total is not None else len(items)
    return NearestParkingResponse(total_found=total_found, parking=best_response)


@app.get(
    "/parking/{item_id}",
    response_model=NearestParkingResponse,
    summary="Получить парковку по идентификатору",
    response_model_exclude_none=True,
    tags=["Parking"],
)
def get_parking_by_item_id(
    item_id: str,
) -> NearestParkingResponse:
    settings = get_settings()

    try:
        item = get_parking_by_id(
            item_id=item_id,
            api_key=settings.dgis_api_key,
            fields="items.name,items.point,items.purpose,items.capacity,items.is_paid,items.access,items.access_comment,items.parking,items.parking.congestion,items.parking.tariffs,items.parking.price,items.for_trucks,items.paving_type,items.is_incentive,items.level_count,items.contact_groups,items.reviews,items.schedule",
        )
    except requests.RequestException as exc:
        _logger.error("Request to 2GIS by id failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Ошибка обращения к 2GIS: {exc}") from exc

    if not item:
        raise HTTPException(status_code=404, detail="Парковка с указанным идентификатором не найдена")

    comment: Optional[str] = None
    if not settings.auto_price_by_distance:
        comment = _extract_parking_comment(item, target_id=item_id)
        if comment:
            item["parking_comment"] = comment

    result = _build_parking_response(
        request_lat=settings.center_latitude,
        request_lon=settings.center_longitude,
        item=item,
        settings=settings,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Парковка не подходит под критерии фильтрации")

    parking_response, _, _ = result

    if comment:
        parking_response = parking_response.model_copy(update={"price_comment": comment})

    return NearestParkingResponse(total_found=1, parking=parking_response)


if __name__ == "__main__":  # pragma: no cover
    import sys
    import uvicorn

    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    if project_root not in sys.path:
        sys.path.append(project_root)

    uvicorn.run(
        "parser.main:app",
        host="0.0.0.0",
        port=_get_env_int("PORT", 8000),
        reload=bool(_get_env_int("RELOAD", 0)),
    )
