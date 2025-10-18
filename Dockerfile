FROM python:3.11-slim

WORKDIR /app

# зависимости в корне
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код
COPY backend ./backend
COPY frontend ./frontend

# Railway передаст PORT; main.py его прочитает
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "backend.main"]
