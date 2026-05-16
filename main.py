import os
import html
import logging
from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import starlette.status as status
from pydantic import BaseModel, Field

import models
import database
import auth

# Настройка базового конфигуратора логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

app = FastAPI()

# Подключение фронтенд-интерфейса
static_path = os.path.join(os.getcwd(), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Инициализация таблиц БД
models.Base.metadata.create_all(bind=database.engine)


# --- СХЕМЫ ВАЛИДАЦИИ ДАННЫХ (PYDANTIC V2) ---

class UserRole(str, Enum):
    student = "student"
    teacher = "teacher"
    dean = "dean"

# ОСТАВЛЕН ТОЛЬКО ОДИН СТРОГИЙ КЛАСС ВАЛИДАЦИИ (Устранен дубликат-уязвимость)
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: UserRole  # Принимаются строго значения из Enum (student, teacher, dean)

class GradeCreate(BaseModel):
    student_id: int
    subject: str = Field(..., min_length=1, max_length=100)  # Защита от переполнения
    score: int = Field(..., ge=0, le=100)  # Валидация диапазона баллов


# --- MIDDLEWARE БЕЗОПАСНОСТИ ---

@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    # Ограничение размера любого входящего запроса до 512 КБ (Защита памяти от DoS)
    MAX_SIZE = 512 * 1024 
    content_length = request.headers.get('content-length')
    
    if content_length and int(content_length) > MAX_SIZE:
        logging.warning(f"SECURITY AUDIT: Заблокирован запрос, превышающий лимит размера ({content_length} байт) с IP: {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 
            detail="Запрос слишком большой. Лимит 512КБ."
        )
    return await call_next(request)


# --- API ЭНДПОИНТЫ ---

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    # Сценарий 1: Неуспешная попытка аутентификации (OWASP A07 / A09)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        safe_username = html.escape(form_data.username).replace("\n", "").replace("\r", "")
        logging.warning(f"SECURITY AUDIT: Неуспешная попытка входа. Скомпрометированный логин: {safe_username}")
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # Сценарий 2: Успешный вход в систему
    logging.info(f"SECURITY AUDIT: Успешный вход в систему. Пользователь: {user.username}, Роль: {user.role}")
    return {"access_token": auth.create_access_token(data={"sub": user.username}), "token_type": "bearer"}


@app.post("/register/")
def register(user_in: UserCreate, db: Session = Depends(database.get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user_in.username).first()
    
    if existing_user:
        logging.warning(f"SECURITY AUDIT: Попытка повторной регистрации существующего имени: {user_in.username}")
        raise HTTPException(status_code=400, detail="Registration failed. Please contact support.")
    
    hashed_pwd = auth.get_password_hash(user_in.password)
    new_user = models.User(username=user_in.username, hashed_password=hashed_pwd, role=user_in.role.value)
    db.add(new_user)
    db.commit()

    safe_name = html.escape(user_in.username).replace("\n", "").replace("\r", "")
    # Логирование изменения прав/создания субъекта доступа
    logging.info(f"SECURITY AUDIT: Создан новый пользователь/назначены права. Логин: {safe_name}, Роль: {user_in.role.value}")
    
    return {"msg": "User created successfully"}


@app.post("/grades/")
def add_grade(grade_in: GradeCreate, 
              db: Session = Depends(database.get_db), 
              current_user: models.User = Depends(auth.get_current_user)):
    
    # Нарушение контроля доступа (Неуспешная попытка изменения сущности — OWASP A01)
    if current_user.role not in ["teacher", "dean"]:
        logging.warning(f"SECURITY AUDIT: ОТКАЗ В ДОСТУПЕ. Пользователь {current_user.username} (роль: {current_user.role}) пытался несанкционированно выставить оценку студенту ID {grade_in.student_id}")
        raise HTTPException(status_code=403, detail="Только преподаватели могут выставлять оценки")

    # Успешное изменение критичной сущности (OWASP A03 - Очистка ввода от XSS)
    safe_subject = html.escape(grade_in.subject)
    new_grade = models.Grade(
        student_id=grade_in.student_id, 
        subject=safe_subject, 
        score=grade_in.score
    )
    db.add(new_grade)
    db.commit()
    
    logging.info(f"SECURITY AUDIT: Изменение критичной сущности (Успеваемость). Преподаватель {current_user.username} выставил оценку {grade_in.score} студенту ID {grade_in.student_id} по предмету {safe_subject}")
    return {"msg": "Grade added successfully"}


@app.get("/grades/")
def get_all_grades(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    # Разграничение прав доступа (OWASP A01: Broken Access Control)
    if current_user.role in ["teacher", "dean"]:
        grades = db.query(models.Grade).all()
    else:
        # Контроль доступа на уровне записей для студентов
        try:
            student_id_int = int(current_user.username)
            grades = db.query(models.Grade).filter(models.Grade.student_id == student_id_int).all()
        except ValueError:
            logging.warning(f"SECURITY AUDIT: Пользователь {current_user.username} с нечисловым логином роли 'student' пытался запросить оценки.")
            grades = []

    # Логирование чтения критичных данных (OWASP A09)
    logging.info(f"SECURITY AUDIT: Пользователь {current_user.username} (роль: {current_user.role}) успешно запросил ведомость оценок. Возвращено записей: {len(grades)}")
    return grades