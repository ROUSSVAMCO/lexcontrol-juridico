
from app import revisar_y_enviar_notificaciones

if __name__ == "__main__":
    total = revisar_y_enviar_notificaciones()
    print(f"Notificaciones procesadas: {total}")
