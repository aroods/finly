from flask import Flask, redirect, url_for
from helpers import euro_datetime  # If you have custom filters
from routes.dashboard import dashboard_bp
from routes.transactions import transactions_bp
from routes.cash import cash_bp
from routes.api import api_bp
from routes.about import about_bp
from db import close_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with your secret

# Register Jinja custom filters
app.jinja_env.filters['euro_datetime'] = euro_datetime

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
