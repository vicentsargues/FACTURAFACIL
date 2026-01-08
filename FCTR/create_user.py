#!/usr/bin/env python3
"""
Script para crear usuarios en la base de datos.
Uso: python create_user.py <username> <password>
"""
import sys
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "invoices.db"


def create_user(username: str, password: str):
    """Create a new user in the database."""
    if not DB_PATH.exists():
        print(f"Error: La base de datos no existe en {DB_PATH}")
        print("Ejecuta primero la aplicación para inicializar la base de datos.")
        return False
    
    if not username or not password:
        print("Error: Usuario y contraseña son obligatorios.")
        return False
    
    if len(password) < 6:
        print("Advertencia: La contraseña es muy corta (minimo 6 caracteres recomendado).")
        print("Continuando de todas formas...")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Check if user already exists
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone():
        print(f"Error: El usuario '{username}' ya existe.")
        conn.close()
        return False
    
    # Create user
    password_hash = generate_password_hash(password)
    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash)
    )
    conn.commit()
    conn.close()
    
    print(f"[OK] Usuario '{username}' creado correctamente.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python create_user.py <username> <password>")
        print("\nEjemplo:")
        print("  python create_user.py admin mi_password_seguro")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if create_user(username, password):
        sys.exit(0)
    else:
        sys.exit(1)
