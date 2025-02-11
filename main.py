from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from typing import Dict
import asyncio
from agent import Agent
from file_manager import FileManager
from session_manager import SessionManager
import uuid
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear una única instancia de SessionManager
session_manager = SessionManager()

# Almacenar conexiones activas
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agents: Dict[str, Agent] = {}
        self.file_manager = FileManager()
        self.session_manager = session_manager

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

manager = ConnectionManager()

# WebSocket endpoint con manejo de sesiones
@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket, wallet_address: str | None = None):
    client_id = str(uuid.uuid4())
    session = manager.session_manager.create_session(client_id, wallet_address)
    
    await manager.connect(websocket, client_id)
    try:
        # Enviar información de conexión al cliente
        await manager.send_message(
            json.dumps({
                "type": "connection_established",
                "client_id": client_id,
                "session_id": session.session_id,
                "session_name": f"Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }),
            client_id
        )

        # Enviar los contextos al cliente
        contexts = manager.session_manager.get_session_contexts(session.session_id)
        await manager.send_message(
            json.dumps({
                "type": "contexts_loaded",
                "content": contexts
            }),
            client_id
        )

        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("content", "")
                context = message_data.get("context", {})
                message_type = message_data.get("type", "message")
                context_id = message_data.get("contextId")

                if message_type == "create_context":
                    # Crear nuevo contexto
                    new_context = manager.session_manager.create_context(
                        session.session_id,
                        message_data.get("name", f"Chat {len(contexts) + 1}")
                    )
                    await manager.send_message(
                        json.dumps({
                            "type": "context_created",
                            "content": new_context
                        }),
                        client_id
                    )
                    continue

                if message_type == "switch_context":
                    # Cambiar contexto activo
                    switched_context = manager.session_manager.switch_context(
                        session.session_id,
                        message_data.get("contextId")
                    )
                    await manager.send_message(
                        json.dumps({
                            "type": "context_switched",
                            "content": switched_context
                        }),
                        client_id
                    )
                    continue

                # Procesar el mensaje con el agente
                agent = manager.agents[client_id]
                response_generator = agent.process_message(content, context, context_id)
                
                async for response in response_generator:
                    if context_id:
                        # Guardar la respuesta en el contexto específico
                        manager.session_manager.add_message_to_context(
                            session.session_id,
                            context_id,
                            {
                                "id": str(uuid.uuid4()),
                                "text": response["content"],
                                "sender": "ai",
                                "timestamp": message_data.get("timestamp", datetime.now().timestamp() * 1000),
                                "type": response["type"]
                            }
                        )
                    
                    # Enviar la respuesta al cliente
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