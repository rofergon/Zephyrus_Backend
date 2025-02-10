import os
import json
import logging
import asyncio
from typing import Dict, List, AsyncGenerator
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from file_manager import FileManager

load_dotenv()
logger = logging.getLogger(__name__)

class Agent:
    def __init__(self, file_manager: FileManager):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no encontrada en las variables de entorno")
        self.anthropic = AsyncAnthropic(api_key=api_key)
        self.file_manager = file_manager
        self.conversation_history: List[Dict] = []
        self.max_retries = 3
        self.max_compilation_attempts = 5
        # Add persistent context
        self.current_contract_context = {
            "file": None,
            "code": None,
            "file_system": {}
        }

    async def process_message(self, message: str, context: Dict) -> AsyncGenerator[Dict, None]:
        """Procesa un mensaje del usuario y genera respuestas."""
        try:
            # Update contract context if provided in the message
            if context.get("currentFile"):
                self.current_contract_context["file"] = context["currentFile"]
            if context.get("currentCode"):
                self.current_contract_context["code"] = context["currentCode"]
            if context.get("fileSystem"):
                self.current_contract_context["file_system"] = context["fileSystem"]

            # Añadir el mensaje del usuario al historial
            self.conversation_history.append({
                "role": "user",
                "content": message
            })

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
- When explaining steps or processes, send each explanation as a separate message with a brief pause between them

