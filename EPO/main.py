from flask import Flask, request, jsonify
import math
from datetime import datetime

app = Flask(__name__)

def estimate_parking_occupancy(cost, distance, spots, hour=None):
    """
    Оценивает загруженность парковки (0-1) на основе параметров.
    """
    # 1. Моделирование влияния расстояния
    distance_factor = math.exp(-distance / 2.0)
    
    # 2. Моделирование влияния цены
    price_factor = 1.0 / (1.0 + math.exp((cost - 100) / 50))
    
    # 3. Моделирование влияния количества мест
    spots_factor = 1.0 / (1.0 + math.log(1 + spots) / 3.0)
    
    # 4. Моделирование временного фактора
    if hour is not None:
        normalized_hour = (hour + 1) % 24
        time_factor = 0.3 + 0.7 * math.exp(-((normalized_hour - 13) ** 2) / 8.0)
    else:
        time_factor = 0.65
    
    # 5. Базовый уровень загруженности
    base_demand = 0.85
    
    # 6. Комбинируем факторы
    probability = (
        base_demand * 0.4 + 
        distance_factor * 0.25 + 
        price_factor * 0.15 + 
        spots_factor * 0.05 +
        time_factor * 0.15
    )
    
    # 7. Корректировка для крайних случаев
    if cost == 0 and distance <= 1.0:
        probability = max(probability, 0.9 - distance * 0.2)
    
    if cost > 500:
        probability = min(probability, 0.3 * (1 - cost / 2000))
    
    # 8. Гарантируем разумные границы
    probability = max(0.05, min(0.95, probability))
    
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

@app.route('/api/parking/occupancy', methods=['GET', 'POST'])
def parking_occupancy():
    """
    Эндпоинт для расчёта загруженности парковки
    """
    try:
        if request.method == 'GET':
            # Для GET запроса - параметры в query string
            cost = float(request.args.get('cost'))
            distance = float(request.args.get('distance'))
            spots = int(request.args.get('spots'))
            hour_str = request.args.get('hour')
        else:
            # Для POST запроса - параметры в JSON теле
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
            # Если время не указано, используем текущий час
            hour = datetime.now().hour
        
        # Проверка обязательных параметров
        if cost is None or distance is None or spots is None:
            return jsonify({
                'error': 'Missing required parameters: cost, distance, spots'
            }), 400
        
        # Проверка на положительные значения
        if cost < 0 or distance < 0 or spots <= 0:
            return jsonify({
                'error': 'Parameters must be positive values'
            }), 400
        
        # Расчёт вероятности
        probability = estimate_parking_occupancy(cost, distance, spots, hour)
        
        # Формирование ответа
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
    
    except ValueError as e:
        return jsonify({
            'error': 'Invalid parameter types. Cost and distance should be numbers, spots should be integer'
        }), 400
    except Exception as e:
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

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

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Эндпоинт для проверки работоспособности сервиса
    """
    return jsonify({'status': 'healthy', 'service': 'parking_occupancy_api'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)