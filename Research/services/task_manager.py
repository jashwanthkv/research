import uuid
import threading

# In-memory task store (for now)
_TASKS = {}
_LOCK = threading.Lock()

# Fixed pipeline steps
PIPELINE_STEPS = ["decision", "retrieve","continuous_explanation", "fetch", "analyse", "explain"]

def create_task(query: str):
    task_id = str(uuid.uuid4())

    with _LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "query": query,
            "mode": None,
            "status": "running",
            "progress": [
                {"step": step, "state": "pending"}
                for step in PIPELINE_STEPS
            ],
            "papers": [],
            "logs": [],
            "result": None
        }

    return task_id


def update_step(task_id: str, step: str, state: str):
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return

        for p in task["progress"]:
            if p["step"] == step:
                p["state"] = state
                break


def complete_task(task_id: str, mode: str, papers=None, result=None):
    with _LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return

        task["status"] = "completed"
        task["mode"] = mode
        task["papers"] = papers or []
        task["result"] = result


def get_task(task_id: str):
    with _LOCK:
        return _TASKS.get(task_id)

def add_task_log(task_id: str, message: str):
    with _LOCK:
        task = _TASKS.get(task_id)
        if task:
            task.setdefault("logs", []).append(message)

