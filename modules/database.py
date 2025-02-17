import sqlite3
import bcrypt
import os

# Asegurar que la carpeta 'data' existe
os.makedirs("../data", exist_ok=True)

DB_PATH = "../data/usuarios.db"

def create_db():
    """ Crea la base de datos y las tablas si no existen """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Crear tabla de usuarios
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            rol TEXT CHECK(rol IN ('admin', 'supervisor', 'comercial')),
            password TEXT
        )
        """)

        # Crear tabla de datos del mapa
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS datos_mapa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provincia TEXT,
            municipio TEXT,
            latitud REAL,
            longitud REAL,
            comercial_asignado TEXT
        )
        """)

        # Crear tabla de formularios
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS formularios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comercial TEXT,
            punto_id INTEGER,
            respuesta TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (punto_id) REFERENCES datos_mapa (id)
        )
        """)

        conn.commit()  # Guardar cambios
        print("✅ Base de datos y tablas creadas correctamente.")

    except sqlite3.Error as e:
        print(f"❌ Error al crear la base de datos: {e}")

    finally:
        conn.close()

def add_user(nombre, rol, password):
    """ Agregar un usuario a la base de datos con contraseña encriptada """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()  # Convertimos bytes a string

    try:
        cursor.execute("INSERT INTO usuarios (username, password, role) VALUES (?, ?, ?)", (nombre, rol, hashed_pw))
        conn.commit()
        print(f"✅ Usuario '{nombre}' creado con éxito.")
    except sqlite3.IntegrityError:
        print(f"⚠️ El usuario '{nombre}' ya existe.")
    finally:
        conn.close()

def verify_user(nombre, password):
    """ Verifica si un usuario existe y su contraseña es correcta """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM usuarios WHERE username = ?", (nombre,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return bcrypt.checkpw(password.encode(), result[0])
    return False

# Ejecutar creación de DB y añadir usuario admin
if __name__ == "__main__":
    create_db()
    add_user("admin", "admin", "admin123")