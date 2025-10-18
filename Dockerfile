FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Скопировать весь проект
COPY . .

# Установить зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Добавляем путь для корректного импорта
ENV PYTHONPATH=/app

# Настройки порта и режима вывода
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Запуск приложения
CMD ["python", "backend/main.py"]
