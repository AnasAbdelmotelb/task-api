import sqlite3
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Task API",
    description="A simple REST API for managing tasks",
    version="1.0.0"
)


class Task(BaseModel):
    title: str
    done: bool = False


def init_db():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done BOOLEAN NOT NULL DEFAULT 0
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]

    if count == 0:
        example_tasks = [
            ("Buy milk", 0),
            ("Learn FastAPI", 1),
            ("Finish internship assignment", 0),
        ]

        cursor.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            example_tasks
        )

    conn.commit()
    conn.close()


init_db()


@app.get("/")
def root():
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/tasks"]
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.get("/tasks")
def get_tasks():
    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (task_id,)
    )
    row = cursor.fetchone()

    conn.close()

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Task {task_id} not found"}
        )

    return dict(row)


@app.post("/tasks", status_code=201)
def create_task(task: Task):
    if not task.title.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Title is required"}
        )

    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (task.title, int(task.done))
    )

    task_id = cursor.lastrowid
    conn.commit()

    cursor.execute(
        "SELECT * FROM tasks WHERE id = ?",
        (task_id,)
    )
    row = cursor.fetchone()

    conn.close()

    return dict(row)


@app.put("/tasks/{task_id}")
def update_task(task_id: int, updated_task: Task):
    for task in tasks:
        if task["id"] == task_id:
            task["title"] = updated_task.title
            task["done"] = updated_task.done
            return task

    return JSONResponse(
        status_code=404,
        content={"error": f"Task {task_id} not found"}
    )


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            tasks.remove(task)
            return {"message": "Task deleted"}

    return JSONResponse(
        status_code=404,
        content={"error": f"Task {task_id} not found"}
    )