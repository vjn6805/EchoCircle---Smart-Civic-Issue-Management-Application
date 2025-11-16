from flask import Flask
from config import SECRET_KEY
from routes.auth import register_auth_routes
from routes.user import register_user_routes
from routes.admin import register_admin_routes
from routes.technician import register_technician_routes

app = Flask(__name__)
app.secret_key = SECRET_KEY

register_auth_routes(app)
register_user_routes(app)
register_admin_routes(app)
register_technician_routes(app)

if __name__ == '__main__':
    app.run(debug=True)