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

    async def process_message(self, message: str, context: Dict) -> AsyncGenerator[Dict, None]:
        """Procesa un mensaje del usuario y genera respuestas."""
        try:
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

When editing contracts, always ensure they follow Solidity best practices and security standards.
If you encounter compilation errors, analyze them and make the necessary fixes."""

            # Preparar el contexto actual
            current_file = context.get("currentFile")
            current_code = context.get("currentCode")
            file_system = context.get("fileSystem", {})

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
                    system=system_prompt,  # Sistema como parámetro de nivel superior
                    messages=messages,
                    temperature=0.7
                )
                
                # Verificar que la respuesta tenga el formato esperado
                if not response or not hasattr(response, 'content') or not response.content:
                    raise ValueError("Respuesta inválida de la API de Anthropic")

                # Procesar la respuesta
                response_content = response.content[0].text
                yield {"type": "message", "content": "Analyzing your request..."}

                # Analizar la respuesta para acciones específicas
                actions = self.parse_actions(response_content)
                
                for action in actions:
                    if action["type"] == "create_file":
                        yield {"type": "message", "content": f"Creating file {action['path']}..."}
                        await self.file_manager.write_file(action["path"], action["content"])
                        yield {
                            "type": "file_create",
                            "content": action["content"],
                            "metadata": {
                                "path": action["path"],
                                "language": "solidity"
                            }
                        }

                    elif action["type"] == "edit_file":
                        yield {"type": "message", "content": f"Editing file {action['path']}..."}
                        current_content = await self.file_manager.read_file(action["path"])
                        new_content = self.apply_edit(current_content, action["edit"])
                        await self.file_manager.write_file(action["path"], new_content)
                        yield {
                            "type": "code_edit",
                            "content": new_content,
                            "metadata": {
                                "path": action["path"]
                            }
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
                    fixed = await self.fix_compilation_errors(current_file, compilation_result["errors"])
                    if fixed:
                        yield {"type": "message", "content": "Successfully fixed compilation errors."}
                    else:
                        yield {"type": "message", "content": "Could not automatically fix all compilation errors."}

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
        current_action = None

        for line in lines:
            if line.startswith("```solidity"):
                current_action = {
                    "type": "create_file",
                    "path": f"contracts/Contract_{len(actions)}.sol",
                    "content": ""
                }
            elif line.startswith("```") and current_action:
                if current_action["content"]:
                    actions.append(current_action)
                current_action = None
            elif current_action:
                current_action["content"] += line + "\n"
            elif line.strip():
                actions.append({
                    "type": "message",
                    "content": line
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