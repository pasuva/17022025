import sqlite3


def agregar_campo_email():
    # Conectar a la base de datos
    conexion = sqlite3.connect("../data/usuarios.db")
    cursor = conexion.cursor()

    # Agregar la columna email si no existe
    try:
        cursor.execute("""
            ALTER TABLE usuarios ADD COLUMN email TEXT;
        """)
        print("Columna 'email' agregada correctamente.")
    except sqlite3.OperationalError:
        print("La columna 'email' ya existe o hubo un error.")

    # Actualizar emails de los usuarios
    usuarios_emails = {
        "admin": "psvpasuva@gmail.com",
        "supervisor": "psvpasuva@gmail.com",
        "chus": None,
        "roberto": "roberto.sanz@verdetuoperador.com",
        "nestor": "nestor.casamichana@verdetuoperador.com",
        "rafa": None,
        "comercial_rafa1": None,
        "comercial_rafa2": None,
        "javi": "ingenieria@symtel.es"
    }

    for usuario, email in usuarios_emails.items():
        if email:
            cursor.execute("""
                UPDATE usuarios SET email = ? WHERE username = ?;
            """, (email, usuario))

    print("Emails actualizados correctamente.")

    # Cerrar la conexión
    conexion.commit()
    conexion.close()


if __name__ == "__main__":
    agregar_campo_email()

