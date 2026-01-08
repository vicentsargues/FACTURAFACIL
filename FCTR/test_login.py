#!/usr/bin/env python3
"""
Script para probar el login directamente con la misma lógica que usa Flask.
"""
import sys
import sqlite3
from pathlib import Path
from werkzeug.security import check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "invoices.db"


def test_login(username: str, password: str):
    """Test login with the same logic as Flask app."""
    if not DB_PATH.exists():
        print(f"Error: La base de datos no existe en {DB_PATH}")
        return False
    
    # Simular exactamente lo que hace Flask
    username = username.strip()
    password = password.strip()
    
    print(f"Testing login:")
    print(f"  Username (after strip): '{username}'")
    print(f"  Password (after strip): '{password}'")
    print(f"  Password length: {len(password)}")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Buscar usuario (igual que Flask)
    cur.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,)
    )
    user = cur.fetchone()
    
    if not user:
        print(f"\n[ERROR] Usuario '{username}' no encontrado en la base de datos.")
        conn.close()
        return False
    
    print(f"\nUsuario encontrado:")
    print(f"  ID: {user['id']}")
    print(f"  Username: '{user['username']}'")
    print(f"  Password hash (primeros 50 chars): {user['password_hash'][:50]}...")
    
    # Verificar contraseña (igual que Flask)
    password_valid = check_password_hash(user["password_hash"], password)
    
    print(f"\nVerificando contraseña...")
    print(f"  Resultado: {'CORRECTO' if password_valid else 'INCORRECTO'}")
    
    if password_valid:
        print("\n[OK] Login exitoso! Las credenciales son correctas.")
        print(f"     Session user_id sería: {user['id']}")
        print(f"     Session username sería: {user['username']}")
    else:
        print("\n[ERROR] La contraseña no coincide.")
        print("\nPosibles causas:")
        print("  1. La contraseña tiene espacios extra")
        print("  2. Caracteres especiales mal codificados")
        print("  3. El hash fue creado con una versión diferente de werkzeug")
        print("\nPrueba a crear el usuario de nuevo:")
        print(f"  python create_user.py {username} '{password}'")
    
    conn.close()
    return password_valid


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python test_login.py <username> <password>")
        print("\nEjemplo:")
        print("  python test_login.py admin adminVSB2001.")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if test_login(username, password):
        sys.exit(0)
    else:
        sys.exit(1)
