# Парковочный сервис

Веб-приложение на базе FastAPI, Flask и Go ищет ближайшие парковки по данным 2ГИС и показывает оценку загруженности (EPO). Фронтенд отображает карту, карточку парковки и прогноз заполненности.

## Настройка окружения

Заполните:

### `parser/.env`
```env
DGIS_API_KEY=ваш_ключ_2gis
DEFAULT_RADIUS=600
DEFAULT_LIMIT=10
CENTER_COORDINATES=55.7558, 37.6173
AUTO_PRICE_BY_DISTANCE=1
```

### `EPO/.env`
```env
DEBUG=false
PORT=5000
GUNICORN_WORKERS=4
GUNICORN_TIMEOUT=120
```

При необходимости скорректируйте значения и параметры в `docker-compose.yml`.

## Запуск

```bash
docker compose up --build
```

После сборки и старта сервис доступен по адресу `http://localhost:12300`.
