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
            username TEXT UNIQUE,
            role TEXT CHECK(role IN ('admin', 'supervisor', 'comercial')),
            password TEXT
        )
        """)

        # Crear tabla datos_uis
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS datos_uis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_ams TEXT,
            apartment_id TEXT,
            address_id TEXT,
            provincia TEXT,
            municipio TEXT,
            poblacion TEXT,
            vial TEXT,
            numero TEXT,
            parcela_catastral TEXT,
            letra TEXT,
            cp TEXT,
            site_operational_state TEXT,
            apartment_operational_state TEXT,
            cto_id TEXT,
            olt TEXT,
            cto TEXT,
            latitud REAL,
            longitud REAL,
            cto_con_proyecto TEXT,
            comercial TEXT,
            zona TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            serviciable TEXT,
            motivo TEXT,
            contrato_uis TEXT
        )
        """)

        # Crear tabla ofertas_comercial
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ofertas_comercial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartment_id TEXT,
            provincia TEXT,
            municipio TEXT,
            poblacion TEXT,
            vial TEXT,
            numero TEXT,
            letra TEXT,
            cp TEXT,
            latitud REAL,
            longitud REAL,
            nombre_cliente TEXT,
            telefono TEXT,
            direccion_alternativa TEXT,
            observaciones TEXT,
            serviciable TEXT,
            motivo_serviciable TEXT,
            incidencia TEXT,
            motivo_incidencia TEXT,
            fichero_imagen TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
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
        cursor.execute("INSERT INTO usuarios (username, role, password) VALUES (?, ?, ?)", (nombre, rol, hashed_pw))
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
        return bcrypt.checkpw(password.encode(), result[0].encode())
    return False

# Ejecutar creación de DB y añadir usuario admin
if __name__ == "__main__":
    create_db()
    add_user("admin", "admin", "admin123")

