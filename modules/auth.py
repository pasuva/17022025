import sqlite3

DB_PATH = "../data/usuarios.db"

def get_user_role(username):
    """ Obtiene el rol de un usuario """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM usuarios WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None