import os

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from fastapi import FastAPI, Response, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel


# --------------------------------------------------
# Environment / Database configuration
# --------------------------------------------------

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="Task API",
    description="A simple REST API for managing tasks",
    version="1.0.0"
)


# --------------------------------------------------
# Validation error handling
# --------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    return JSONResponse(
        status_code=400,
        content={"error": "Invalid request data"}
    )


# --------------------------------------------------
# Models
# --------------------------------------------------

class Task(BaseModel):
    title: str
    done: bool = False


# --------------------------------------------------
# Database initialization
# --------------------------------------------------

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    done BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)

            cursor.execute(
                "SELECT COUNT(*) AS count FROM tasks"
            )

            count = cursor.fetchone()["count"]

            if count == 0:
                example_tasks = [
                    ("Buy milk", False),
                    ("Learn FastAPI", True),
                    ("Finish internship assignment", False),
                ]

                cursor.executemany(
                    """
                    INSERT INTO tasks (title, done)
                    VALUES (%s, %s)
                    """,
                    example_tasks
                )


init_db()


# --------------------------------------------------
# Root
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Task API",
        "version": "1.0",
        "database": "PostgreSQL",
        "endpoints": ["/tasks"]
    }


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# --------------------------------------------------
# GET all tasks
#
# Optional:
# /tasks?search=milk
# /tasks?done=true
# /tasks?search=fast&done=true
#
# Results are sorted alphabetically.
# --------------------------------------------------

@app.get("/tasks")
def get_tasks(
    search: str = None,
    done: bool = None
):
    with get_connection() as conn:
        with conn.cursor() as cursor:

            if search and done is not None:

                cursor.execute(
                    """
                    SELECT id, title, done
                    FROM tasks
                    WHERE title ILIKE %s
                    AND done = %s
                    ORDER BY title
                    """,
                    (
                        f"%{search}%",
                        done
                    )
                )

            elif search:

                cursor.execute(
                    """
                    SELECT id, title, done
                    FROM tasks
                    WHERE title ILIKE %s
                    ORDER BY title
                    """,
                    (
                        f"%{search}%",
                    )
                )

            elif done is not None:

                cursor.execute(
                    """
                    SELECT id, title, done
                    FROM tasks
                    WHERE done = %s
                    ORDER BY title
                    """,
                    (
                        done,
                    )
                )

            else:

                cursor.execute(
                    """
                    SELECT id, title, done
                    FROM tasks
                    ORDER BY title
                    """
                )

            rows = cursor.fetchall()

            return rows


# --------------------------------------------------
# GET one task
# --------------------------------------------------

@app.get("/tasks/{task_id}")
def get_task(task_id: int):

    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT id, title, done
                FROM tasks
                WHERE id = %s
                """,
                (
                    task_id,
                )
            )

            row = cursor.fetchone()

            if row is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Task {task_id} not found"
                    }
                )

            return row


# --------------------------------------------------
# CREATE task
# --------------------------------------------------

@app.post(
    "/tasks",
    status_code=201
)
def create_task(task: Task):

    if not task.title.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": "Title is required"
            }
        )

    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO tasks (title, done)
                VALUES (%s, %s)
                RETURNING id, title, done
                """,
                (
                    task.title,
                    task.done
                )
            )

            new_task = cursor.fetchone()

            return new_task


# --------------------------------------------------
# UPDATE task
# --------------------------------------------------

@app.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    updated_task: Task
):

    if not updated_task.title.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": "Title is required"
            }
        )

    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                UPDATE tasks
                SET title = %s,
                    done = %s
                WHERE id = %s
                RETURNING id, title, done
                """,
                (
                    updated_task.title,
                    updated_task.done,
                    task_id
                )
            )

            row = cursor.fetchone()

            if row is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Task {task_id} not found"
                    }
                )

            return row


# --------------------------------------------------
# DELETE task
# --------------------------------------------------

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):

    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                DELETE FROM tasks
                WHERE id = %s
                RETURNING id
                """,
                (
                    task_id,
                )
            )

            deleted_task = cursor.fetchone()

            if deleted_task is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": f"Task {task_id} not found"
                    }
                )

    return Response(status_code=204)


# --------------------------------------------------
# Statistics
# --------------------------------------------------

@app.get("/stats")
def get_stats():

    with get_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE done = TRUE
                    ) AS completed,
                    COUNT(*) FILTER (
                        WHERE done = FALSE
                    ) AS pending
                FROM tasks
                """
            )

            stats = cursor.fetchone()

            return stats
