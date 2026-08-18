from server.app import create_app
from server.config import ProdConfig

app = create_app(ProdConfig)
