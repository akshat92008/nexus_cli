import sys
from pathlib import Path

# Ensure project root is in sys.path when running python3 src/app.py directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, render_template
from src.routes import products_blueprint
from src.database import create_products_table

app = Flask(__name__)
app.register_blueprint(products_blueprint)

# Initialize database table on app startup
with app.app_context():
    create_products_table()

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)