import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Blueprint, jsonify
try:
    from src.models import Product
except ModuleNotFoundError:
    from models import Product

products_blueprint = Blueprint('products', __name__)

@products_blueprint.route('/products', methods=['GET'])
def get_products():
    products = [
        Product(id=1, name='Mechanical Gaming Keyboard', price=89.99, description='RGB backlit mechanical switches with custom PBT keycaps.'),
        Product(id=2, name='Ergonomic Wireless Mouse', price=49.99, description='Precision 26k DPI optical sensor with dual Bluetooth connection.'),
        Product(id=3, name='Noise Cancelling Headphones', price=199.99, description='Active noise cancellation with 40-hour long battery life.'),
        Product(id=4, name='Ultra-Wide 4K Gaming Monitor', price=499.99, description='34-inch curved IPS panel with 144Hz refresh rate and HDR10.')
    ]
    return jsonify([{'id': product.id, 'name': product.name, 'price': product.price, 'description': product.description} for product in products])