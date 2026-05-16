import database, models, auth
import random

def seed():
    models.Base.metadata.create_all(bind=database.engine)
    db = database.SessionLocal()
    try:
        # Создаем начального пользователя (Преподаватель)
        pwd = auth.get_password_hash("Astana2026!")
        if not db.query(models.User).filter_by(username="teacher_admin").first():
            teacher = models.User(username="teacher_admin", hashed_password=pwd, role="dean")
            db.add(teacher)
            db.commit()
        
        # Генерируем 200 записей оценок (БЕЗ teacher_id)
        subjects = ["Cybersecurity", "Network Security", "Cloud Systems", "Secure SDLC"]
        for _ in range(200):
            grade = models.Grade(
                student_id=random.randint(100000, 999999),
                subject=random.choice(subjects),
                score=random.randint(50, 100)
                # УДАЛИЛИ СТРОКУ С teacher_id ЗДЕСЬ
            )
            db.add(grade)
        db.commit()
        print("--- БАЗА УСПЕШНО НАПОЛНЕНА: 200+ СТРОК ---")
    finally:
        db.close()

if __name__ == "__main__":
    seed()