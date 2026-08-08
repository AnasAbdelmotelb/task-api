from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# -----------------------------
# Data Model
# -----------------------------
class Task(BaseModel):
    title: str
    done: bool = False


tasks = [
    {"id": 1, "title": "Buy milk", "done": False},
    {"id": 2, "title": "Learn FastAPI", "done": True},
    {"id": 3, "title": "Finish internship assignment", "done": False},
]

# -----------------------------
# Root
# -----------------------------
@app.get("/")
def root():
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": [
            "/tasks",
            "/tasks/{id}",
            "/health"
        ]
    }

# -----------------------------
# Health Check
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -----------------------------
# Get All Tasks
# -----------------------------
@app.get("/tasks")
def get_tasks():
    return tasks

# -----------------------------
# Get One Task
# -----------------------------
@app.get("/tasks/{task_id}")
def get_task(task_id: int):

    for task in tasks:
        if task["id"] == task_id:
            return task

    return JSONResponse(
        status_code=404,
        content={"error": f"Task {task_id} not found"}
    )

# -----------------------------
# Create Task
# -----------------------------
@app.post("/tasks")
def create_task(task: Task):

    new_task = {
        "id": len(tasks) + 1,
        "title": task.title,
        "done": task.done
    }

    tasks.append(new_task)

    return new_task

# -----------------------------
# Update Task
# -----------------------------
@app.put("/tasks/{task_id}")
def update_task(task_id: int, updated: Task):

    for task in tasks:

        if task["id"] == task_id:
            task["title"] = updated.title
            task["done"] = updated.done
            return task

    return JSONResponse(
        status_code=404,
        content={"error": "Task not found"}
    )

# -----------------------------
# Delete Task
# -----------------------------
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):

    for task in tasks:

        if task["id"] == task_id:
            tasks.remove(task)
            return {"message": "Task deleted"}

    return JSONResponse(
        status_code=404,
        content={"error": "Task not found"}
    )