import os
import secrets
from datetime import datetime

from flask import Flask, redirect, url_for

from helpers import euro_datetime
from routes.dashboard import dashboard_bp
from routes.transactions import transactions_bp
from routes.cash import cash_bp
from routes.api import api_bp
from routes.about import about_bp
from db import close_db

app = Flask(__name__)

_secret = os.environ.get('SECRET_KEY')
if not _secret:
    _secret = secrets.token_urlsafe(32)
    app.logger.warning(
        "SECRET_KEY environment variable not set; using a temporary key for this run."
    )
app.config['SECRET_KEY'] = _secret
app.config['ASSET_VERSION'] = os.environ.get('ASSET_VERSION', '2')

# Register Jinja custom filters
app.jinja_env.filters['euro_datetime'] = euro_datetime


@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year, "asset_version": app.config.get('ASSET_VERSION', '1')}


# Register blueprints
app.register_blueprint(dashboard_bp, url_prefix='/')
app.register_blueprint(transactions_bp, url_prefix='/transactions')
app.register_blueprint(cash_bp, url_prefix='/cash')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(about_bp, url_prefix='/about')

# Close DB connections after each request
app.teardown_appcontext(close_db)


# Home (redirect to dashboard)
@app.route('/')
def home():
    return redirect(url_for('dashboard.dashboard'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
