import sqlite3
import bcrypt

# Conexión a la base de datos
conn = sqlite3.connect("../data/usuarios.db")
cursor = conn.cursor()

# Crear la tabla si no existe
cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL
)''')

# Función para encriptar contraseña
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# Insertar usuarios de prueba
usuarios = [
    ("admin", hash_password("admin123"), "admin"),
    ("supervisor", hash_password("supervisor123"), "supervisor"),
    ("chus", hash_password("chus123"), "comercial"),
    ("roberto", hash_password("roberto123"), "comercial"),
]

for user in usuarios:
    try:
        cursor.execute("INSERT INTO usuarios (username, password, role) VALUES (?, ?, ?)", user)
    except sqlite3.IntegrityError:
        print(f"El usuario {user[0]} ya existe. Omitiendo...")

# Guardar y cerrar conexión
conn.commit()
conn.close()

print("Usuarios creados correctamente.")