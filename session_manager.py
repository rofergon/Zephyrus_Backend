import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import uuid
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Session:
    def __init__(self, session_id: str, name: str, client_id: str, wallet_address: str | None = None):
        self.session_id = session_id
        self.name = name
        self.client_id = client_id
        self.wallet_address = wallet_address
        self.created_at = datetime.now().isoformat()
        self.last_accessed = datetime.now().isoformat()
        self.files: Dict[str, str] = {}  # path -> content
        self.conversation_history: List[Dict] = []
        logger.info(f"Created new session: {session_id} for client: {client_id} with wallet: {wallet_address}")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "client_id": self.client_id,
            "wallet_address": self.wallet_address,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "files": self.files,
            "conversation_history": self.conversation_history
        }

class SessionManager:
    def __init__(self, base_path: str = "./sessions"):
        self.base_path = base_path
        self.sessions: Dict[str, Session] = {}
        self._ensure_base_path()
        self._load_sessions()

    def _ensure_base_path(self):
        """Asegura que existe el directorio base para las sesiones"""
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    def _get_session_path(self, session_id: str) -> str:
        """Obtiene la ruta completa para una sesión"""
        return os.path.join(self.base_path, f"{session_id}.json")

    def _load_sessions(self):
        """Carga todas las sesiones guardadas"""
        logger.info(f"Loading sessions from directory: {self.base_path}")
        
        if not os.path.exists(self.base_path):
            logger.info("Sessions directory does not exist, creating it")
            os.makedirs(self.base_path)
            return
            
        # Limpiar las sesiones existentes
        self.sessions.clear()
        logger.info("Cleared existing sessions from memory")
            
        for filename in os.listdir(self.base_path):
            if filename.endswith(".json"):
                session_path = os.path.join(self.base_path, filename)
                logger.info(f"Found session file: {filename}")
                try:
                    with open(session_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        session = Session(
                            data["session_id"],
                            data["name"],
                            data["client_id"],
                            data.get("wallet_address")
                        )
                        session.created_at = data["created_at"]
                        session.last_accessed = data["last_accessed"]
                        session.files = data.get("files", {})
                        session.conversation_history = data.get("conversation_history", [])
                        self.sessions[session.session_id] = session
                        logger.info(f"Loaded session: {session.session_id} for client: {session.client_id}")
                except Exception as e:
                    logger.error(f"Error loading session {filename}: {str(e)}")

    def create_session(self, name: str, client_id: str, wallet_address: str | None = None) -> Session:
        """Crea una nueva sesión"""
        session_id = str(uuid.uuid4())
        session = Session(session_id, name, client_id, wallet_address)
        
        # Si hay una wallet_address, actualizar el client_id de todas las sesiones existentes de esa wallet
        if wallet_address:
            for existing_session in self.sessions.values():
                if existing_session.wallet_address == wallet_address:
                    existing_session.client_id = client_id
                    self._save_session(existing_session)
        
        self.sessions[session_id] = session
        self._save_session(session)
        logger.info(f"Created new session: {session_id} for client: {client_id} with wallet: {wallet_address}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Obtiene una sesión por su ID"""
        session = self.sessions.get(session_id)
        if session:
            session.last_accessed = datetime.now().isoformat()
            self._save_session(session)
        return session

    def get_client_sessions(self, client_id: str, wallet_address: str | None = None) -> List[Session]:
        """Obtiene todas las sesiones de un cliente, opcionalmente filtradas por billetera"""
        logger.info(f"Getting sessions for client: {client_id} with wallet: {wallet_address}")
        logger.info(f"Total sessions in memory: {len(self.sessions)}")
        
        if wallet_address:
            # Si hay wallet_address, devolver todas las sesiones de esa wallet sin importar el client_id
            sessions = [s for s in self.sessions.values() if s.wallet_address == wallet_address]
            logger.info(f"Found {len(sessions)} sessions for wallet {wallet_address}")
        else:
            # Si no hay wallet_address, usar el client_id
            sessions = [s for s in self.sessions.values() if s.client_id == client_id]
            logger.info(f"Found {len(sessions)} sessions for client {client_id}")
        
        # Ordenar por última accedida
        sessions.sort(key=lambda x: x.last_accessed, reverse=True)
        
        for session in sessions:
            logger.info(f"Session details - ID: {session.session_id}, Name: {session.name}, Wallet: {session.wallet_address}")
        
        return sessions

    def update_session_files(self, session_id: str, files: Dict[str, str]):
        """Actualiza los archivos de una sesión"""
        session = self.get_session(session_id)
        if session:
            session.files = files
            session.last_accessed = datetime.now().isoformat()
            self._save_session(session)

    def add_to_conversation_history(self, session_id: str, message: Dict):
        """Añade un mensaje al historial de conversación"""
        session = self.get_session(session_id)
        if session:
            session.conversation_history.append(message)
            session.last_accessed = datetime.now().isoformat()
            self._save_session(session)

    def _save_session(self, session: Session):
        """Guarda una sesión en disco"""
        try:
            if not os.path.exists(self.base_path):
                logger.info(f"Creating sessions directory: {self.base_path}")
                os.makedirs(self.base_path)
                
            session_path = self._get_session_path(session.session_id)
            logger.info(f"Saving session to: {session_path}")
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(session_path), exist_ok=True)
            
            # Guardar con codificación UTF-8
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Successfully saved session: {session.session_id}")
        except Exception as e:
            logger.error(f"Error saving session {session.session_id}: {str(e)}")

    def delete_session(self, session_id: str):
        """Elimina una sesión"""
        logger.info(f"Attempting to delete session: {session_id}")
        if session_id in self.sessions:
            try:
                session_path = self._get_session_path(session_id)
                logger.info(f"Deleting session file: {session_path}")
                
                # Eliminar el archivo si existe
                if os.path.exists(session_path):
                    os.remove(session_path)
                    logger.info(f"Session file deleted successfully: {session_path}")
                else:
                    logger.warning(f"Session file not found: {session_path}")
                
                # Eliminar la sesión de la memoria
                del self.sessions[session_id]
                logger.info(f"Session removed from memory: {session_id}")
                
                return True
            except Exception as e:
                logger.error(f"Error deleting session {session_id}: {str(e)}")
                raise Exception(f"Failed to delete session: {str(e)}")
        else:
            logger.warning(f"Session not found for deletion: {session_id}")
            return False

    def rename_session(self, session_id: str, new_name: str):
        """Renombra una sesión y su archivo JSON"""
        session = self.get_session(session_id)
        if session:
            old_path = self._get_session_path(session_id)
            session.name = new_name
            session.last_accessed = datetime.now().isoformat()
            
            # Guardar con el nuevo nombre
            self._save_session(session)
            
            # Si el archivo anterior existe y es diferente al nuevo, eliminarlo
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception as e:
                    print(f"Error removing old session file: {str(e)}")
        else:
            raise ValueError(f"Session {session_id} not found") 