import sqlite3


def get_all_ofertas_comercial():
    # Conectar a la base de datos
    conn = sqlite3.connect('../data/usuarios.db')
    cursor = conn.cursor()

    # Ejecutar la consulta para obtener todos los registros
    cursor.execute("SELECT * FROM ofertas_comercial")

    # Obtener todos los resultados
    rows = cursor.fetchall()

    # Cerrar la conexión a la base de datos
    conn.close()

    return rows


if __name__ == '__main__':
    resultados = get_all_ofertas_comercial()
    for fila in resultados:
        print(fila)
