from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from typing import Dict, List
import asyncio
from agent import Agent
from file_manager import FileManager
import uuid

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenar conexiones activas
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agents: Dict[str, Agent] = {}
        self.file_manager = FileManager()

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.agents[client_id] = Agent(self.file_manager)
        logger.info(f"Client {client_id} connected")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.agents:
            del self.agents[client_id]
        logger.info(f"Client {client_id} disconnected")

    async def send_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

manager = ConnectionManager()

# Endpoint que acepta client_id en la URL
@app.websocket("/ws/agent/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("content", "")
                context = message_data.get("context", {})
                
                # Procesar el mensaje con el agente
                agent = manager.agents[client_id]
                response_generator = agent.process_message(content, context)
                
                async for response in response_generator:
                    # Enviar cada respuesta al cliente
                    await manager.send_message(
                        json.dumps(response),
                        client_id
                    )
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
                await manager.send_message(
                    json.dumps({
                        "type": "error",
                        "content": "Invalid message format"
                    }),
                    client_id
                )
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await manager.send_message(
                    json.dumps({
                        "type": "error",
                        "content": f"Error: {str(e)}"
                    }),
                    client_id
                )

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        manager.disconnect(client_id)

# Nuevo endpoint que genera un client_id automáticamente
@app.websocket("/ws/agent")
async def websocket_endpoint_auto(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.connect(websocket, client_id)
    try:
        # Enviar el client_id al cliente
        await manager.send_message(
            json.dumps({
                "type": "connection_established",
                "client_id": client_id
            }),
            client_id
        )
        
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("content", "")
                context = message_data.get("context", {})
                
                # Procesar el mensaje con el agente
                agent = manager.agents[client_id]
                response_generator = agent.process_message(content, context)
                
                async for response in response_generator:
                    # Enviar cada respuesta al cliente
                    await manager.send_message(
                        json.dumps(response),
                        client_id
                    )
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
                await manager.send_message(
                    json.dumps({
                        "type": "error",
                        "content": "Invalid message format"
                    }),
                    client_id
                )
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await manager.send_message(
                    json.dumps({
                        "type": "error",
                        "content": f"Error: {str(e)}"
                    }),
                    client_id
                )

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        manager.disconnect(client_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 