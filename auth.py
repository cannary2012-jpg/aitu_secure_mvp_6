import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import models, database
from jose import JWTError

# Эти константы должны быть определены вверху файла
# Мы используем os.getenv для защиты (Задание 1 & 2)
SECRET_KEY = os.getenv("SECRET_KEY", "AITU_SUPER_SECRET_KEY_2026") 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# SECRET_KEY = "AITU_SUPER_SECRET_KEY_2026"
#ALGORITHM = "HS256"
#ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Используем pbkdf2_sha256, чтобы избежать ошибки про 72 байта
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user = db.query(models.User).filter(models.User.username == username).first()
        if user is None: raise HTTPException(status_code=401)
        return user
   # except:
   #     raise HTTPException(status_code=401, detail="Could not validate credentials")
    except JWTError:
      raise HTTPException(status_code=401, detail="Invalid token signature or expired")
    except Exception as e:
        logging.error(f"Unexpected error during auth: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")