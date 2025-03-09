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
                    role = "assistant" if msg["sender"] == "ai" else "user"
                    history.append({
                        "role": role,
                        "content": msg["text"]
                    })
                return history
        except Exception as e:
            logger.error(f"Error loading conversation history for context {context_id}: {str(e)}")
        return []

    async def process_message(self, message: str, context: Dict, context_id: str | None = None) -> AsyncGenerator[Dict, None]:
        """Processes a user message and generates responses."""
        try:
            # Validate that the message is not empty
            if not message or not message.strip():
                yield {
                    "type": "message",
                    "content": "Ready to help you with your smart contract development."
                }
                return

            # Initialize context history if it doesn't exist
            if context_id and context_id not in self.conversation_histories:
                # Load history from persistent storage
                self.conversation_histories[context_id] = self._load_conversation_history(context_id)
            
            # Update current context history
            if context_id:
                self.conversation_histories[context_id].append({
                    "role": "user",
                    "content": message
                })
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

            # Get response from Claude with optimized parameters
            response = await self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8096,  # Increased to allow more complete responses
                temperature=0.3,  # Reduced for more consistent and precise responses
                system="""You are an AI assistant specialized in Solidity smart contract development using OpenZeppelin v5.2.0.
Your primary role is to write, edit, and debug smart contracts with a focus on security and best practices.

CRITICAL RULES FOR SMART CONTRACT DEVELOPMENT:

1. When fixing errors or bugs:
   - ALWAYS provide the complete contract code with all corrections applied
     - Explain why the changes resolve the issue
   - Include all necessary imports and dependencies

2. When adding new features:
   - ALWAYS provide the complete contract code with the new functionality integrated
   - Explain how the new feature works and interacts with existing code
   - Include all necessary imports and dependencies
   - Ensure proper integration with existing functions and state variables
   - Never use // for comments, use /* */ instead
   - cuando vayas a explicar el codigo o el constructor con expresiones como new MyToken("My Token", "MTK", 6, 1000000) esta siempre deber ir enel formato **new MyToken("My Token", "MTK", 6, 1000000)**
3. Code Structure:
   - ALWAYS provide the complete contract code with all the changes applied
   - Maintain consistent formatting
   - Include comprehensive comments
   - Keep proper function ordering
   - Follow Solidity style guide
   - ALWAYS include a view function named 'owner' that returns the address of the contract owner
   - ALWAYS implement import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Pausable.sol"
   


5. Security Best Practices:
   - Implement access control
   - Add input validation
   - Use SafeMath when needed
   - Follow checks-effects-interactions pattern
   - Emit events for state changes
      
6. OpenZeppelin Integration:
   - Use latest v5.2.0 contracts
   - Use latest 0.8.20 version of solidity
   - Properly inherit and override functions
   - Implement standard interfaces
   
7. Response Format:
   - First: Explain planned changes/approach
   - Then: Show complete contract code
   - Finally: Explain security considerations
   - Use ```solidity for code blocks

8. Error Prevention:
   - Double-check all imports exist in v5.2.0
   - Verify function visibility
   - Ensure proper event emissions
   - Add input validation
   - Include require/revert messages,

9. Comment Style:
   - siempre empezar con ** cual quier explicacion incluso si es codigo o exlpiocacion del constructor cadavez que envies u nmensaje de esta clase **
   - For all other explanations and comments outside code blocks, use regular text""",
                messages=current_history,
                stop_sequences=["\```"]  # Stop after code blocks
            )
            
            if not response or not hasattr(response, 'content') or not response.content:
                raise ValueError("Invalid response from Anthropic API")

            # Save the response in the context history
            if context_id:
                self.conversation_histories[context_id].append({
                    "role": "assistant",
                    "content": response.content[0].text
                })

            # Process the response
            response_content = response.content[0].text
            yield {"type": "message", "content": "Analyzing your request..."}
            await asyncio.sleep(0.3 )  # Short initial pause

            # Analyze the response for specific actions
            actions = self.edit_actions.parse_actions(response_content)
            
            for action in actions:
                yield await self.handle_action(action, context_id)
                await asyncio.sleep(0.4)  # Pause between actions

        except Exception as api_error:
            logger.error(f"Error in Anthropic API: {str(api_error)}")
            yield {
                "type": "error",
                "content": f"Error communicating with Anthropic API: {str(api_error)}"
            }

    async def handle_action(self, action: Dict, context_id: str | None = None) -> Dict:
        """Handles a specific action and returns the appropriate response."""
        action_type = action.get("type")
        
        if action_type == "message":
            return {
                "type": "message",
                "content": action["content"]
            }
            
        elif action_type == "create_file":
            return {
                "type": "file_create",
                "content": action["content"],
                "metadata": {
                    "path": action["path"],
                    "language": "solidity"
                }
            }
            
        elif action_type == "edit_file":
            return {
                "type": "code_edit",
                "content": action["edit"]["replace"],
                "metadata": {  
                    "path": action["path"],
                    "language": "solidity"
                }
            }
            
        elif action_type == "delete_file":
            return {
                "type": "file_delete",
                "content": "",
                "metadata": {
                    "path": action["path"]
                }
            }
            
        return {
            "type": "error",
            "content": f"Unknown action type: {action_type}"
        } 