import sqlite3


def leer_ofertas():
    # Conectar a la base de datos
    conexion = sqlite3.connect("../data/usuarios2.db")
    cursor = conexion.cursor()

    # Ejecutar la consulta para obtener todos los datos de la tabla
    cursor.execute("SELECT * FROM ofertas_comercial")
    ofertas = cursor.fetchall()

    # Cerrar la conexión
    conexion.close()

    # Imprimir los resultados
    for oferta in ofertas:
        print(oferta)


if __name__ == "__main__":
    leer_ofertas()