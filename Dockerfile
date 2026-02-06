FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение
COPY . .

# Создаем директорию для БД
RUN mkdir -p /data

# Переменные окружения
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Порт
EXPOSE 5000

# Запуск
CMD ["gunicorn", "--worker-class", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]

