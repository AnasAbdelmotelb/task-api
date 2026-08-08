# Task API

A simple REST API built with FastAPI for managing tasks.

## Features

- Get all tasks
- Get a task by ID
- Create a new task
- Update an existing task
- Delete a task
- Health check endpoint

## Technologies

- Python 3
- FastAPI
- Uvicorn
- Git

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd task-api
```

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate it:

**macOS/Linux**

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install fastapi uvicorn
```

## Running the API

```bash
uvicorn main:app --reload
```

The API will run at:

```
http://127.0.0.1:8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | / | API information |
| GET | /health | Health check |
| GET | /tasks | Get all tasks |
| GET | /tasks/{id} | Get a task by ID |
| POST | /tasks | Create a task |
| PUT | /tasks/{id} | Update a task |
| DELETE | /tasks/{id} | Delete a task |

## Example Request

```bash
curl http://127.0.0.1:8000/tasks
```

## Example Response

```json
[
  {
    "id": 1,
    "title": "Buy coffee",
    "done": true
  }
]
```

## Author

Anas Mansour