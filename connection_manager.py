from fastapi import WebSocket
from typing import Dict
import logging
from agent import Agent
from file_manager import FileManager
from session_manager import ChatManager

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agents: Dict[str, Agent] = {}
        self.file_manager = FileManager()
        self.chat_manager = ChatManager()

    async def connect(self, websocket: WebSocket, wallet_address: str):
        await websocket.accept()
        self.active_connections[wallet_address] = websocket
        self.agents[wallet_address] = Agent(self.file_manager, self.chat_manager)
        
        # Load existing chats for the wallet
        chats = self.chat_manager.get_user_chats(wallet_address)
        await websocket.send_json({
            "type": "contexts_loaded",
            "content": chats
        })
        logger.info(f"Wallet {wallet_address} connected")

    def disconnect(self, wallet_address: str):
        if wallet_address in self.active_connections:
            del self.active_connections[wallet_address]
        if wallet_address in self.agents:
            # Limpiar cualquier estado del agente antes de eliminarlo
            agent = self.agents[wallet_address]
            # Limpiar referencias a acciones que podrían tener estado
            agent.edit_actions = None
            agent.compilation_actions = None
            agent.message_actions = None
            # Eliminar el agente
            del self.agents[wallet_address]
            
        # Limpiar cualquier caché o estado temporal relacionado con el usuario
        if hasattr(self, 'chat_manager') and self.chat_manager:
            # Llamar al nuevo método de limpieza de caché para este usuario
            self.chat_manager.clean_user_cache(wallet_address)
            
        logger.info(f"Wallet {wallet_address} disconnected and cache cleaned")

    async def send_message(self, message: str, wallet_address: str):
        if wallet_address in self.active_connections:
            await self.active_connections[wallet_address].send_text(message) 