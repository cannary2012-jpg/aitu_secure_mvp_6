from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import models, database, auth, logging
import html
from pydantic import Field
from fastapi import Request, HTTPException
import starlette.status as status
from enum import Enum
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

static_path = os.path.join(os.getcwd(), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Allowlist-валидация ролей (Задание 2) 
class UserRole(str, Enum):
    student = "student"
    teacher = "teacher"
    dean = "dean"

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50) # Нормализация длины 
    password: str = Field(..., min_length=8)
    role: UserRole # Теперь принимаются ТОЛЬКО значения из Enum

class GradeCreate(BaseModel):
    student_id: int
    # Защита от переполнения буфера памяти: ограничение длины строки 
    subject: str = Field(..., min_length=1, max_length=100) 
    # Валидация диапазона значений 
    score: int = Field(..., ge=0, le=100)

models.Base.metadata.create_all(bind=database.engine)

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    # Ограничиваем размер любого запроса до 512 КБ
    MAX_SIZE = 512 * 1024 
    content_length = request.headers.get('content-length')
    
    if content_length and int(content_length) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 
            detail="Запрос слишком большой. Лимит 512КБ."
        )
    return await call_next(request)

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": auth.create_access_token(data={"sub": user.username}), "token_type": "bearer"}

@app.post("/register/")
def register(user_in: UserCreate, db: Session = Depends(database.get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user_in.username).first()
    if existing_user:
        # Удали отсюда:
        raise HTTPException(status_code=400, detail="Registration failed. Please contact support.")
    
    hashed_pwd = auth.get_password_hash(user_in.password)
    new_user = models.User(username=user_in.username, hashed_password=hashed_pwd, role=user_in.role)
    db.add(new_user)
    db.commit()

    # И отсюда тоже удали:
    safe_name = html.escape(user_in.username).replace("\n", "").replace("\r", "")
    logging.info(f"Доверительная граница пройдена: создан пользователь {safe_name}")
    
    return {"msg": "User created successfully"}

@app.post("/grades/")
def add_grade(grade_in: GradeCreate, 
              db: Session = Depends(database.get_db), 
              current_user: models.User = Depends(auth.get_current_user)):
    
    # 1. Проверка роли (Авторизация на уровне действия)
    if current_user.role not in ["teacher", "dean"]:
        logging.warning(f"Отказ в доступе: пользователь {current_user.username} пытался выставить оценку")
        raise HTTPException(status_code=403, detail="Только преподаватели могут выставлять оценки")

    # 2. Объектная привязка (Обоснование принятых мер)
    # Здесь можно добавить проверку: привязан ли этот преподаватель к данному предмету
    
    safe_subject = html.escape(grade_in.subject)
    new_grade = models.Grade(
        student_id=grade_in.student_id, 
        subject=safe_subject, 
        score=grade_in.score,
    #    teacher_id=current_user.id  # Фиксируем, КТО именно поставил оценку
    )
    db.add(new_grade)
    db.commit()
    logging.info(f"Оценка выставлена преподавателем {current_user.username} для студента ID {grade_in.student_id}")
    return {"msg": "Grade added successfully"}

@app.get("/grades/")
def get_all_grades(
    db: Session = Depends(database.get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    # Разграничение прав (OWASP A01: Broken Access Control)
    # Преподаватели и Декан могут видеть все оценки, а Студент — только свои
    if current_user.role in ["teacher", "dean"]:
        grades = db.query(models.Grade).all()
    else:
        # Пытаемся сопоставить username студента с его student_id (если они совпадают)
        # Или, если в системе это не связано, студент видит пустой список или ошибку.
        # Для простоты проверки сделаем, чтобы декан видел всё, а иначе фильтровалось:
        try:
            student_id_int = int(current_user.username)
            grades = db.query(models.Grade).filter(models.Grade.student_id == student_id_int).all()
        except ValueError:
            grades = [] # Если логин не числовой, студент ничего не увидит из соображений приватности

    # Логируем успешное чтение данных (OWASP A09: Logging Failure)
    logging.info(f"Пользователь {current_user.username} (роль: {current_user.role}) запросил список оценок")
    return grades