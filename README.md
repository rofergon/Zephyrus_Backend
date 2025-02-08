# Smart Contract AI Assistant Backend

Este es el backend para el asistente AI de contratos inteligentes. Proporciona una interfaz WebSocket para comunicarse con un agente AI que puede ayudar a escribir, editar y depurar contratos Solidity.

## Características

- Integración con Claude AI de Anthropic para asistencia inteligente
- Comunicación en tiempo real mediante WebSocket
- Manejo de archivos y directorios
- Compilación y validación de contratos Solidity
- Corrección automática de errores de compilación
- Sistema de caché de archivos para mejor rendimiento
- Soporte para múltiples clientes simultáneos
- Generación automática de IDs de cliente

## Requisitos

- Python 3.8 o superior
- Una clave API de Anthropic (Claude)
- Solidity Compiler (solc) instalado en el sistema

## Instalación

1. Clonar el repositorio:
```bash
git clone <url-del-repositorio>
cd <nombre-del-directorio>
```

2. Crear un entorno virtual:
```bash
# En Windows
python -m venv venv
.\venv\Scripts\activate

# En Linux/Mac
python -m venv venv
source venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
- Copiar `.env.example` a `.env`
- Agregar tu clave API de Anthropic en `ANTHROPIC_API_KEY`
- Ajustar otras configuraciones según sea necesario

## Uso

1. Iniciar el servidor:
```bash
python main.py
```

El servidor se iniciará en `http://localhost:8000` con dos endpoints WebSocket disponibles:
- `ws://localhost:8000/ws/agent` - Conexión sin ID de cliente (se genera automáticamente)
- `ws://localhost:8000/ws/agent/{client_id}` - Conexión con ID de cliente específico

### Ejemplo de conexión WebSocket

```javascript
// Conexión sin ID de cliente
const ws = new WebSocket('ws://localhost:8000/ws/agent');

// El servidor enviará un mensaje con el ID de cliente asignado
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'connection_established') {
        console.log('Client ID:', data.client_id);
    }
};

// Enviar un mensaje al agente
ws.send(JSON.stringify({
    content: "Tu mensaje aquí",
    context: {
        currentFile: "path/to/file.sol",
        currentCode: "código actual",
        fileSystem: {}
    }
}));
```

## Estructura del Proyecto

```
backend/
├── main.py              # Servidor FastAPI principal
├── agent.py             # Lógica del agente AI
├── file_manager.py      # Manejo de archivos y directorios
├── requirements.txt     # Dependencias del proyecto
└── .env                # Variables de entorno (no incluido en git)
```

## Respuestas del Servidor

El servidor puede enviar diferentes tipos de mensajes:

```json
{
    "type": "message|code_edit|file_create|file_delete|error|connection_established",
    "content": "contenido de la respuesta",
    "metadata": {
        "path": "path/to/file",
        "language": "solidity"
    }
}
```

## Desarrollo

1. Para desarrollo local, asegúrate de tener el entorno virtual activado
2. El servidor tiene hot-reload activado por defecto
3. Los logs se muestran en la consola en tiempo real

## Contribuir

1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles. 