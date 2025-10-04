import math

import math

def estimate_parking_occupancy(cost, distance, spots):
    """
    Оценивает загруженность парковки (0-1) на основе параметров.
    Использует непрерывные математические функции для моделирования реальных зависимостей.
    """
    # 1. Моделирование влияния расстояния (экспоненциальное затухание)
    # Чем ближе к центру, тем выше загруженность
    distance_factor = math.exp(-distance / 2.0)  # Полураспад на 2 км
    
    # 2. Моделирование влияния цены (логистическая функция)
    # Бесплатные парковки почти всегда заняты, с ростом цены загруженность падает
    price_factor = 1.0 / (1.0 + math.exp((cost - 100) / 50))  # Переход вокруг 100 руб
    
    # 3. Моделирование влияния количества мест (логарифмическое)
    # Больше мест = ниже вероятность что конкретное место занято
    spots_factor = 1.0 / (1.0 + math.log(1 + spots) / 3.0)
    
    # 4. Базовый уровень загруженности для центра города
    base_demand = 0.85
    
    # 5. Комбинируем факторы с весами, отражающими их важность
    # Расстояние наиболее важно, затем цена, затем количество мест
    probability = (
        base_demand * 0.5 + 
        distance_factor * 0.3 + 
        price_factor * 0.15 + 
        spots_factor * 0.05
    )
    
    # 6. Нелинейная корректировка для крайних случаев
    # Бесплатные парковки в центре должны быть почти всегда заняты
    if cost == 0 and distance <= 1.0:
        probability = max(probability, 0.9 - distance * 0.2)
    
    # Очень дорогие парковки должны быть почти всегда пусты
    if cost > 500:
        probability = min(probability, 0.3 * (1 - cost / 2000))
    
    # 7. Гарантируем разумные границы
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

from flask import Flask, request, jsonify

app = Flask(__name__)

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
        else:
            # Для POST запроса - параметры в JSON теле
            data = request.get_json()
            cost = float(data.get('cost'))
            distance = float(data.get('distance'))
            spots = int(data.get('spots'))
        
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
        probability = estimate_parking_occupancy(cost, distance, spots)
        
        # Формирование ответа
        response = {
            'occupancy_probability': probability,
            'occupancy_percentage': round(probability * 100, 1),
            'parameters': {
                'cost': cost,
                'distance': distance,
                'spots': spots
            },
            'occupancy_level': get_occupancy_level(probability)
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

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Эндпоинт для проверки работоспособности сервиса
    """
    return jsonify({'status': 'healthy', 'service': 'parking_occupancy_api'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)