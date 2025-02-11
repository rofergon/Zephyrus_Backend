import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class EditActions:
    def __init__(self):
        self.current_contract_context = {
            "file": None,
            "code": None,
            "file_system": {}
        }

    def parse_actions(self, response: str) -> List[Dict]:
        """Analiza la respuesta para extraer acciones."""
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

    def update_contract_context(self, file: str = None, code: str = None, file_system: dict = None):
        """Actualiza el contexto del contrato actual."""
        if file is not None:
            self.current_contract_context["file"] = file
        if code is not None:
            self.current_contract_context["code"] = code
        if file_system is not None:
            self.current_contract_context["file_system"] = file_system 