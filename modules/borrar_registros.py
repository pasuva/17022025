import sqlite3

# Conexión a la base de datos
conn = sqlite3.connect("../data/usuarios.db")
cursor = conn.cursor()


# Función para limpiar las tablas y resetear IDs
def limpiar_y_resetear_tabla(tabla):
    try:
        # Eliminar todos los registros de la tabla
        cursor.execute(f"DELETE FROM {tabla}")
        print(f"Datos de la tabla {tabla} eliminados correctamente.")

        # Resetear el contador de autoincremento
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabla}'")
        print(f"ID de la tabla {tabla} reiniciado correctamente.")

    except sqlite3.Error as e:
        print(f"Error al limpiar la tabla {tabla}: {e}")


# Lista de tablas a limpiar
tablas_a_limpiar = ["trazabilidad", "viabilidades", "comercial_rafa"]

# Limpiar cada tabla y resetear IDs
for tabla in tablas_a_limpiar:
    limpiar_y_resetear_tabla(tabla)

# Guardar los cambios y cerrar la conexión
conn.commit()
conn.close()

print("Datos de las tablas limpiados y IDs reiniciados correctamente.")