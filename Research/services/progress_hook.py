from services.task_manager import update_step

def before_step(task_id: str, step: str):
    update_step(task_id, step, "running")

def after_step(task_id: str, step: str):
    update_step(task_id, step, "done")
