from flask import Blueprint, request, jsonify
from services.task_manager import create_task, get_task
from services.agent_runner import run_task
import threading

api = Blueprint("api", __name__)


@api.route("/task", methods=["POST"])
def create_task_route():
    data       = request.get_json()
    query      = data.get("query", "").strip()
    session_id = data.get("session_id")
    year_from  = data.get("year_from")
    year_to    = data.get("year_to")

    if not query:
        return jsonify({"error": "query is required"}), 400

    task_id = create_task(query)


    thread = threading.Thread(
        target=run_task,
        args=(task_id, query, session_id, year_from, year_to),
        daemon=True
    )
    thread.start()


    return jsonify({"task_id": task_id}), 200


@api.route("/task/<task_id>", methods=["GET"])
def get_task_status(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify({
        "task_id":  task["task_id"],
        "status":   task["status"],
        "progress": task["progress"],
        "logs":     task.get("logs", []),
    })


@api.route("/task/<task_id>/result", methods=["GET"])
def get_task_result(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task["status"] != "completed":
        return jsonify({"error": "Task not completed yet"}), 202

    return jsonify({
        "task_id": task["task_id"],
        "mode":    task["mode"],
        "papers":  task["papers"],
        "result":  task["result"],
    })