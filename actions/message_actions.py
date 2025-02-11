import logging
from typing import Dict, List, AsyncGenerator
import asyncio
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class MessageActions:
    def __init__(self, anthropic_client, edit_actions, compilation_actions):
        self.anthropic = anthropic_client
        self.edit_actions = edit_actions
        self.compilation_actions = compilation_actions
        self.conversation_histories: Dict[str, List[Dict]] = {}
        self.max_retries = 3

    async def process_message(self, message: str, context: Dict, context_id: str | None = None) -> AsyncGenerator[Dict, None]:
        """Procesa un mensaje del usuario y genera respuestas."""
        try:
            # Inicializar el historial del contexto si no existe
            if context_id and context_id not in self.conversation_histories:
                self.conversation_histories[context_id] = []
            
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

            # Preparar el contexto del sistema
            system_prompt = """You are an AI assistant specialized in Solidity smart contract development.
Your task is to help users write, edit, and debug smart contracts. You can:
1. Read and analyze contract code
2. Create new contracts
3. Edit existing contracts
4. Fix compilation errors
5. Manage files and directories

Important guidelines for code handling:
- ALWAYS use Solidity version 0.8.20 for all contracts (pragma solidity ^0.8.20;)
- When asked for suggestions or ideas, prefix them with "Suggestion:" or "Idea:" and show example code in ```solidity blocks
- Only CREATE or EDIT contracts when explicitly asked to do so
- When showing example code as part of a suggestion, wrap it in ```solidity blocks
- When actually creating or editing a contract, use ```solidity blocks and be explicit about the action
- Always include SPDX-License-Identifier and pragma statements in new contracts
- When editing contracts, always ensure they follow Solidity best practices and security standards
- Never delete or completely replace an existing contract unless explicitly requested
- Always preserve the existing contract structure and functionality when making edits
- If you need to make significant changes, first explain what you plan to do and wait for approval
- When explaining steps or processes, send each explanation as a separate message with a brief pause between them"""

            try:
                # Obtener la respuesta de Claude
                response = await self.anthropic.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=current_history,
                    temperature=0.7
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
                await asyncio.sleep(0.5)  # Pequeña pausa inicial

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

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error: {str(e)}"
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