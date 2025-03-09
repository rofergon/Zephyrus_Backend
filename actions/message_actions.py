import logging
from typing import Dict, List, AsyncGenerator
import asyncio
import uuid
from datetime import datetime
from session_manager import ChatManager

logger = logging.getLogger(__name__)

class MessageActions:
    def __init__(self, anthropic_client, edit_actions, compilation_actions, chat_manager: ChatManager):
        self.anthropic = anthropic_client
        self.edit_actions = edit_actions
        self.compilation_actions = compilation_actions
        self.chat_manager = chat_manager
        self.conversation_histories: Dict[str, List[Dict]] = {}
        self.max_retries = 3

    def _load_conversation_history(self, context_id: str) -> List[Dict]:
        """Loads the conversation history from persistent storage."""
        try:
            # Get the chat directly from ChatManager
            chat = self.chat_manager.get_chat_by_id(context_id)
            if chat:
                # Convert messages to the format expected by the conversation history
                history = []
                for msg in chat.messages:
                    if "text" in msg and "sender" in msg:
                        role = "assistant" if msg["sender"] == "ai" else "user"
                        content = msg["text"]
                        
                        # Ensure content is a string
                        if not isinstance(content, str):
                            content = str(content)
                            
                        history.append({
                            "role": role,
                            "content": content
                        })
                return history
        except Exception as e:
            logger.error(f"Error loading conversation history for context {context_id}: {str(e)}")
        return []

    async def process_message(self, message: str, context: Dict, context_id: str | None = None, wallet_address: str = None) -> AsyncGenerator[Dict, None]:
        """Process a message and return the response."""
        try:
            # Skip processing for empty messages
            if not message.strip():
                yield {
                    "sender": "ai",
                    "timestamp": datetime.now().isoformat(),
                    "type": "message",
                    "content": "Ready to help you with your smart contract development.",
                    "wallet_address": wallet_address
                }
                return

            # Initialize context history if it doesn't exist
            if context_id and context_id not in self.conversation_histories:
                # Load history from persistent storage
                self.conversation_histories[context_id] = self._load_conversation_history(context_id)
            
            # Update current context history
            if context_id:
                # Ensure message is properly formatted
                user_message = {
                    "role": "user",
                    "content": message
                }
                self.conversation_histories[context_id].append(user_message)
                current_history = self.conversation_histories[context_id]
            else:
                # If there's no context_id, use a temporary history
                current_history = [{
                    "role": "user",
                    "content": message
                }]

            # Update contract context if provided in the message
            if context.get("currentFile"):
                self.edit_actions.update_contract_context(
                    file=context["currentFile"],
                    code=context.get("currentCode"),
                    file_system=context.get("fileSystem", {})
                )

            # Ensure all message formats are valid for Anthropic API
            formatted_history = []
            for msg in current_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    # Check if content should be formatted as a list
                    if isinstance(msg["content"], list):
                        # Already a list, keep it
                        formatted_msg = msg
                    else:
                        # Convert to text if it's not already a list
                        formatted_msg = {
                            "role": msg["role"],
                            "content": str(msg["content"])
                        }
                    formatted_history.append(formatted_msg)

            # Get response from Claude with optimized parameters
            try:
                response = await self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=8096,  # Increased to allow more complete responses
                    temperature=0.3,  # Reduced for more consistent and precise responses
                    system="""You are an AI assistant specialized in Solidity smart contract development using OpenZeppelin v5.2.0.
Your primary role is to write, edit, and debug smart contracts with a focus on security and best practices.""",
                    messages=formatted_history,
                    stop_sequences=["\```"]  # Stop after code blocks
                )
                
                # Extract content from the response
                if hasattr(response, 'content') and response.content:
                    response_content = response.content[0].text
                else:
                    response_content = str(response)
                    
            except Exception as e:
                logger.error(f"Error in Anthropic API: {str(e)}")
                yield {
                    "type": "error",
                    "content": f"Error communicating with Anthropic API: {str(e)}",
                    "wallet_address": wallet_address
                }
                return

            # Send initial response
            yield {
                "type": "message", 
                "content": response_content,
                "sender": "ai",
                "timestamp": datetime.now().isoformat(),
                "wallet_address": wallet_address
            }
            
            # Short pause before analyzing
            await asyncio.sleep(0.3)

            # Analyze the response for specific actions
            actions = self.edit_actions.parse_actions(response_content)
            
            for action in actions:
                yield await self.handle_action(action, context_id, wallet_address)
                await asyncio.sleep(0.4)  # Pause between actions
            
            # Add the assistant response to the conversation history
            if context_id:
                self.conversation_histories[context_id].append({
                    "role": "assistant",
                    "content": response_content
                })
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error processing message: {str(e)}",
                "wallet_address": wallet_address
            }

    async def handle_action(self, action: Dict, context_id: str | None = None, wallet_address: str = None) -> Dict:
        """Handles a specific action and returns a response."""
        action_type = action.get("type")
        try:
            if action_type == "edit" or action_type == "file_create":
                # Process file edits and creation
                result = self.edit_actions.handle_edit_action(action)
                if "error" in result:
                    logger.error(f"Edit action error: {result['error']}")
                    return {
                        "type": "error",
                        "content": f"Error in edit action: {result['error']}",
                        "wallet_address": wallet_address
                    }
                
                # Success - format the response based on the action type
                if action_type == "edit":
                    response = {
                        "type": "code_edit",
                        "content": result["content"],
                        "metadata": {
                            "path": result["path"],
                            "language": result.get("language", "solidity")
                        },
                        "wallet_address": wallet_address
                    }
                else:  # file_create
                    response = {
                        "type": "file_create",
                        "content": result["content"],
                        "metadata": {
                            "path": result["path"],
                            "language": result.get("language", "solidity")
                        },
                        "wallet_address": wallet_address
                    }
                
                # Save virtual file in chat if context_id is provided
                if context_id and "path" in result and "content" in result:
                    try:
                        self.chat_manager.add_virtual_file_to_chat(
                            wallet_address or "anonymous",
                            context_id,
                            result["path"],
                            result["content"],
                            result.get("language", "solidity")
                        )
                    except Exception as e:
                        logger.error(f"Error saving virtual file: {str(e)}")
                
                return response
            
            elif action_type == "delete_file":
                return {
                    "type": "file_delete",
                    "content": f"File {action.get('path', 'unknown')} deleted successfully.",
                    "metadata": {
                        "path": action.get("path", "unknown")
                    },
                    "wallet_address": wallet_address
                }
                
            elif action_type == "compile":
                result = await self.compilation_actions.compile_contract(action["contract"])
                return {
                    "type": "compilation_result",
                    "content": result["output"],
                    "metadata": {
                        "success": result["success"],
                        "warnings": result.get("warnings", []),
                        "errors": result.get("errors", [])
                    },
                    "wallet_address": wallet_address
                }
                
            elif action_type == "message":
                return {
                    "type": "message",
                    "content": action["content"],
                    "wallet_address": wallet_address
                }
                
            else:
                logger.warning(f"Unknown action type: {action_type}")
                return {
                    "type": "error",
                    "content": f"Unknown action type: {action_type}",
                    "wallet_address": wallet_address
                }
                
        except Exception as e:
            logger.error(f"Error handling action: {str(e)}")
            return {
                "type": "error",
                "content": f"Error handling action: {str(e)}",
                "wallet_address": wallet_address
            } 