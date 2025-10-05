from flask import Flask, request, jsonify
import math
from datetime import datetime, timezone, timedelta
import os

app = Flask(__name__)

# Отключаем debug в продакшене
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

def estimate_parking_occupancy(cost, distance, spots, hour=None):
    """Оценивает загруженность парковки (0-1) на основе параметров."""

    # 1. Близость к центру: чем ближе, тем сильнее спрос
    distance_factor = 0.45 + 0.55 * math.exp(-max(distance, 0.0) / 0.8)

    # 2. Стоимость: дорогие парковки чуть менее привлекательны, но не критично
    baseline_cost = 300.0
    effective_cost = max(cost - baseline_cost, 0.0)
    price_factor = 0.74 + 0.26 * math.exp(-effective_cost / 1000.0)

    # 3. Количество мест: маленькие парковки быстрее заполняются
    spots_factor = 0.6 + 0.4 * math.exp(-max(spots, 1) / 120.0)

    # 4. Временной фактор
    if hour is not None:
        normalized_hour = int(hour) % 24
        time_factor = 0.4 + 0.6 * math.exp(-((normalized_hour - 13) ** 2) / 16.0)
    else:
        time_factor = 0.65

    # 5. Базовый спрос
    base_demand = 0.67

    # 6. Комбинация факторов
    probability = (
        base_demand * 0.2
        + distance_factor * 0.3
        + price_factor * 0.23
        + spots_factor * 0.12
        + time_factor * 0.15
    )

    # 7. Дополнительная корректировка для парковок в центре
    if distance <= 0.8:
        boost = 0.16 * (0.8 - distance) / 0.8
        probability = max(probability, 0.88 + boost)

    if cost <= 0 and distance <= 1.0:
        probability = max(probability, 0.9 - distance * 0.15)

    # 8. Финальные границы
    probability = max(0.05, min(0.995, probability))

    return round(probability, 3)

def get_occupancy_level(probability):
    """
    Определяет уровень загруженности по вероятности
    """
    if probability < 0.2:
        return "очень низкая"
    elif probability < 0.4:
        return "низкая"
    elif probability < 0.6:
        return "средняя"
    elif probability < 0.8:
        return "высокая"
    else:
        return "очень высокая"

def get_time_context(hour):
    """
    Возвращает контекстное описание времени суток
    """
    if 0 <= hour < 6:
        return "ночь (минимум загруженности)"
    elif 6 <= hour < 10:
        return "утро (растущая загруженность)"
    elif 10 <= hour < 14:
        return "обеденное время (пик загруженности)"
    elif 14 <= hour < 18:
        return "день (высокая загруженность)"
    elif 18 <= hour < 22:
        return "вечер (спадающая загруженность)"
    else:
        return "поздний вечер (низкая загруженность)"

@app.route('/api/parking/occupancy', methods=['GET', 'POST'])
def parking_occupancy():
    """
    Эндпоинт для расчёта загруженности парковки
    """
    try:
        if request.method == 'GET':
            cost = float(request.args.get('cost'))
            distance = float(request.args.get('distance'))
            spots = int(request.args.get('spots'))
            hour_str = request.args.get('hour')
        else:
            data = request.get_json()
            cost = float(data.get('cost'))
            distance = float(data.get('distance'))
            spots = int(data.get('spots'))
            hour_str = data.get('hour')
        
        # Обработка параметра времени
        if hour_str is not None:
            try:
                hour = int(hour_str)
                if hour < 0 or hour > 23:
                    return jsonify({
                        'error': 'Hour must be between 0 and 23'
                    }), 400
            except ValueError:
                return jsonify({
                    'error': 'Hour must be an integer between 0 and 23'
                }), 400
        else:
            moscow_tz = timezone(timedelta(hours=3))
            hour = datetime.now(moscow_tz).hour
        
        # Валидация
        if cost < 0 or distance < 0 or spots <= 0:
            return jsonify({
                'error': 'Parameters must be positive values'
            }), 400
        
        # Расчёт
        probability = estimate_parking_occupancy(cost, distance, spots, hour)
        
        # Ответ
        response = {
            'occupancy_probability': probability,
            'occupancy_percentage': round(probability * 100, 1),
            'parameters': {
                'cost': cost,
                'distance': distance,
                'spots': spots,
                'hour': hour
            },
            'occupancy_level': get_occupancy_level(probability),
            'time_context': get_time_context(hour)
        }
        
        return jsonify(response)
    
    except (ValueError, TypeError):
        return jsonify({
            'error': 'Invalid parameter types. Cost and distance should be numbers, spots should be integer'
        }), 400
    except Exception as e:
        app.logger.error(f"Error: {str(e)}")
        return jsonify({
            'error': 'Internal server error'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'service': 'parking_occupancy_api'})

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'message': 'Parking Occupancy API',
        'version': '1.0.0',
        'endpoints': {
            'occupancy': '/api/parking/occupancy',
            'health': '/api/health'
        }
    })

# Запуск через python (только для разработки)
if __name__ == '__main__':
    app.run(debug=DEBUG, host='0.0.0.0', port=5000)
