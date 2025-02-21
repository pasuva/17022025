import sqlite3
import os

# Ruta de la base de datos
DB_PATH = "../data/usuarios.db"

def delete_tables():
    """ Elimina las tablas datos_uis, datos_mapa y formularios """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Borrar las tablas si existen
        #cursor.execute("DROP TABLE IF EXISTS datos_uis;")
        #cursor.execute("DROP TABLE IF EXISTS datos_mapa;")
        #cursor.execute("DROP TABLE IF EXISTS formularios;")
        cursor.execute("DROP TABLE IF EXISTS nueva_tabla;")

        conn.commit()
        print("✅ Tablas eliminadas correctamente.")

    except sqlite3.Error as e:
        print(f"❌ Error al eliminar las tablas: {e}")

    finally:
        conn.close()

if __name__ == "__main__":
    delete_tables()