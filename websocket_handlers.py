from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import json
import logging
from datetime import datetime
import uuid
from connection_manager import ConnectionManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_websocket_connection(
    websocket: WebSocket,
    wallet_address: str | None,
    chat_id: str | None,
    manager: ConnectionManager
):
    logger.info(f"Attempting connection - Wallet: {wallet_address}, Chat ID: {chat_id}")
    
    if not wallet_address:
        logger.error("Connection rejected - Wallet address not provided")
        await websocket.close(code=1008, reason="Invalid wallet address - No wallet address provided")
        return
    
    if not wallet_address.startswith('0x'):
        logger.error(f"Connection rejected - Invalid wallet format: {wallet_address}")
        await websocket.close(code=1008, reason="Invalid wallet address - Must start with 0x")
        return

    await manager.connect(websocket, wallet_address)

    if chat_id:
        try:
            uuid.UUID(chat_id)
            logger.info(f"Valid UUID format for chat_id: {chat_id}")
        except ValueError:
            logger.error(f"Connection rejected - Invalid UUID format for chat_id: {chat_id}")
            await websocket.close(code=1008, reason="Invalid chat_id format - must be a valid UUID")
            return

        existing_chat = manager.chat_manager.get_chat_by_id(chat_id)
        if not existing_chat:
            logger.info(f"Creating new chat - ID: {chat_id}, Wallet: {wallet_address}")
            manager.chat_manager.create_chat(wallet_address, chat_id)
            logger.info(f"Successfully created new chat with ID {chat_id} for wallet {wallet_address}")
        else:
            logger.info(f"Using existing chat - ID: {chat_id}, Wallet: {wallet_address}")

    while True:
        try:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            content = message_data.get("content", "")
            context = message_data.get("context", {})
            message_type = message_data.get("type", "message")
            
            current_chat_id = chat_id or message_data.get("chat_id")
            
            logger.debug(f"Received message - Type: {message_type}, Chat ID: {current_chat_id}, Wallet: {wallet_address}")

            # Skip processing for contexts_synced messages
            if message_type == "contexts_synced":
                continue

            if message_type == "save_file":
                try:
                    path = message_data.get("path")
                    if not path:
                        raise ValueError("No path provided for file")
                    
                    # Save the file in the chat
                    manager.chat_manager.add_virtual_file_to_chat(
                        wallet_address,
                        current_chat_id,
                        path,
                        content,
                        message_data.get("language", "solidity")
                    )
                    
                    # Send confirmation to the client
                    await manager.send_message(
                        json.dumps({
                            "type": "file_saved",
                            "content": f"File saved successfully: {path}",
                            "metadata": {
                                "path": path,
                                "chat_id": current_chat_id
                            }
                        }),
                        wallet_address
                    )
                    continue
                except Exception as e:
                    logger.error(f"Error saving file: {str(e)}")
                    await manager.send_message(
                        json.dumps({
                            "type": "error",
                            "content": f"Error saving file: {str(e)}"
                        }),
                        wallet_address
                    )
                    continue

            elif message_type == "get_file_version":
                try:
                    path = message_data.get("path")
                    version = message_data.get("version")
                    if not path:
                        raise ValueError("No path provided for file")
                    
                    # Get the file version
                    file_data = manager.chat_manager.get_virtual_file_from_chat(
                        wallet_address,
                        current_chat_id,
                        path,
                        version
                    )
                    
                    if file_data:
                        await manager.send_message(
                            json.dumps({
                                "type": "file_version",
                                "content": file_data["content"],
                                "metadata": {
                                    "path": path,
                                    "chat_id": current_chat_id,
                                    "version": version,
                                    "timestamp": file_data["timestamp"]
                                }
                            }),
                            wallet_address
                        )
                    else:
                        await manager.send_message(
                            json.dumps({
                                "type": "error",
                                "content": f"File version not found: {path}"
                            }),
                            wallet_address
                        )
                    continue
                except Exception as e:
                    logger.error(f"Error getting file version: {str(e)}")
                    await manager.send_message(
                        json.dumps({
                            "type": "error",
                            "content": f"Error getting file version: {str(e)}"
                        }),
                        wallet_address
                    )
                    continue

            # Create a new message in the chat
            if current_chat_id:
                manager.chat_manager.add_message_to_chat(
                    wallet_address,
                    current_chat_id,
                    {
                        "id": str(uuid.uuid4()),
                        "text": content,
                        "sender": "user",
                        "timestamp": datetime.now().timestamp() * 1000
                    }
                )

            # Check if response should be suppressed
            if message_data.get("suppress_response", False):
                continue

            # Process the message with the agent
            agent = manager.agents[wallet_address]
            response_generator = agent.process_message(content, context, current_chat_id)
            
            async for response in response_generator:
                if current_chat_id:
                    # Save AI response to chat
                    manager.chat_manager.add_message_to_chat(
                        wallet_address,
                        current_chat_id,
                        {
                            "id": str(uuid.uuid4()),
                            "text": response["content"],
                            "sender": "ai",
                            "timestamp": datetime.now().timestamp() * 1000,
                            "type": response["type"]
                        }
                    )
                    
                    # If it's a file_create or code_edit message type, save the file in the chat
                    if response["type"] in ["file_create", "code_edit"] and response.get("metadata", {}).get("path"):
                        manager.chat_manager.add_virtual_file_to_chat(
                            wallet_address,
                            current_chat_id,
                            response["metadata"]["path"],
                            response["content"],
                            response["metadata"].get("language", "solidity")
                        )
                
                # Send response to client
                await manager.send_message(
                    json.dumps(response),
                    wallet_address
                )
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {data}")
            await manager.send_message(
                json.dumps({
                    "type": "error",
                    "content": "Invalid message format"
                }),
                wallet_address
            )

        except WebSocketDisconnect:
            manager.disconnect(wallet_address)
            break

        except Exception as e:
            logger.error(f"Error in websocket connection: {str(e)}")
            manager.disconnect(wallet_address)
            break 