/**
 * Конфигурация API
 * Обновите API_ENDPOINT, если нужно, чтобы он указывал на ваш бэкенд.
 */
const API_ENDPOINT = '/api/parking/load';
const REQUEST_METHOD = 'POST';

const STATUS_PRESETS = {
  low: { label: 'Свободно', cssClass: 'status-card--success', emoji: '🟢' },
  medium: { label: 'Плотно', cssClass: 'status-card--warning', emoji: '🟡' },
  high: { label: 'Переполнено', cssClass: 'status-card--danger', emoji: '🔴' },
  unknown: { label: 'Нет данных', cssClass: 'status-card--warning', emoji: '⚪️' },
};

const HACK_CONFIG = {
  appId: 'ru.2gishackathon.app03.01',
  key: 'e50d3992-8076-47d8-bc3c-9add5a142f20',
};

// Вся инициализация ждёт загрузки DOM
document.addEventListener('DOMContentLoaded', () => {
  // Ноды формы/инпута/плейсхолдера статуса — безопасно ищем их (могут отсутствовать в тестовой странице)
  const form = document.getElementById('lookup-form');
  const input = document.getElementById('parking-number');
  const errorField = document.getElementById('lookup-error');
  const card = document.getElementById('status-card');

  // Инициализация карты MapGL — создаём карту и включаем клики
  let map = null;
  try {
    map = new mapgl.Map('map', {
      center: [37.618423, 55.751244], // [lng, lat]
      zoom: 12,
      key: HACK_CONFIG.key,
    });
  } catch (err) {
    console.error('Ошибка инициализации mapgl:', err);
  }

  // Храним маркеры, если понадобятся
  const markers = [];

  // --- UI / форма ---
  if (form && input) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clearError();

      const rawValue = input.value.trim();
      if (!rawValue) {
        showError('Введите номер парковки.');
        return;
      }

      await requestStatus(rawValue);
    });
  }

  function showError(message) {
    if (!errorField) {
      console.warn('Ошибка (no errorField):', message);
      return;
    }
    errorField.textContent = message;
    errorField.hidden = false;
  }

  function clearError() {
    if (!errorField) return;
    errorField.hidden = true;
    errorField.textContent = '';
  }

  // --- Запрос к API ---
  async function requestStatus(parkingNumber) {
    if (input) toggleForm(false, 'Запрос…');

    if (card) renderLoading();

    try {
      const response = await fetch(API_ENDPOINT, {
        method: REQUEST_METHOD,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parkingNumber }),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => '');
        throw new Error(`Сервер вернул ${response.status}${text ? `: ${text}` : ''}`);
      }

      const payload = await response.json().catch(() => null);
      const normalized = normalizePayload(payload, parkingNumber);
      renderStatus(normalized);
    } catch (err) {
      console.error(err);
      renderErrorState(err);
    } finally {
      if (input) toggleForm(true);
    }
  }

  function toggleForm(isEnabled, loadingText) {
    if (!form) return;
    const inputEl = form.querySelector('#parking-number') || form.querySelector('input');
    const submitButton = form.querySelector('.lookup__submit') || form.querySelector('button[type="submit"]');

    if (inputEl) inputEl.disabled = !isEnabled;
    if (submitButton) {
      submitButton.disabled = !isEnabled;
      if (!isEnabled) {
        submitButton.dataset.originalText = submitButton.textContent;
        submitButton.textContent = loadingText ?? 'Загрузка…';
      } else if (submitButton.dataset.originalText) {
        submitButton.textContent = submitButton.dataset.originalText;
        delete submitButton.dataset.originalText;
      }
    }
  }

  function renderLoading() {
    if (!card) return;
    card.innerHTML = `
      <div class="status-card">
        <div class="status-card__placeholder">
          <span class="status-card__emoji" aria-hidden="true">⏳</span>
          <p class="status-card__text">Получаем данные о загруженности…</p>
        </div>
      </div>
    `;
  }

  function renderErrorState(error) {
    if (!card) {
      console.warn('renderErrorState:', error);
      return;
    }
    card.innerHTML = `
      <div class="status-card status-card--danger">
        <div class="status-card__placeholder">
          <span class="status-card__emoji" aria-hidden="true">⚠️</span>
          <p class="status-card__text">${escapeHtml(error?.message ?? 'Не удалось получить данные. Попробуйте позже.')}</p>
        </div>
      </div>
    `;
  }

  function renderStatus(data) {
    if (!card) {
      console.warn('renderStatus: card отсутствует', data);
      return;
    }

    const badge = STATUS_PRESETS[data.statusPreset] ?? STATUS_PRESETS.unknown;

    const statsHtml = [
      { label: 'Занято', value: formatNumber(data.occupiedSpots, '--') },
      { label: 'Свободно', value: formatNumber(data.freeSpots, '--') },
      { label: 'Всего мест', value: formatNumber(data.totalSpots, '--') },
      { label: 'Загрузка', value: data.occupancyPercent != null ? `${data.occupancyPercent}%` : '--' },
    ]
      .filter((stat) => stat.value !== '--' || stat.label === 'Загрузка')
      .map(
        (stat) => `
          <div class="status-card__stat">
            <span class="status-card__stat-label">${stat.label}</span>
            <span class="status-card__stat-value">${stat.value}</span>
          </div>
        `
      )
      .join('');

    card.innerHTML = `
      <div class="status-card ${badge.cssClass}">
        <div class="status-card__header">
          <div>
            <p class="status-card__badge">${badge.emoji} ${badge.label}</p>
            <h2 class="status-card__title">Парковка №${escapeHtml(String(data.parkingNumber ?? '—'))}</h2>
            <p class="status-card__subtitle">${escapeHtml(data.humanStatus ?? '')}</p>
          </div>
          <div class="status-card__meta">
            ${data.updatedAtText ? `<span class="status-card__meta-time">Обновлено: ${escapeHtml(data.updatedAtText)}</span>` : ''}
          </div>
        </div>

        <div class="status-card__progress" role="img" aria-label="Загруженность ${data.occupancyPercent ?? 'неизвестна'}%">
          <div class="status-card__progress-fill" style="width: ${Math.min(data.occupancyPercent ?? 0, 100)}%"></div>
        </div>

        <div class="status-card__stats">
          ${statsHtml}
        </div>

        <footer class="status-card__footer">
          ${data.updatedAtRelative ? `Актуальность: ${escapeHtml(data.updatedAtRelative)}` : 'Актуальность зависит от частоты обновлений API.'}
        </footer>
      </div>
    `;
  }

  // --- Payload normalization / утилиты ---
  function normalizePayload(payload, fallbackParkingNumber) {
    const raw = payload?.data ?? payload;

    if (!raw || typeof raw !== 'object') {
      throw new Error('Ответ сервера имеет неожиданный формат.');
    }

    const total = coerceNumber(raw.totalSpots ?? raw.total ?? raw.capacity ?? raw.maxCapacity);
    const occupied = coerceNumber(raw.occupiedSpots ?? raw.occupied ?? raw.busy ?? raw.taken);
    const free = coerceNumber(raw.freeSpots ?? raw.free ?? raw.available ?? raw.vacant);

    let occupancyPercent = null;
    if (raw.occupancy != null) occupancyPercent = normalizePercent(raw.occupancy);
    if (occupancyPercent == null && raw.occupancyPercent != null) occupancyPercent = normalizePercent(raw.occupancyPercent);
    if (occupancyPercent == null && occupied != null && total != null && total > 0) occupancyPercent = Math.round((occupied / total) * 100);
    if (occupancyPercent == null && free != null && total != null && total > 0) occupancyPercent = Math.round(((total - free) / total) * 100);

    let resolvedOccupied = occupied;
    let resolvedFree = free;

    if (resolvedOccupied == null && total != null && free != null) resolvedOccupied = Math.max(total - free, 0);
    if (resolvedFree == null && total != null && occupied != null) resolvedFree = Math.max(total - occupied, 0);

    const statusRaw = (raw.status ?? raw.state ?? '').toString().toLowerCase();
    const statusPreset = chooseStatusPreset(statusRaw, occupancyPercent);
    const humanStatus = formatHumanStatus(statusRaw, statusPreset, occupancyPercent);
    const updatedAt = raw.updatedAt ?? raw.timestamp ?? raw.lastUpdated;

    return {
      parkingNumber: raw.parkingNumber ?? raw.zone ?? fallbackParkingNumber,
      totalSpots: total ?? null,
      occupiedSpots: resolvedOccupied ?? null,
      freeSpots: resolvedFree ?? (total != null && resolvedOccupied != null ? Math.max(total - resolvedOccupied, 0) : null),
      occupancyPercent: occupancyPercent ?? null,
      statusPreset,
      humanStatus,
      updatedAtText: updatedAt ? formatDate(updatedAt) : '',
      updatedAtRelative: updatedAt ? formatRelativeTime(updatedAt) : '',
    };
  }

  function chooseStatusPreset(statusRaw, occupancyPercent) {
    if (statusRaw.includes('free') || statusRaw.includes('низ')) return 'low';
    if (statusRaw.includes('mid') || statusRaw.includes('сред')) return 'medium';
    if (statusRaw.includes('high') || statusRaw.includes('переполн') || statusRaw.includes('закры')) return 'high';

    if (typeof occupancyPercent === 'number') {
      if (occupancyPercent < 60) return 'low';
      if (occupancyPercent < 85) return 'medium';
      return 'high';
    }

    return 'unknown';
  }

  function formatHumanStatus(statusRaw, preset, percent) {
    if (statusRaw) return capitalize(statusRaw);
    switch (preset) {
      case 'low': return percent != null ? `Свободно · ${percent}% занято` : 'Парковка свободна';
      case 'medium': return percent != null ? `Плотная загрузка · ${percent}% занято` : 'Загрузка повышенная';
      case 'high': return percent != null ? `Переполнена · ${percent}% занято` : 'Свободных мест почти нет';
      default: return 'Статус будет указан после ответа сервера';
    }
  }

  function normalizePercent(value) {
    if (value == null) return null;
    if (typeof value === 'number' && Number.isFinite(value)) return clamp(Math.round(value <= 1 ? value * 100 : value), 0, 100);
    const numeric = parseFloat(String(value).replace(',', '.'));
    if (!Number.isNaN(numeric)) {
      const scaled = numeric <= 1 ? numeric * 100 : numeric;
      return clamp(Math.round(scaled), 0, 100);
    }
    return null;
  }

  function coerceNumber(value) {
    if (value == null) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function formatNumber(value, fallback = '') {
    if (value == null) return fallback;
    return new Intl.NumberFormat('ru-RU').format(value);
  }

  function formatDate(input) {
    const date = toDate(input);
    if (!date) return '';
    return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  function formatRelativeTime(input) {
    const date = toDate(input);
    if (!date) return '';
    const diffMs = Date.now() - date.getTime();
    const diffMinutes = Math.round(diffMs / 60000);
    if (diffMinutes < 1) return 'только что';
    if (diffMinutes < 60) return `${diffMinutes} мин назад`;
    const diffHours = Math.round(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} ч назад`;
    const diffDays = Math.round(diffHours / 24);
    return `${diffDays} дн назад`;
  }

  function toDate(value) {
    if (value instanceof Date) return value;
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function clamp(value, min, max) { return Math.min(Math.max(value, min), max); }
  function capitalize(text) { if (!text) return ''; return String(text).charAt(0).toUpperCase() + String(text).slice(1); }
  function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  }
  
async function get_park_on_coords(lat, lng, options = {}) {
  if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) {
    console.warn('Неверные координаты для поиска парковки:', lat, lng);
    return null;
  }

  const serverUrl = options.serverUrl ?? 'http://127.0.0.1:8001/parking/nearest';

  // Формируем координаты в строку "lat,lng"
  const coordsStr = `${lat},${lng}`;

  let responseData;
  try {
    const url = new URL(serverUrl);
    url.searchParams.append('coordinates', coordsStr);

    const resp = await fetch(url.toString(), { method: 'GET' });
    if (!resp.ok) {
      console.warn('Сервер вернул ошибку:', resp.status);
      return null;
    }

    responseData = await resp.json();
  } catch (err) {
    console.error('Ошибка запроса к серверу nearest:', err);
    return null;
  }

  if (!responseData || !responseData.parking) {
    console.warn('Сервер не вернул данные о парковке');
    return null;
  }

  const nearest = {
    id: responseData.parking.name, // или другой идентификатор, если есть
    name: responseData.parking.name,
    lat: Number(responseData.parking.coordinates.split(',')[0]),
    lng: Number(responseData.parking.coordinates.split(',')[1]),
    distance: responseData.parking.distance_to_request_m,
    raw: responseData.parking
  };

  // --- Маркер на карте ---
  if (typeof window.map !== 'undefined') {
    // Удаляем старый маркер
    if (window.__nearestParkingMarker) window.__nearestParkingMarker.remove();

    window.__nearestParkingMarker = new mapgl.Marker(window.map, {
      coordinates: [nearest.lng, nearest.lat],
      icon: options.iconUrl ?? 'https://docs.2gis.com/img/mapgl/marker.svg'
    });

    // Простое popup окно через DOM
    const popup = document.createElement('div');
    popup.className = 'dg-popup';
    popup.style.cssText = `
      position:absolute;
      background:#fff;
      border-radius:6px;
      padding:8px;
      box-shadow:0 4px 12px rgba(0,0,0,0.12);
      max-width:240px;
      font-size:12px;
      color:#333;
      display:none;
    `;
    popup.innerHTML = `<strong>${nearest.name}</strong><div>≈ ${Math.round(nearest.distance)} м</div>`;
    document.body.appendChild(popup);
    window.__nearestParkingPopup = popup;

    window.__nearestParkingMarker.on('click', () => {
      const pos = window.map.transform.lngLatToContainer([nearest.lng, nearest.lat]);
      popup.style.left = pos[0] + 'px';
      popup.style.top = (pos[1] - popup.offsetHeight - 10) + 'px';
      popup.style.display = 'block';
    });

    // Центрируем карту
    const curZoom = window.map.getZoom ? window.map.getZoom() : 12;
    window.map.setCenter([nearest.lng, nearest.lat], { duration: 600, easing: 'easeOutCubic' });
    window.map.setZoom(Math.max(curZoom + 2, 15), { duration: 600, easing: 'easeOutCubic' });
  }

  return nearest;
}



  // --- MapGL helpers: маркеры и обработка клика ---
  function addMarker(lat, lng, text = '') {
    if (!map) { console.warn('map не инициализирован'); return null; }
    const marker = new mapgl.Marker(map, {
      coordinates: [parseFloat(lng), parseFloat(lat)],
      icon: 'https://docs.2gis.com/img/mapgl/marker.svg',
    });
    if (text) {
      const popup = new mapgl.Popup(map, { coordinates: [parseFloat(lng), parseFloat(lat)], content: escapeHtml(text) });
      marker.on('click', () => popup.open());
    }
    markers.push(marker);
    return marker;
  }

  // Включаем отслеживание клика: при клике приближаем карту и вызываем get_park_on_coords(lat, lng)
  function enableClickToZoomAndQuery(mapInstance) {
    if (!mapInstance || typeof mapInstance.on !== 'function') {
      console.error('Неправильный объект карты передан в enableClickToZoomAndQuery');
      return;
    }

    let isAnimating = false;

    mapInstance.on('click', (e) => {
      let lng, lat;

      // MapGL event: e.lngLat или e.lngLat.toArray()
      if (e && e.lngLat && typeof e.lngLat.lng !== 'undefined') {
        lng = e.lngLat.lng;
        lat = e.lngLat.lat;
      } else if (e && Array.isArray(e.lngLat) && e.lngLat.length >= 2) {
        lng = e.lngLat[0];
        lat = e.lngLat[1];
      } else {
        console.error('Не удалось получить координаты клика из события', e);
        return;
      }

      if (isAnimating) return;
      isAnimating = true;

      const currentZoom = typeof mapInstance.getZoom === 'function' ? mapInstance.getZoom() : 12;
      const targetZoom = Math.min(currentZoom + 3, 18);

      // Анимированное центрирование и зум (MapGL поддерживает setCenter/setZoom с опциями)
      try {
        if (typeof mapInstance.setCenter === 'function') {
          mapInstance.setCenter([lng, lat], { easing: 'easeOutCubic', duration: 700 });
        }
        if (typeof mapInstance.setZoom === 'function') {
          mapInstance.setZoom(targetZoom, { easing: 'easeOutCubic', duration: 700 });
        }
      } catch (err) {
        console.warn('Ошибка анимации карты:', err);
      }

      // Вызов функции с координатами в порядке (lat, lng)
      get_park_on_coords(lat, lng);

      // Разрешаем следующий клик после окончания анимации
      setTimeout(() => { isAnimating = false; }, 800);
    });
  }

  // Включаем слушатель клика, если карта проинициализирована
  if (map) enableClickToZoomAndQuery(map);

  // Экспорт в window для удобства (при необходимости)
  window._parkingApp = {
    config: HACK_CONFIG,
    addMarker,
    requestStatus,
    normalizePayload,
    map,
  };
}); // DOMContentLoaded