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

            # Handle chat history synchronization
            if message_type == "sync_chat_history" or message_type == "full_history_sync":
                try:
                    history = message_data.get("history")
                    if not history or not current_chat_id:
                        raise ValueError("Missing chat history or chat_id")
                    
                    logger.info(f"Syncing chat history for chat {current_chat_id}")
                    
                    # For full history sync, we'll replace everything
                    if message_type == "full_history_sync":
                        # First delete the existing chat if it exists
                        existing_chat = manager.chat_manager.get_chat(wallet_address, current_chat_id)
                        if existing_chat:
                            manager.chat_manager.delete_chat(wallet_address, current_chat_id)
                        logger.info(f"Performing full history replacement for chat {current_chat_id}")
                    
                    # Sync the chat history
                    manager.chat_manager.sync_chat_history(
                        wallet_address,
                        current_chat_id,
                        history
                    )
                    
                    # Send confirmation to the client
                    await manager.send_message(
                        json.dumps({
                            "type": "chat_synced",
                            "content": f"Chat history synced successfully for chat: {current_chat_id}",
                            "metadata": {
                                "chat_id": current_chat_id,
                                "sync_type": message_type
                            }
                        }),
                        wallet_address
                    )
                    continue
                except Exception as e:
                    logger.error(f"Error syncing chat history: {str(e)}")
                    await manager.send_message(
                        json.dumps({
                            "type": "error",
                            "content": f"Error syncing chat history: {str(e)}"
                        }),
                        wallet_address
                    )
                    continue

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

            # Process message
            if message_type == "message":
                # Create or get chat if not exists
                if current_chat_id and not manager.chat_manager.get_chat(wallet_address, current_chat_id):
                    logger.info(f"Creating new chat for message - ID: {current_chat_id}")
                    manager.chat_manager.create_chat(wallet_address, current_chat_id)
                
                # Message format validation
                try:
                    validated_content = content
                    # If content is JSON string, parse it
                    if isinstance(content, str) and (content.startswith('{') or content.startswith('[')):
                        try:
                            parsed_content = json.loads(content)
                            if isinstance(parsed_content, dict) and "text" in parsed_content:
                                validated_content = parsed_content["text"]
                        except json.JSONDecodeError:
                            # Not JSON, use as is
                            pass
                    
                    # Process the message
                    agent = manager.agents.get(wallet_address)
                    if agent:
                        async for response in agent.process_message(validated_content, context, current_chat_id, wallet_address):
                            # Add wallet_address to response for tracking
                            if "wallet_address" not in response:
                                response["wallet_address"] = wallet_address
                            await manager.send_message(json.dumps(response), wallet_address)
                    else:
                        logger.error(f"No agent found for wallet {wallet_address}")
                        await manager.send_message(
                            json.dumps({
                                "type": "error",
                                "content": "Agent initialization failed",
                                "wallet_address": wallet_address
                            }),
                            wallet_address
                        )
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    await manager.send_message(
                        json.dumps({
                            "type": "error",
                            "content": f"Error processing message: {str(e)}"
                        }),
                        wallet_address
                    )

            # Check if response should be suppressed
            if message_data.get("suppress_response", False):
                continue

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
            logger.info(f"WebSocket disconnected for wallet {wallet_address}")
            manager.disconnect(wallet_address)
            break

        except Exception as e:
            logger.error(f"Error in websocket connection: {str(e)}")
            # Asegurar que se limpie la conexión incluso en caso de error
            manager.disconnect(wallet_address)
            break 