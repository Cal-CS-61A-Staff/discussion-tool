from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
oauth = OAuth()
# No app-wide default limit: this app polls constantly (state every ~2.5s,
# run-tests every 1s while grading) and students often share one IP behind
# campus WiFi/NAT, so a blanket per-IP limit would risk throttling a whole
# classroom's legitimate traffic. Only /login and /admin-login (rare,
# one-shot, and the only endpoints with brute-forceable auth) get an
# explicit @limiter.limit(...) — see server/blueprints/auth.py.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
