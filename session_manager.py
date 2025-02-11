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
    def __init__(self, session_id: str, client_id: str, wallet_address: str | None = None):
        self.session_id = session_id
        self.client_id = client_id
        self.wallet_address = wallet_address
        self.created_at = datetime.now().isoformat()
        self.last_accessed = datetime.now().isoformat()
        self.contexts: List[Dict] = [{
            "id": str(uuid.uuid4()),
            "name": "Main Chat",
            "type": "chat",
            "timestamp": datetime.now().timestamp() * 1000,
            "content": "",
            "active": True,
            "messages": []
        }]
        logger.info(f"Created new session: {session_id} for client: {client_id} with wallet: {wallet_address}")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "client_id": self.client_id,
            "wallet_address": self.wallet_address,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "contexts": self.contexts
        }

    def get_context(self, context_id: str) -> Dict | None:
        return next((ctx for ctx in self.contexts if ctx["id"] == context_id), None)

    def add_message_to_context(self, context_id: str, message: Dict) -> None:
        context = self.get_context(context_id)
        if context:
            if "messages" not in context:
                context["messages"] = []
            context["messages"].append(message)
        else:
            raise ValueError(f"Context {context_id} not found")

    def create_context(self, name: str) -> Dict:
        # Desactivar todos los contextos existentes
        for context in self.contexts:
            context["active"] = False

        # Crear nuevo contexto
        new_context = {
            "id": str(uuid.uuid4()),
            "name": name,
            "type": "chat",
            "timestamp": datetime.now().timestamp() * 1000,
            "content": "",
            "active": True,
            "messages": []
        }
        self.contexts.append(new_context)
        return new_context

    def switch_context(self, context_id: str) -> Dict:
        context_found = False
        for context in self.contexts:
            if context["id"] == context_id:
                context["active"] = True
                context_found = True
            else:
                context["active"] = False

        if not context_found:
            raise ValueError(f"Context {context_id} not found")

        return self.get_context(context_id)

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
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
            return
            
        self.sessions.clear()
        
        for filename in os.listdir(self.base_path):
            if filename.endswith(".json"):
                session_path = os.path.join(self.base_path, filename)
                try:
                    with open(session_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        session = Session(
                            data["session_id"],
                            data["client_id"],
                            data.get("wallet_address")
                        )
                        session.created_at = data["created_at"]
                        session.last_accessed = data["last_accessed"]
                        session.contexts = data.get("contexts", [])
                        self.sessions[session.session_id] = session
                except Exception as e:
                    logger.error(f"Error loading session {filename}: {str(e)}")

    def create_session(self, client_id: str, wallet_address: str | None = None) -> Session:
        """Crea una nueva sesión"""
        session_id = str(uuid.uuid4())
        session = Session(session_id, client_id, wallet_address)
        
        if wallet_address:
            for existing_session in self.sessions.values():
                if existing_session.wallet_address == wallet_address:
                    existing_session.client_id = client_id
                    self._save_session(existing_session)
                    return existing_session
        
        self.sessions[session_id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Obtiene una sesión por su ID"""
        session = self.sessions.get(session_id)
        if session:
            session.last_accessed = datetime.now().isoformat()
            self._save_session(session)
        return session

    def _save_session(self, session: Session):
        """Guarda una sesión en disco"""
        try:
            if not os.path.exists(self.base_path):
                os.makedirs(self.base_path)
                
            session_path = self._get_session_path(session.session_id)
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving session {session.session_id}: {str(e)}")

    def get_session_contexts(self, session_id: str) -> List[Dict]:
        """Obtiene los contextos de una sesión"""
        session = self.get_session(session_id)
        if session:
            return session.contexts
        return []

    def create_context(self, session_id: str, name: str) -> Dict:
        """Crea un nuevo contexto en una sesión"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        new_context = session.create_context(name)
        self._save_session(session)
        return new_context

    def switch_context(self, session_id: str, context_id: str) -> Dict:
        """Cambia el contexto activo en una sesión"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        switched_context = session.switch_context(context_id)
        self._save_session(session)
        return switched_context

    def add_message_to_context(self, session_id: str, context_id: str, message: Dict) -> None:
        """Añade un mensaje a un contexto específico"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.add_message_to_context(context_id, message)
        self._save_session(session) 