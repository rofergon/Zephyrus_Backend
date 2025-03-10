import json
import os
from datetime import datetime
import uuid
import logging
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Chat:
    def __init__(self, chat_id: str, name: str, wallet_address: str):
        self.chat_id = chat_id
        self.name = name
        self.wallet_address = wallet_address
        self.created_at = datetime.now().isoformat()
        self.last_accessed = datetime.now().isoformat()
        self.messages = []
        self.virtual_files = {}  # {base_name: {content, language, timestamp}}
        self.virtual_file_history = {}  # {base_name: [{content, timestamp}]}
        logger.info(f"Created new chat: {chat_id} for wallet: {wallet_address}")

    def to_dict(self) -> dict:
        # Solo incluir los archivos activos en la serialización
        return {
            "id": self.chat_id,
            "name": self.name,
            "wallet_address": self.wallet_address,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "messages": self.messages,
            "type": "chat",
            "virtualFiles": {
                f"contracts/{name}": file_data 
                for name, file_data in self.virtual_files.items()
            }
        }

    def add_message(self, message: dict) -> None:
        self.messages.append(message)
        self.last_accessed = datetime.now().isoformat()

    def add_virtual_file(self, path: str, content: str, language: str = "solidity") -> None:
        """Añade o actualiza un archivo virtual en el chat."""
        current_time = datetime.now().timestamp() * 1000
        
        # Extraer el nombre base del archivo (eliminar timestamp si existe)
        base_name = os.path.basename(path).replace(".sol", "")
        base_name = base_name.split("_")[0] + ".sol"
        
        # Si el contenido es diferente al actual, crear nueva versión
        if base_name in self.virtual_files:
            current = self.virtual_files[base_name]
            if content != current["content"]:
                # Guardar versión anterior en el historial
                if base_name not in self.virtual_file_history:
                    self.virtual_file_history[base_name] = []
                self.virtual_file_history[base_name].append({
                    "content": current["content"],
                    "timestamp": current["timestamp"]
                })
                # Mantener solo las últimas 5 versiones en el historial
                if len(self.virtual_file_history[base_name]) > 5:
                    self.virtual_file_history[base_name] = self.virtual_file_history[base_name][-5:]
        
        # Actualizar archivo activo
        self.virtual_files[base_name] = {
            "content": content,
            "language": language,
            "timestamp": current_time
        }
        
        self.last_accessed = datetime.now().isoformat()

    def get_virtual_file(self, path: str, version: int = None) -> dict | None:
        """Obtiene un archivo virtual del chat, opcionalmente una versión específica."""
        base_name = os.path.basename(path).replace(".sol", "").split("_")[0] + ".sol"
        
        if version is None:
            # Retornar versión activa
            if base_name in self.virtual_files:
                return self.virtual_files[base_name]
            return None
            
        # Retornar versión específica del historial
        if base_name in self.virtual_file_history:
            history = self.virtual_file_history[base_name]
            if 0 <= version < len(history):
                return history[version]
        
        return None

    def delete_virtual_file(self, path: str) -> None:
        """Elimina un archivo virtual del chat."""
        base_name = os.path.basename(path).replace(".sol", "").split("_")[0] + ".sol"
        if base_name in self.virtual_files:
            del self.virtual_files[base_name]
            if base_name in self.virtual_file_history:
                del self.virtual_file_history[base_name]
        self.last_accessed = datetime.now().isoformat()

    def get_file_history(self, path: str) -> List[dict]:
        """Obtiene el historial de versiones de un archivo."""
        base_name = os.path.basename(path).replace(".sol", "").split("_")[0] + ".sol"
        if base_name in self.virtual_file_history:
            return self.virtual_file_history[base_name]
        return []

