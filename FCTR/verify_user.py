#!/usr/bin/env python3
"""
Script para verificar usuarios en la base de datos y probar login.
Uso: python verify_user.py <username> <password>
"""
import sys
import sqlite3
from pathlib import Path
from werkzeug.security import check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "invoices.db"


def verify_user(username: str, password: str):
    """Verify a user's credentials."""
    if not DB_PATH.exists():
        print(f"Error: La base de datos no existe en {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get user
    cur.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    
    if not user:
        print(f"Error: El usuario '{username}' no existe en la base de datos.")
        conn.close()
        return False
    
    print(f"Usuario encontrado:")
    print(f"  ID: {user['id']}")
    print(f"  Username: {user['username']}")
    print(f"  Password hash: {user['password_hash'][:50]}...")
    
    # Check password
    password_matches = check_password_hash(user["password_hash"], password)
    
    print(f"\nVerificando contraseña...")
    print(f"  Contraseña proporcionada: '{password}'")
    print(f"  Longitud: {len(password)} caracteres")
    print(f"  Coincide: {'SI' if password_matches else 'NO'}")
    
    if password_matches:
        print("\n[OK] Las credenciales son correctas.")
    else:
        print("\n[ERROR] La contraseña no coincide.")
        print("\nPosibles causas:")
        print("  - Espacios al inicio o final de la contraseña")
        print("  - Caracteres especiales mal codificados")
        print("  - La contraseña fue creada con un hash diferente")
    
    conn.close()
    return password_matches


def list_users():
    """List all users in the database."""
    if not DB_PATH.exists():
        print(f"Error: La base de datos no existe en {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT id, username, created_at FROM users ORDER BY id")
    users = cur.fetchall()
    
    if not users:
        print("No hay usuarios en la base de datos.")
    else:
        print(f"Usuarios en la base de datos ({len(users)}):")
        for user in users:
            print(f"  ID: {user['id']}, Username: '{user['username']}', Creado: {user['created_at']}")
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        list_users()
        sys.exit(0)
    
    if len(sys.argv) < 3:
        print("Uso: python verify_user.py <username> <password>")
        print("   o: python verify_user.py  (para listar todos los usuarios)")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if verify_user(username, password):
        sys.exit(0)
    else:
        sys.exit(1)
