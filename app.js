// Обновите путь, чтобы он указывал на ваш бэкенд.
const API_ENDPOINT = '/api/parking/load';
const REQUEST_METHOD = 'POST';

const form = document.getElementById('lookup-form');
const input = document.getElementById('parking-number');
const errorField = document.getElementById('lookup-error');
const card = document.getElementById('status-card');

const STATUS_PRESETS = {
  low: {
    label: 'Свободно',
    cssClass: 'status-card--success',
    emoji: '🟢',
  },
  medium: {
    label: 'Плотно',
    cssClass: 'status-card--warning',
    emoji: '🟡',
  },
  high: {
    label: 'Переполнено',
    cssClass: 'status-card--danger',
    emoji: '🔴',
  },
  unknown: {
    label: 'Нет данных',
    cssClass: 'status-card--warning',
    emoji: '⚪️',
  },
};

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearError();

  const rawValue = input.value.trim();
  if (!/^\d{3,}$/.test(rawValue)) {
    showError('Введите номер из минимум трёх цифр.');
    return;
  }

  await requestStatus(rawValue);
});

function showError(message) {
  errorField.textContent = message;
  errorField.hidden = false;
}

function clearError() {
  errorField.hidden = true;
  errorField.textContent = '';
}

async function requestStatus(parkingNumber) {
  toggleForm(false, 'Запрос…');
  renderLoading();

  try {
    const response = await fetch(API_ENDPOINT, {
      method: REQUEST_METHOD,
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ parkingNumber }),
    });

    if (!response.ok) {
      throw new Error(`Сервер вернул ${response.status}`);
    }

    const payload = await response.json();
    const normalized = normalizePayload(payload, parkingNumber);
    renderStatus(normalized);
  } catch (err) {
    console.error(err);
    renderErrorState(err);
  } finally {
    toggleForm(true);
  }
}

function toggleForm(isEnabled, loadingText) {
  input.disabled = !isEnabled;
  const submitButton = form.querySelector('.lookup__submit');
  submitButton.disabled = !isEnabled;
  if (!isEnabled) {
    submitButton.dataset.originalText = submitButton.textContent;
    submitButton.textContent = loadingText ?? 'Загрузка…';
  } else if (submitButton.dataset.originalText) {
    submitButton.textContent = submitButton.dataset.originalText;
    delete submitButton.dataset.originalText;
  }
}

function renderLoading() {
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
  card.innerHTML = `
    <div class="status-card status-card--danger">
      <div class="status-card__placeholder">
        <span class="status-card__emoji" aria-hidden="true">⚠️</span>
        <p class="status-card__text">${error.message || 'Не удалось получить данные. Попробуйте позже.'}</p>
      </div>
    </div>
  `;
}

function renderStatus(data) {
  const badge = STATUS_PRESETS[data.statusPreset] ?? STATUS_PRESETS.unknown;

  const statsHtml = [
    {
      label: 'Занято',
      value: formatNumber(data.occupiedSpots, '--'),
    },
    {
      label: 'Свободно',
      value: formatNumber(data.freeSpots, '--'),
    },
    {
      label: 'Всего мест',
      value: formatNumber(data.totalSpots, '--'),
    },
    {
      label: 'Загрузка',
      value: data.occupancyPercent != null ? `${data.occupancyPercent}%` : '--',
    },
  ]
    .filter((stat) => stat.value !== '--' || stat.label === 'Загрузка')
    .map(
      (stat) => `
        <div class="status-card__stat">
          <span class="status-card__stat-label">${stat.label}</span>
          <span class="status-card__stat-value">${stat.value}</span>
        </div>
      `,
    )
    .join('');

  card.innerHTML = `
    <div class="status-card ${badge.cssClass}">
      <div class="status-card__header">
        <div>
          <p class="status-card__badge">${badge.emoji} ${badge.label}</p>
          <h2 class="status-card__title">Парковка №${data.parkingNumber}</h2>
          <p class="status-card__subtitle">${data.humanStatus}</p>
        </div>
        <div class="status-card__meta">
          ${data.updatedAtText ? `<span class="status-card__meta-time">Обновлено: ${data.updatedAtText}</span>` : ''}
        </div>
      </div>

      <div class="status-card__progress" role="img" aria-label="Загруженность ${data.occupancyPercent ?? 'неизвестна'}%">
        <div class="status-card__progress-fill" style="width: ${Math.min(data.occupancyPercent ?? 0, 100)}%"></div>
      </div>

      <div class="status-card__stats">
        ${statsHtml}
      </div>

      <footer class="status-card__footer">
        ${data.updatedAtRelative ? `Актуальность: ${data.updatedAtRelative}` : 'Актуальность зависит от частоты обновлений API.'}
      </footer>
    </div>
  `;
}

function normalizePayload(payload, fallbackParkingNumber) {
  const raw = payload?.data ?? payload;

  if (!raw || typeof raw !== 'object') {
    throw new Error('Ответ сервера имеет неожиданный формат.');
  }

  const total = coerceNumber(
    raw.totalSpots ?? raw.total ?? raw.capacity ?? raw.maxCapacity,
  );
  const occupied = coerceNumber(
    raw.occupiedSpots ?? raw.occupied ?? raw.busy ?? raw.taken,
  );
  const free = coerceNumber(
    raw.freeSpots ?? raw.free ?? raw.available ?? raw.vacant,
  );

  let occupancyPercent = null;
  if (raw.occupancy != null) {
    occupancyPercent = normalizePercent(raw.occupancy);
  }
  if (occupancyPercent == null && raw.occupancyPercent != null) {
    occupancyPercent = normalizePercent(raw.occupancyPercent);
  }
  if (occupancyPercent == null && occupied != null && total != null && total > 0) {
    occupancyPercent = Math.round((occupied / total) * 100);
  }
  if (occupancyPercent == null && free != null && total != null && total > 0) {
    occupancyPercent = Math.round(((total - free) / total) * 100);
  }

  let resolvedOccupied = occupied;
  let resolvedFree = free;

  if (resolvedOccupied == null && total != null && free != null) {
    resolvedOccupied = Math.max(total - free, 0);
  }

  if (resolvedFree == null && total != null && occupied != null) {
    resolvedFree = Math.max(total - occupied, 0);
  }

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
  if (statusRaw) {
    return capitalize(statusRaw);
  }

  switch (preset) {
    case 'low':
      return percent != null ? `Свободно · ${percent}% занято` : 'Парковка свободна';
    case 'medium':
      return percent != null ? `Плотная загрузка · ${percent}% занято` : 'Загрузка повышенная';
    case 'high':
      return percent != null ? `Переполнена · ${percent}% занято` : 'Свободных мест почти нет';
    default:
      return 'Статус будет указан после ответа сервера';
  }
}

function normalizePercent(value) {
  if (value == null) return null;

  if (typeof value === 'number' && Number.isFinite(value)) {
    return clamp(Math.round(value <= 1 ? value * 100 : value), 0, 100);
  }

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
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
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

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function capitalize(text) {
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}