class ChatManager:
    def __init__(self):
        self.chats = {}  # wallet_address -> {chat_id -> Chat}

    def create_chat(self, wallet_address: str, chat_id: str, name: str = None) -> Chat:
        """Crea un chat temporal con el ID proporcionado por el frontend."""
        if wallet_address not in self.chats:
            self.chats[wallet_address] = {}
            
        if chat_id in self.chats.get(wallet_address, {}):
            return self.chats[wallet_address][chat_id]
            
        chat_name = name or f"Chat {len(self.chats[wallet_address]) + 1}"
        chat = Chat(chat_id, chat_name, wallet_address)
        
        self.chats[wallet_address][chat_id] = chat
        return chat

    def sync_chat_history(self, wallet_address: str, chat_id: str, history: dict) -> None:
        """Sincroniza el historial del chat desde el frontend."""
        if not self.get_chat(wallet_address, chat_id):
            self.create_chat(wallet_address, chat_id, history.get("name"))
        
        chat = self.get_chat(wallet_address, chat_id)
        if chat:
            # Verify and format messages
            formatted_messages = []
            if "messages" in history and isinstance(history["messages"], list):
                for msg in history["messages"]:
                    if isinstance(msg, dict) and "text" in msg and "sender" in msg:
                        # Ensure timestamp exists
                        if "timestamp" not in msg:
                            msg["timestamp"] = datetime.now().isoformat()
                        formatted_messages.append(msg)
            
            chat.messages = formatted_messages
            
            # Verify and format virtual files
            if "virtualFiles" in history and isinstance(history["virtualFiles"], dict):
                # Process and validate each file
                validated_files = {}
                for path, file_data in history["virtualFiles"].items():
                    if isinstance(file_data, dict) and "content" in file_data:
                        # Extract file name from path
                        base_name = os.path.basename(path)
                        # Ensure all required fields exist
                        validated_file = {
                            "content": str(file_data["content"]),
                            "language": file_data.get("language", "solidity"),
                            "timestamp": file_data.get("timestamp", datetime.now().timestamp() * 1000)
                        }
                        validated_files[base_name] = validated_file
                
                chat.virtual_files = validated_files
            
            # Update timestamps
            chat.created_at = history.get("created_at", datetime.now().isoformat())
            chat.last_accessed = history.get("last_accessed", datetime.now().isoformat())

    def get_user_chats(self, wallet_address: str) -> list:
        return [chat.to_dict() for chat in self.chats.get(wallet_address, {}).values()]

    def get_chat(self, wallet_address: str, chat_id: str) -> Chat | None:
        return self.chats.get(wallet_address, {}).get(chat_id)

    def add_message_to_chat(self, wallet_address: str, chat_id: str, message: dict) -> None:
        chat = self.get_chat(wallet_address, chat_id)
        if chat:
            chat.add_message(message)
        else:
            raise ValueError(f"Chat {chat_id} not found for wallet {wallet_address}")

    def add_virtual_file_to_chat(self, wallet_address: str, chat_id: str, path: str, content: str, language: str = "solidity") -> None:
        """Añade o actualiza un archivo virtual en un chat específico."""
        chat = self.get_chat(wallet_address, chat_id)
        if chat:
            chat.add_virtual_file(path, content, language)
        else:
            raise ValueError(f"Chat {chat_id} not found for wallet {wallet_address}")

    def get_virtual_file_from_chat(self, wallet_address: str, chat_id: str, path: str, version: int = None) -> dict | None:
        """Obtiene un archivo virtual de un chat específico."""
        chat = self.get_chat(wallet_address, chat_id)
        if chat:
            return chat.get_virtual_file(path, version)
        return None

    def delete_virtual_file_from_chat(self, wallet_address: str, chat_id: str, path: str) -> None:
        """Elimina un archivo virtual de un chat específico."""
        chat = self.get_chat(wallet_address, chat_id)
        if chat:
            chat.delete_virtual_file(path)
        else:
            raise ValueError(f"Chat {chat_id} not found for wallet {wallet_address}")

    def delete_chat(self, wallet_address: str, chat_id: str) -> None:
        """Elimina un chat específico."""
        if wallet_address in self.chats and chat_id in self.chats[wallet_address]:
            del self.chats[wallet_address][chat_id]
            logger.info(f"Deleted chat {chat_id} for wallet {wallet_address}")

    def get_chat_by_id(self, chat_id: str) -> Chat | None:
        """Obtiene un chat por su ID, independientemente del wallet_address."""
        for wallet_chats in self.chats.values():
            if chat_id in wallet_chats:
                return wallet_chats[chat_id]
        return None

    def clean_user_cache(self, wallet_address: str) -> None:
        """
        Limpia la caché y recursos asociados a un usuario específico.
        Esta función se llama cuando un usuario se desconecta para evitar problemas al reconectarse.
        
        Args:
            wallet_address (str): La dirección de wallet del usuario
        """
        # Obtener todos los chats del usuario
        user_chats = self.get_user_chats(wallet_address)
        
        # Para cada chat, limpiar los recursos en memoria
        for chat_info in user_chats:
            if chat_id := chat_info.get('id'):
                chat = self.get_chat(wallet_address, chat_id)
                if chat:
                    # Limpiar archivos virtuales en memoria
                    chat.virtual_files = {}
                    chat.virtual_file_history = {}
                    
                    # Mantener los mensajes, pero marcar el chat como "limpio"
                    if not hasattr(chat, 'metadata'):
                        chat.metadata = {}
                    chat.metadata['last_cleaned'] = datetime.now().isoformat()
                    chat.metadata['connection_state'] = 'disconnected'
        
        # Registrar la limpieza
        logging.info(f"Cache limpiada para el usuario {wallet_address}") 