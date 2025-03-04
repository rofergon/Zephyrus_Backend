# Manual de Comunicación WebSocket Frontend-Backend

Este documento describe la especificación para la comunicación WebSocket entre el frontend y el backend de la aplicación.

## 1. Establecimiento de Conexión

### URL del WebSocket
```javascript
ws://your-domain/ws/agent
```

### Parámetros Requeridos (Query Parameters)
| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `wallet_address` | string | Dirección Ethereum (debe comenzar con '0x') | `0x123...` |
| `chat_id` | UUID | Identificador único de la conversación | `550e8400-e29b-41d4-a716-446655440000` |

### Ejemplo de Conexión
```javascript
const ws = new WebSocket(`ws://your-domain/ws/agent?wallet_address=0x123...&chat_id=550e8400-e29b-41d4-a716-446655440000`);
```

### Errores de Conexión
La conexión será rechazada (código 1008) en los siguientes casos:
- No se proporciona `wallet_address` o no comienza con '0x'
- No se proporciona `chat_id`
- El `chat_id` no es un UUID válido

## 2. Tipos de Mensajes

### 2.1 Mensaje Regular
```json
{
    "type": "message",
    "content": "Tu mensaje aquí",
    "context": {},
    "chat_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2.2 Guardar Archivo
```json
{
    "type": "save_file",
    "path": "ruta/del/archivo.sol",
    "content": "contenido del archivo",
    "language": "solidity",
    "chat_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2.3 Obtener Versión de Archivo
```json
{
    "type": "get_file_version",
    "path": "ruta/del/archivo.sol",
    "version": "version-id",
    "chat_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2.4 Sincronización de Contextos
```json
{
    "type": "contexts_synced",
    "chat_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2.5 Mensaje sin Respuesta
```json
{
    "type": "message",
    "content": "Tu mensaje aquí",
    "suppress_response": true,
    "chat_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## 3. Respuestas del Servidor

### 3.1 Respuesta Regular
```json
{
    "type": "message",
    "content": "Respuesta del AI",
    "metadata": {}
}
```

### 3.2 Confirmación de Archivo Guardado
```json
{
    "type": "file_saved",
    "content": "File saved successfully: path/to/file",
    "metadata": {
        "path": "path/to/file",
        "chat_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

### 3.3 Respuesta de Versión de Archivo
```json
{
    "type": "file_version",
    "content": "contenido del archivo",
    "metadata": {
        "path": "path/to/file",
        "chat_id": "550e8400-e29b-41d4-a716-446655440000",
        "version": "version-id",
        "timestamp": 1234567890
    }
}
```

### 3.4 Mensajes de Error
```json
{
    "type": "error",
    "content": "Descripción del error"
}
```

## 4. Consideraciones Técnicas

### 4.1 Persistencia del chat_id
- El `chat_id` proporcionado en la conexión WebSocket se mantiene durante toda la sesión
- Cada mensaje debe incluir el mismo `chat_id`
- El `chat_id` debe ser un UUID válido

### 4.2 Manejo de Errores
- Implementar reconexión automática en caso de desconexión
- Manejar los mensajes de error del servidor apropiadamente
- Validar el formato de los mensajes antes de enviarlos

### 4.3 Formato de Datos
- Todos los mensajes deben ser JSON válido
- El campo `content` es obligatorio en la mayoría de los mensajes
- Los timestamps se manejan en milisegundos (timestamp * 1000)

### 4.4 Seguridad
- Asegurarse de que el `wallet_address` sea válido antes de intentar la conexión
- Mantener el `chat_id` consistente durante toda la sesión
- No enviar datos sensibles en el contexto

## 5. Ejemplos de Implementación

### 5.1 Conexión Básica
```javascript
const connectWebSocket = (walletAddress, chatId) => {
    const ws = new WebSocket(`ws://your-domain/ws/agent?wallet_address=${walletAddress}&chat_id=${chatId}`);
    
    ws.onopen = () => {
        console.log('Conexión establecida');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };
    
    ws.onerror = (error) => {
        console.error('Error en la conexión:', error);
    };
    
    ws.onclose = () => {
        console.log('Conexión cerrada');
        // Implementar lógica de reconexión
    };
};
```

### 5.2 Envío de Mensaje
```javascript
const sendMessage = (ws, content, chatId) => {
    const message = {
        type: "message",
        content: content,
        chat_id: chatId,
        context: {}
    };
    ws.send(JSON.stringify(message));
};
```

## 6. Buenas Prácticas

1. **Validación de Datos**
   - Validar todos los campos antes de enviar mensajes
   - Asegurar que el formato JSON sea correcto
   - Verificar que el `chat_id` sea consistente

2. **Manejo de Estado**
   - Mantener un registro del estado de la conexión
   - Implementar un sistema de reintentos para mensajes fallidos
   - Guardar mensajes importantes en caché local

3. **Gestión de Errores**
   - Implementar timeouts apropiados
   - Manejar reconexiones de forma gradual
   - Registrar errores para debugging

4. **Optimización**
   - Minimizar el tamaño de los mensajes
   - Implementar rate limiting en el cliente
   - Usar compresión cuando sea posible

## 7. Preguntas Frecuentes

### ¿Qué hacer si la conexión se pierde?
Implementar un sistema de reconexión automática con backoff exponencial.

### ¿Cómo manejar mensajes grandes?
Considerar la fragmentación de mensajes grandes y el uso de compresión.

### ¿Cómo garantizar la entrega de mensajes?
Implementar un sistema de confirmación de mensajes y reintentos.

---

Para más información o actualizaciones, consulta la documentación oficial del proyecto. 