
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
