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
        """Carga el historial de conversación desde el almacenamiento persistente."""
        try:
            # Obtener el chat del ChatManager directamente
            chat = self.chat_manager.get_chat_by_id(context_id)
            if chat:
                # Convertir los mensajes al formato esperado por el historial de conversación
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
        """Procesa un mensaje del usuario y genera respuestas."""
        try:
            # Validar que el mensaje no esté vacío
            if not message or not message.strip():
                yield {
                    "type": "message",
                    "content": "Ready to help you with your smart contract development."
                }
                return

            # Inicializar el historial del contexto si no existe
            if context_id and context_id not in self.conversation_histories:
                # Cargar el historial desde el almacenamiento persistente
                self.conversation_histories[context_id] = self._load_conversation_history(context_id)
            
            # Actualizar el historial del contexto actual
            if context_id:
                self.conversation_histories[context_id].append({
                    "role": "user",
                    "content": message
                })
                current_history = self.conversation_histories[context_id]
            else:
                # Si no hay context_id, usar un historial temporal
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

            # Obtener la respuesta de Claude con parámetros optimizados
            response = await self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8096,  # Aumentado para permitir respuestas más completas
                temperature=0.4,  # Reducido para respuestas más consistentes y precisas
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

3. Code Structure:
   - Maintain consistent formatting
   - Include comprehensive comments
   - Keep proper function ordering
   - Follow Solidity style guide
   - ALWAYS include a view function named 'owner' that returns the address of the contract owner

4. Security Best Practices:
   - Implement access control
   - Add input validation
   - Use SafeMath when needed
   - Follow checks-effects-interactions pattern
   - Emit events for state changes
      
5. OpenZeppelin Integration:
   - Use latest v5.2.0 contracts
   - Properly inherit and override functions
   - Implement standard interfaces
   
6. Response Format:
   - First: Explain planned changes/approach
   - Then: Show complete contract code
   - Finally: Explain security considerations
   - Use ```solidity for code blocks

7. Error Prevention:
   - Double-check all imports exist in v5.2.0
   - Verify function visibility
   - Ensure proper event emissions
   - Add input validation
   - Include require/revert messages

8. Comment Style:
   - Use // style comments ONLY for Solidity contract code (e.g. SPDX-License, pragma, etc.)
   - For all other explanations and comments outside code blocks, use regular text""",
                messages=current_history,
                stop_sequences=["\```"]  # Detener después de bloques de código
            )
            
            if not response or not hasattr(response, 'content') or not response.content:
                raise ValueError("Respuesta inválida de la API de Anthropic")

            # Guardar la respuesta en el historial del contexto
            if context_id:
                self.conversation_histories[context_id].append({
                    "role": "assistant",
                    "content": response.content[0].text
                })

            # Procesar la respuesta
            response_content = response.content[0].text
            yield {"type": "message", "content": "Analyzing your request..."}
            await asyncio.sleep(0.3 )  # Pequeña pausa inicial

            # Analizar la respuesta para acciones específicas
            actions = self.edit_actions.parse_actions(response_content)
            
            for action in actions:
                yield await self.handle_action(action, context_id)
                await asyncio.sleep(0.4)  # Pausa entre acciones

        except Exception as api_error:
            logger.error(f"Error en la API de Anthropic: {str(api_error)}")
            yield {
                "type": "error",
                "content": f"Error al comunicarse con la API de Anthropic: {str(api_error)}"
            }

    async def handle_action(self, action: Dict, context_id: str | None = None) -> Dict:
        """Maneja una acción específica y retorna la respuesta apropiada."""
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