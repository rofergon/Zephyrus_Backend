import os
import logging
from typing import Dict, AsyncGenerator
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from file_manager import FileManager
from session_manager import ChatManager
from actions import CompilationActions, EditActions, MessageActions

load_dotenv()
logger = logging.getLogger(__name__)

class Agent:
    def __init__(self, file_manager: FileManager, chat_manager: ChatManager):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.anthropic = AsyncAnthropic(api_key=api_key)
        self.file_manager = file_manager
        self.chat_manager = chat_manager
        
        # Initialize actions
        self.edit_actions = EditActions()
        self.compilation_actions = CompilationActions(self.anthropic, self.file_manager)
        self.message_actions = MessageActions(self.anthropic, self.edit_actions, self.compilation_actions, self.chat_manager)

    async def process_message(self, message: str, context: Dict, context_id: str | None = None) -> AsyncGenerator[Dict, None]:
        """Processes a user message and generates responses."""
        async for response in self.message_actions.process_message(message, context, context_id):
            yield response 