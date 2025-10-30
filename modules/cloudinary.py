import cloudinary
import cloudinary.uploader
import cloudinary.api

cloudinary.config(
    cloud_name="dh2x0d89n",
    api_key="626968612235749",
    api_secret="9GeX9gmnqy0FB_RvtxxmB3vEQTw"
)

def upload_image_to_cloudinary(file_obj, folder="incidencias"):
    """
    Sube el archivo (file_obj) a Cloudinary en la carpeta especificada y devuelve la URL segura.
    """
    # Asegúrate de que el archivo se encuentre al inicio
    file_obj.seek(0)
    # Sube la imagen; puedes ajustar opciones adicionales si lo deseas
    upload_result = cloudinary.uploader.upload(file_obj, folder=folder)
    return upload_result.get("secure_url")