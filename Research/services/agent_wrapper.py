from services.progress_hook import before_step, after_step

def wrap_agent(agent_fn, step_name: str, task_id: str):
    def wrapped(state):
        before_step(task_id, step_name)
        result = agent_fn(state)
        after_step(task_id, step_name)
        return result
    return wrapped
