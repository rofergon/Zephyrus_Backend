from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from typing import Dict, List
import asyncio
from agent import Agent
from file_manager import FileManager
from session_manager import SessionManager
import uuid
from datetime import datetime
from pydantic import BaseModel

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

# Crear una única instancia de SessionManager
session_manager = SessionManager()

# Almacenar conexiones activas
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agents: Dict[str, Agent] = {}
        self.file_manager = FileManager()
        self.session_manager = session_manager  # Usar la instancia única

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

class SessionCreate(BaseModel):
    name: str | None = None
    wallet_address: str | None = None

class SessionRename(BaseModel):
    new_name: str

# Endpoints REST para gestión de sesiones
@app.get("/api/sessions/{client_id}")
async def get_client_sessions(client_id: str, wallet_address: str | None = None):
    sessions = manager.session_manager.get_client_sessions(client_id, wallet_address)
    return [session.to_dict() for session in sessions]

@app.post("/api/sessions/{client_id}")
async def create_session(client_id: str, session_data: SessionCreate):
    try:
        name = session_data.name if session_data.name else f"Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        session = manager.session_manager.create_session(
            name=name,
            client_id=client_id,
            wallet_address=session_data.wallet_address
        )
        return session.to_dict()
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    manager.session_manager.delete_session(session_id)
    return {"status": "success"}

@app.put("/api/sessions/{session_id}/name")
async def rename_session(session_id: str, rename_data: SessionRename):
    try:
        manager.session_manager.rename_session(session_id, rename_data.new_name)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error renaming session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint con manejo de sesiones
@app.websocket("/ws/agent/{client_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    session_id: str,
    wallet_address: str | None = None
):
    await manager.connect(websocket, client_id)
    session = manager.session_manager.get_session(session_id)
    
    if not session:
        await websocket.close(code=4000, reason="Session not found")
        return

    # Verificar que la billetera coincida si está presente
    if wallet_address and session.wallet_address and wallet_address != session.wallet_address:
        await websocket.close(code=4001, reason="Unauthorized wallet address")
        return
        
    try:
        # Enviar el historial de la sesión al cliente
        if session.conversation_history:
            for message in session.conversation_history:
                await manager.send_message(json.dumps(message), client_id)

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
                    # Guardar la respuesta en el historial de la sesión
                    manager.session_manager.add_to_conversation_history(
                        session_id,
                        {
                            "type": response["type"],
                            "content": response["content"],
                            "timestamp": message_data.get("timestamp", None),
                            "sender": "agent"
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

# Endpoint para conexión automática
@app.websocket("/ws/agent")
async def websocket_endpoint_auto(websocket: WebSocket, wallet_address: str | None = None):
    client_id = str(uuid.uuid4())
    session_name = f"Session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    session = manager.session_manager.create_session(
        name=session_name,
        client_id=client_id,
        wallet_address=wallet_address
    )
    
    await manager.connect(websocket, client_id)
    try:
        # Enviar información de conexión al cliente
        await manager.send_message(
            json.dumps({
                "type": "connection_established",
                "client_id": client_id,
                "session_id": session.session_id,
                "session_name": session.name
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
                    # Guardar la respuesta en el historial de la sesión
                    manager.session_manager.add_to_conversation_history(
                        session.session_id,
                        {
                            "type": response["type"],
                            "content": response["content"],
                            "timestamp": message_data.get("timestamp", None),
                            "sender": "agent"
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