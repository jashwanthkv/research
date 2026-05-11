from services.task_manager import update_step

def before_step(task_id: str, step: str):
    agent_names = {
        "decision": "DECISION",
        "retrieve": " DATABASE_RETRIEVAL",
        "fetch": "🌐 WEB_FETCH",
        "analyse": "🔬 ANALYSIS",
        "explain": "💬 EXPLANATION",
        "continuous_explanation": "💬 CONTINUOUS_EXPLANATION",
    }
    agent_name = agent_names.get(step, step)
    print(f"\n{'*'*70}")
    print(f"⏳ STARTING: {agent_name}")
    print(f"{'*'*70}")
    update_step(task_id, step, "running")

def after_step(task_id: str, step: str):
    print(f"COMPLETED: {step.upper()}")
    print(f"{'*'*70 + chr(10)}")
    update_step(task_id, step, "done")
