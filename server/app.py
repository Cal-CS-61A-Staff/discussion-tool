import os

from flask import Flask, abort, send_from_directory

from server.config import INSTANCE_DIR, DevConfig, ProdConfig
from server.extensions import db

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_DIST = os.path.join(REPO_ROOT, "client", "dist")


def create_app(config_object=None):
    if config_object is None:
        config_object = ProdConfig if os.environ.get("FLASK_ENV") == "production" else DevConfig

    # static_folder=None: Flask would otherwise auto-register its own static
    # route at "/<path:filename>" (since static_url_path="/" below would
    # collide with it), which shadows the catch-all SPA-fallback route
    # registered in _register_spa_routes — any direct/refreshed URL like
    # /sections/1/dashboard would hit Flask's static 404 instead of ever
    # reaching the fallback that serves index.html. Serving is handled
    # entirely by serve_spa() instead.
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_object)
    app.config["CLIENT_DIST"] = CLIENT_DIST

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    db.init_app(app)

    import server.models  # noqa: F401  ensures every model is registered before first query

    from server.blueprints.admin import admin_bp
    from server.blueprints.auth import auth_bp
    from server.blueprints.groups import groups_bp
    from server.blueprints.sections import sections_bp
    from server.blueprints.ta import ta_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(sections_bp, url_prefix="/api")
    app.register_blueprint(groups_bp, url_prefix="/api/groups")
    app.register_blueprint(ta_bp, url_prefix="/api/worksheets")
    app.register_blueprint(admin_bp, url_prefix="/api")

    _register_seed_command(app)
    _register_spa_routes(app)

    return app


def _register_seed_command(app):
    @app.cli.command("seed-db")
    def seed_db_command():
        """Create tables and load the demo worksheet + section fixtures."""
        from server.seed import seed_db

        with app.app_context():
            db.create_all()
            seed_db()


def _register_spa_routes(app):
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        if path.startswith("api/"):
            abort(404)
        client_dist = app.config["CLIENT_DIST"]
        full_path = os.path.join(client_dist, path)
        if path and os.path.exists(full_path):
            return send_from_directory(client_dist, path)
        index_path = os.path.join(client_dist, "index.html")
        if not os.path.exists(index_path):
            abort(
                404,
                description=(
                    "Client not built. Run `npm run build` in client/, or use "
                    "`npm run dev` in client/ for local development instead of "
                    "hitting the Flask server's static routes directly."
                ),
            )
        return send_from_directory(client_dist, "index.html")