Contract Template Format:
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract ContractName {
    // Contract code here
}
```

If you encounter compilation errors, analyze them and make the necessary fixes."""

            # Preparar el contexto actual usando el estado persistente
            current_file = self.current_contract_context["file"]
            current_code = self.current_contract_context["code"]

            # Construir los mensajes para Claude
            messages = [*self.conversation_history]

            if current_file and current_code:
                messages.append({
                    "role": "user",
                    "content": f"Current file: {current_file}\nCurrent code:\n```solidity\n{current_code}\n```"
                })

            try:
                # Obtener la respuesta de Claude con manejo de errores específico
                response = await self.anthropic.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    temperature=0.7
                )
                
                # Verificar que la respuesta tenga el formato esperado
                if not response or not hasattr(response, 'content') or not response.content:
                    raise ValueError("Respuesta inválida de la API de Anthropic")

                # Procesar la respuesta
                response_content = response.content[0].text
                yield {"type": "message", "content": "Analyzing your request..."}
                await asyncio.sleep(0.5)  # Pequeña pausa inicial

                # Analizar la respuesta para acciones específicas
                actions = self.parse_actions(response_content)
                
                for action in actions:
                    if action["type"] == "create_file":
                        yield {"type": "message", "content": f"Creating file {action['path']}..."}
                        await asyncio.sleep(0.3)  # Pausa antes de crear el archivo
                        await self.file_manager.write_file(action["path"], action["content"])
                        yield {
                            "type": "file_create",
                            "content": action["content"],
                            "metadata": {
                                "path": action["path"],
                                "language": "solidity"
                            }
                        }
                        await asyncio.sleep(0.5)  # Pausa después de crear el archivo

                    elif action["type"] == "edit_file":
                        yield {"type": "message", "content": f"Editing file {action['path']}..."}
                        await asyncio.sleep(0.3)
                        
                        try:
                            # Leer el contenido actual del archivo
                            current_content = await self.file_manager.read_file(action["path"])
                            # Aplicar la edición
                            new_content = self.apply_edit(current_content, action["edit"])
                            # Escribir el nuevo contenido
                            await self.file_manager.write_file(action["path"], new_content)
                            
                            # Actualizar el contexto si es el archivo actual
                            if action["path"] == self.current_contract_context["file"]:
                                self.current_contract_context["code"] = new_content
                                logger.info(f"Updated context for file {action['path']}")
                            
                            # Enviar la actualización al cliente
                            yield {
                                "type": "code_edit",
                                "content": new_content,
                                "metadata": {
                                    "path": action["path"],
                                    "language": "solidity"
                                }
                            }
                            
                            await asyncio.sleep(0.5)
                            
                        except Exception as edit_error:
                            logger.error(f"Error editing file {action['path']}: {str(edit_error)}")
                            yield {
                                "type": "error",
                                "content": f"Error editing file: {str(edit_error)}"
                            }

                    elif action["type"] == "delete_file":
                        yield {"type": "message", "content": f"Deleting file {action['path']}..."}
                        await self.file_manager.delete_file(action["path"])
                        yield {
                            "type": "file_delete",
                            "content": "",
                            "metadata": {
                                "path": action["path"]
                            }
                        }

                    elif action["type"] == "message":
                        yield {
                            "type": "message",
                            "content": action["content"]
                        }
                        await asyncio.sleep(0.4)  # Pausa entre mensajes

            except Exception as api_error:
                logger.error(f"Error en la API de Anthropic: {str(api_error)}")
                yield {
                    "type": "error",
                    "content": f"Error al comunicarse con la API de Anthropic: {str(api_error)}"
                }
                return

            # Si hay un archivo actual, verificar errores de compilación
            if current_file and current_file.endswith('.sol'):
                compilation_result = await self.file_manager.compile_solidity(current_file)
                if not compilation_result["success"]:
                    yield {"type": "message", "content": "Found compilation errors. Attempting to fix..."}
                    await asyncio.sleep(0.5)  # Pausa antes de intentar arreglar errores
                    fixed = await self.fix_compilation_errors(current_file, compilation_result["errors"])
                    if fixed:
                        yield {"type": "message", "content": "Successfully fixed compilation errors."}
                    else:
                        yield {"type": "message", "content": "Could not automatically fix all compilation errors."}
                    await asyncio.sleep(0.5)  # Pausa final

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error: {str(e)}"
            }

    def parse_actions(self, response: str) -> List[Dict]:
        """Analiza la respuesta de Claude para extraer acciones."""
        actions = []
        lines = response.split('\n')
        in_code_block = False
        code_content = ""
        is_suggestion_block = False
        
        # Si hay un contrato actual, cualquier código solidity debería ser una edición
        is_editing_mode = self.current_contract_context["file"] is not None

        for i, line in enumerate(lines):
            # Detectar si es una sugerencia antes del bloque de código
            if not in_code_block and any(keyword in line.lower() for keyword in ["suggestion:", "idea:", "you could:", "consider:", "recommendation:", "proposal:"]):
                is_suggestion_block = True
                actions.append({
                    "type": "message",
                    "content": line.strip()
                })
                continue

            # Detectar inicio de bloque de código
            if line.startswith("```solidity"):
                in_code_block = True
                code_content = ""
                continue
            # Detectar fin de bloque de código
            elif line.startswith("```") and in_code_block:
                in_code_block = False
                if code_content.strip():
                    # Si es un bloque de sugerencia, solo mostrar el código como mensaje
                    if is_suggestion_block:
                        actions.append({
                            "type": "message",
                            "content": f"Example code:\n```solidity\n{code_content.strip()}\n```"
                        })
                    # Si no es sugerencia y hay un contrato actual, editar
                    elif is_editing_mode:
                        actions.append({
                            "type": "edit_file",
                            "path": self.current_contract_context["file"],
                            "edit": {"replace": code_content.strip()}
                        })
                        # Actualizar el contexto inmediatamente
                        self.current_contract_context["code"] = code_content.strip()
                    # Si no es sugerencia y no hay contrato actual, crear nuevo
                    else:
                        actions.append({
                            "type": "create_file",
                            "path": f"contracts/Contract_{len(actions)}.sol",
                            "content": code_content.strip()
                        })
                is_suggestion_block = False
                continue
            # Acumular contenido del bloque de código
            elif in_code_block:
                code_content += line + "\n"
            # Si la línea no es parte de un bloque de código y no está vacía
            elif line.strip():
                actions.append({
                    "type": "message",
                    "content": line.strip()
                })

        return actions

    def apply_edit(self, current_content: str, edit: Dict) -> str:
        """Aplica una edición a un contenido existente."""
        if "replace" in edit:
            return edit["replace"]
        
        if "insert" in edit:
            lines = current_content.splitlines()
            lines.insert(edit["line"] - 1, edit["insert"])
            return "\n".join(lines)
        
        return current_content

    async def fix_compilation_errors(self, file_path: str, errors: List[Dict]) -> bool:
        """Intenta corregir errores de compilación automáticamente."""
        attempts = 0
        while attempts < self.max_compilation_attempts:
            try:
                # Obtener el contenido actual
                content = await self.file_manager.read_file(file_path)
                
                # Crear un mensaje para Claude con los errores
                error_message = "Fix the following Solidity compilation errors:\n"
                for error in errors:
                    error_message += f"Line {error['line']}: {error['message']}\n"
                error_message += f"\nCurrent code:\n```solidity\n{content}\n```"

                # Obtener la solución de Claude
                response = await self.anthropic.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=4096,
                    system="You are a Solidity expert. Fix the compilation errors in the contract.",
                    messages=[
                        {"role": "user", "content": error_message}
                    ],
                    temperature=0.3
                )

                # Extraer el código corregido
                fixed_code = self.extract_solidity_code(response.content[0].text)
                if fixed_code:
                    # Aplicar la corrección
                    await self.file_manager.write_file(file_path, fixed_code)
                    
                    # Verificar si se resolvieron los errores
                    new_result = await self.file_manager.compile_solidity(file_path)
                    if new_result["success"]:
                        return True
                
                attempts += 1
            except Exception as e:
                logger.error(f"Error fixing compilation errors: {str(e)}")
                break

        return False

    def extract_solidity_code(self, text: str) -> str:
        """Extrae el código Solidity de una respuesta de texto."""
        start = text.find("```solidity")
        if start == -1:
            start = text.find("```")
        if start == -1:
            return ""
        
        end = text.find("```", start + 3)
        if end == -1:
            return ""
        
        code = text[start:end].strip()
        code = code.replace("```solidity", "").replace("```", "").strip()
        return code 