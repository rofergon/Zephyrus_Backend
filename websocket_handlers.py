from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import json
import logging
from datetime import datetime
import uuid
from connection_manager import ConnectionManager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_websocket_connection(
    websocket: WebSocket,
    wallet_address: str | None,
    manager: ConnectionManager
):
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
                await handle_websocket_message(data, client_id, manager, session)
                    
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

async def handle_websocket_message(data: str, client_id: str, manager: ConnectionManager, session):
    message_data = json.loads(data)
    content = message_data.get("content", "")
    context = message_data.get("context", {})
    message_type = message_data.get("type", "message")
    context_id = message_data.get("contextId")

    if message_type == "create_context":
        await handle_create_context(message_data, manager, session, client_id)
        return

    if message_type == "switch_context":
        await handle_switch_context(message_data, manager, session, client_id)
        return

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

async def handle_create_context(message_data: dict, manager: ConnectionManager, session, client_id: str):
    contexts = manager.session_manager.get_session_contexts(session.session_id)
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

async def handle_switch_context(message_data: dict, manager: ConnectionManager, session, client_id: str):
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