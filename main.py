from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import logging
from connection_manager import ConnectionManager
from websocket_handlers import handle_websocket_connection

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS with security restrictions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your Cloudflare domain when you have it
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Create a single instance of ConnectionManager
manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    """
    Evento de inicio de la aplicación que limpia cualquier estado persistente
    que podría haber quedado de ejecuciones anteriores.
    """
    logger.info("Iniciando servidor y limpiando caché previa...")
    # Si hay almacenamiento persistente para conexiones o chats, reiniciarlos aquí
    manager.active_connections = {}
    manager.agents = {}
    # También se podría reiniciar cualquier estado persistente del ChatManager
    # como manager.chat_manager.reset_all_connections() si es necesario
    logger.info("Servidor iniciado y caché limpia")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Evento de cierre de la aplicación que limpia cualquier estado persistente
    y cierra correctamente todas las conexiones.
    """
    logger.info("Cerrando servidor y limpiando recursos...")
    # Cerrar todas las conexiones activas
    for wallet_address in list(manager.active_connections.keys()):
        try:
            logger.info(f"Desconectando al usuario {wallet_address}")
            manager.disconnect(wallet_address)
        except Exception as e:
            logger.error(f"Error al desconectar al usuario {wallet_address}: {str(e)}")
    logger.info("Servidor cerrado y recursos liberados")

@app.get("/")
async def healthcheck():
    return {"status": "healthy", "message": "Server is running"}

# WebSocket endpoint with session handling
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket, wallet_address: str | None = None, chat_id: str | None = None):
    await handle_websocket_connection(websocket, wallet_address, chat_id, manager)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",  # Changed to localhost since Cloudflare Tunnel will handle exposure
        port=8000,
        reload=True
    ) 