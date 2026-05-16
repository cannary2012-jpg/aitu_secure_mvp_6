# 1. Используем официальный легкий образ Python
FROM python:3.12-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR C:\Users\Abulkhair\Desktop\Магистратура\invest\aitu_mvp_9

# 3. Копируем файл зависимостей
COPY requirements.txt .

# 4. Устанавливаем библиотеки (Secure Supply Chain: фиксируем зависимости)
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем все файлы проекта (main.py, auth.py и т.д.) в контейнер
COPY . .

# 6. Открываем порт 8000 для внешнего доступа
EXPOSE 8000

# 7. Команда для запуска сервера
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Проверка: создаем папку если ее нет (на всякий случай)
RUN mkdir -p static
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]