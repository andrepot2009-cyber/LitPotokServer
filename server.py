from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import sqlite3
import bcrypt  # Добавили прямой импорт bcrypt

app = FastAPI(title="LitPotok API")
DB_NAME = "litpotok_server.db"
SECRET_KEY = "litpotok-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# --- Исправленные функции для работы с паролями ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt проверяет соответствие пароля и хеша
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    # Генерируем соль и создаем хеш
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS works (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        author_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(author_id) REFERENCES users(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(work_id) REFERENCES works(id)
    )""")
    conn.commit()
    conn.close()

init_db()

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str

class WorkCreate(BaseModel):
    title: str
    content: str

class FeedbackCreate(BaseModel):
    work_id: int
    category: str
    text: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)

@app.post("/auth/register")
def register(user: UserCreate):
    db = get_db()
    if db.execute("SELECT id FROM users WHERE username = ?", (user.username,)).fetchone():
        db.close()
        raise HTTPException(status_code=400, detail="Логин уже занят")
    hashed_pw = get_password_hash(user.password)
    db.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
               (user.username, hashed_pw, user.role, datetime.now().strftime("%d.%m.%Y %H:%M")))
    db.commit()
    db.close()
    return {"message": "Аккаунт создан"}

@app.post("/auth/login")
def login(user: UserLogin):
    db = get_db()
    db_user = db.execute("SELECT * FROM users WHERE username = ?", (user.username,)).fetchone()
    db.close()
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    access_token = create_access_token(data={"sub": db_user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/works")
def get_works(current_user: dict = Depends(get_current_user)):
    db = get_db()
    if current_user["role"] == "writer":
        rows = db.execute("SELECT w.id, w.title, w.created_at, u.username as author FROM works w JOIN users u ON w.author_id = u.id WHERE w.author_id = ?", (current_user["id"],)).fetchall()
    else:
        rows = db.execute("SELECT w.id, w.title, w.created_at, u.username as author FROM works w JOIN users u ON w.author_id = u.id").fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/works/{work_id}")
def get_work(work_id: int, current_user: dict = Depends(get_current_user)):
    db = get_db()
    row = db.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)

@app.post("/works")
def create_work(work: WorkCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "writer":
        raise HTTPException(status_code=403, detail="Writers only")
    db = get_db()
    cursor = db.execute("INSERT INTO works (title, content, author_id, created_at) VALUES (?, ?, ?, ?)",
                        (work.title, work.content, current_user["id"], datetime.now().strftime("%d.%m.%Y %H:%M")))
    db.commit()
    last_id = cursor.lastrowid
    db.close()
    return {"id": last_id}

@app.get("/feedback/{work_id}")
def get_feedback(work_id: int, current_user: dict = Depends(get_current_user)):
    db = get_db()
    rows = db.execute("SELECT f.category, f.text, f.created_at, u.username as reviewer FROM feedback f JOIN users u ON f.user_id = u.id WHERE f.work_id = ?", (work_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/feedback")
def add_feedback(fb: FeedbackCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "reader":
        raise HTTPException(status_code=403, detail="Readers only")
    db = get_db()
    db.execute("INSERT INTO feedback (work_id, user_id, category, text, created_at) VALUES (?, ?, ?, ?, ?)",
               (fb.work_id, current_user["id"], fb.category, fb.text, datetime.now().strftime("%d.%m.%Y %H:%M")))
    db.commit()
    db.close()
    return {"message": "OK"}