# server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime
from typing import Optional

app = FastAPI(title="ЛитПоток API")
DB_NAME = "litpotok_server.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS works (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(work_id) REFERENCES works(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

class WorkCreate(BaseModel):
    title: str
    author: str
    content: str

class FeedbackCreate(BaseModel):
    work_id: int
    category: str
    text: str

@app.get("/works")
def get_works():
    conn = get_db()
    rows = conn.execute("SELECT id, title, author, created_at FROM works ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"id": r["id"], "title": r["title"], "author": r["author"], "created_at": r["created_at"]} for r in rows]

@app.get("/works/{work_id}")
def get_work(work_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Произведение не найдено")
    return dict(row)

@app.post("/works")
def create_work(work: WorkCreate):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO works (title, author, content, created_at) VALUES (?, ?, ?, ?)",
        (work.title, work.author, work.content, datetime.now().strftime("%d.%m.%Y %H:%M"))
    )
    conn.commit()
    conn.close()
    return {"message": "Произведение добавлено", "id": cursor.lastrowid}

@app.get("/feedback/{work_id}")
def get_feedback(work_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT category, text, created_at FROM feedback WHERE work_id = ? ORDER BY created_at DESC",
        (work_id,)
    ).fetchall()
    conn.close()
    return [{"category": r["category"], "text": r["text"], "created_at": r["created_at"]} for r in rows]

@app.post("/feedback")
def add_feedback(fb: FeedbackCreate):
    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (work_id, category, text, created_at) VALUES (?, ?, ?, ?)",
        (fb.work_id, fb.category, fb.text, datetime.now().strftime("%d.%m.%Y %H:%M"))
    )
    conn.commit()
    conn.close()
    return {"message": "Отзыв добавлен"}