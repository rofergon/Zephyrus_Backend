import os
import logging
from typing import Dict, AsyncGenerator
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from file_manager import FileManager
from session_manager import ChatManager
from actions import CompilationActions, EditActions, MessageActions
from datetime import datetime

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

    async def process_message(self, message: str, context: Dict, context_id: str | None = None, wallet_address: str = None) -> AsyncGenerator[Dict, None]:
        """Process a message through message actions."""
        # Validate message format
        if isinstance(message, dict) and "content" in message:
            # Extract content if message is in dict format
            message_content = message["content"]
        else:
            # Use as is if it's already a string
            message_content = str(message)
            
        try:
            async for response in self.message_actions.process_message(message_content, context, context_id, wallet_address):
                # Store message in chat history if context_id provided
                if context_id:
                    # Store user message
                    user_message = {
                        "text": message_content,
                        "sender": "user",
                        "timestamp": datetime.now().isoformat()
                    }
                    self.chat_manager.add_message_to_chat(
                        wallet_address or "anonymous",
                        context_id,
                        user_message
                    )
                    
                    # Store AI response
                    ai_message = {
                        "text": response.get("content", ""),
                        "sender": "ai",
                        "timestamp": datetime.now().isoformat()
                    }
                    self.chat_manager.add_message_to_chat(
                        wallet_address or "anonymous",
                        context_id,
                        ai_message
                    )
                    
                yield response
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error processing message: {str(e)}"
            } 