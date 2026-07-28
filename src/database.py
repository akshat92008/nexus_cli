import sqlite3

def create_products_table():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products
        (id INTEGER PRIMARY KEY, name TEXT, price REAL, description TEXT)
    ''')
    conn.commit()
    conn.close()

create_products_table()