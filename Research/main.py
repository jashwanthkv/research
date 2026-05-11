
import sys, io, os
os.environ["PYTHONUTF8"] = "1"  # force UTF-8 in subprocesses (Flask debug restart)
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask
from flask_cors import CORS
from vectore_store.paper_index_store import init_paper_index
from api.routes import api
from config import llm, embeddings
from vectore_store.chroma_store import init_chroma


def create_app():
    app = Flask(__name__)
    init_chroma()
    init_paper_index()
    CORS(app)
    app.register_blueprint(api, url_prefix="/api")
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
