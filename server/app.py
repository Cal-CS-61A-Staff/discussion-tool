import os

import click
from flask import Flask, abort, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from server.config import INSTANCE_DIR, SERVER_DIR, DevConfig, ProdConfig, validate_prod_config
from server.extensions import db, limiter, migrate, oauth

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

    if app.config["SENTRY_DSN"]:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=app.config["SENTRY_DSN"],
            integrations=[FlaskIntegration()],
            traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
            environment="production" if config_object is ProdConfig else "development",
        )

    if config_object is ProdConfig:
        validate_prod_config(app)
        # Production always sits behind a reverse proxy (see deploy/Caddyfile)
        # terminating TLS — without this, every request's remote_addr is the
        # proxy's own IP, not the real client's, which would silently break
        # IP-keyed rate limiting (server/extensions.py) by bucketing every
        # user together under one address. x_for/x_proto trust exactly one
        # hop, matching a single reverse proxy in front of gunicorn.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    db.init_app(app)

    import server.models  # noqa: F401  ensures every model is registered before first query

    migrate.init_app(app, db, directory=os.path.join(SERVER_DIR, "migrations"))
    limiter.init_app(app)

    oauth.init_app(app)
    app.config["GOOGLE_OAUTH_ENABLED"] = bool(app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"])
    if app.config["GOOGLE_OAUTH_ENABLED"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

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

    _register_health_route(app)
    _register_seed_command(app)
    _register_create_admin_command(app)
    _register_import_roster_command(app)
    _register_grading_worker_command(app)
    _register_spa_routes(app)

    return app


def _register_health_route(app):
    @app.get("/api/health")
    def health():
        """For a load balancer / uptime check — deliberately checks real DB
        connectivity (not just "the process is up") since that's the
        failure mode worth paging on: gunicorn can be alive and still
        unable to serve a single real request if Postgres is unreachable.
        """
        from sqlalchemy import text

        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            return {"status": "error", "database": "unreachable"}, 503
        return {"status": "ok"}, 200


def _register_seed_command(app):
    @app.cli.command("seed-db")
    def seed_db_command():
        """Create tables and load the demo worksheet + section fixtures."""
        from server.seed import seed_db

        with app.app_context():
            db.create_all()
            seed_db()


def _register_create_admin_command(app):
    @app.cli.command("create-admin")
    @click.argument("display_name")
    @click.option("--email", default=None, help="Optional — recorded for consistency with the roster-import identity model.")
    def create_admin_command(display_name, email):
        """Create an admin user. Unlike student/ta, 'admin' has no login-form
        option (server/models/user.py) — this is the only way to grant it,
        mirroring how a real Canvas/bCourses admin designation comes from the
        roster rather than something a user can self-select.
        """
        from server.models.user import User

        with app.app_context():
            user = User(display_name=display_name, role="admin", email=email.lower() if email else None)
            db.session.add(user)
            db.session.commit()
            print(f"Created admin user '{display_name}' (id={user.id}).")


def _register_import_roster_command(app):
    @app.cli.command("import-roster")
    @click.argument("path", type=click.Path(exists=True))
    def import_roster_command(path):
        """Import a TA-roster file (tab-separated: TA name, then repeating
        Section/Groups column pairs — see server/services/roster_import.py
        for the exact shape and what's used vs. ignored).
        """
        from server.services.roster_import import import_ta_roster

        with open(path) as f:
            text = f.read()

        with app.app_context():
            summary = import_ta_roster(text)
            print(
                f"TAs: {summary['tas_created']} created, {summary['tas_matched']} matched. "
                f"Sections: {summary['sections_created']} created, "
                f"{summary['sections_assigned']} assignments made."
            )


def _register_grading_worker_command(app):
    @app.cli.command("grading-worker")
    def grading_worker_command():
        """Run one grading worker: pulls jobs off the Redis-backed "grading"
        queue (server/services/grading_queue.py) and runs the real Docker
        container for each (server/services/grading_jobs.py). Each worker
        process handles one job — and therefore one Docker container — at a
        time, so run as many processes as you want concurrent containers
        (see README "Grading concurrency" for sizing this against real
        hardware, and for process-supervision options).
        """
        from redis import Redis
        from rq import Worker

        with app.app_context():
            conn = Redis.from_url(app.config["REDIS_URL"])
            Worker(["grading"], connection=conn).work()


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
