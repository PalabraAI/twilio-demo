// WebSocket connection
const ws = new WebSocket(`wss://${window.location.host}/transcription-ws`);
const statusElement = document.getElementById('connection-status');
const container = document.getElementById('messages-container');

// Storage for transcriptions by transcription_id
const transcriptionMessages = new Map();

// WebSocket event handlers
ws.onopen = function() {
    statusElement.textContent = 'Connected';
    container.innerHTML = '';
};

ws.onclose = function() {
    statusElement.textContent = 'Disconnected';
};

ws.onerror = function(error) {
    console.error('WebSocket error:', error);
    statusElement.textContent = 'Error';
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'transcription') {
        handleTranscription(data);
    }
};

// Main transcription handling function
function handleTranscription(data) {
    console.log('Handling transcription:', {
        action: data.action,
        id: data.transcription_id,
        role: data.role,
        original: data.original_text,
        translated: data.translated_text,
        lang: data.original_language
    });
    
    // Единственное действие - update (создать или обновить)
    updateOrCreateDiv(data);
    
    // Clean up old transcriptions
    cleanupOldTranscriptions();
    
    container.scrollTop = container.scrollHeight;
}

// Universal function to create or update transcription div
function updateOrCreateDiv(data) {
    let div = transcriptionMessages.get(data.transcription_id);
    
    if (!div) {
        // Создаем новый div
        div = createMessageElement(data);
        transcriptionMessages.set(data.transcription_id, div);
        container.appendChild(div);
        console.log('Created new div for transcription ID:', data.transcription_id);
    } else {
        // Обновляем существующий div
        if (data.original_text) {
            // Обновляем оригинальный текст
            const originalText = div.querySelector('.text-block:first-child .text-content');
            originalText.textContent = data.original_text;
            console.log('Updated original text for transcription ID:', data.transcription_id);
        }
        
        if (data.translated_text) {
            // Обновляем переведенный текст
            const translatedText = div.querySelector('.text-block:last-child .text-content');
            translatedText.textContent = data.translated_text;
            div.classList.remove('partial');
            div.classList.add('complete');
            console.log('Updated translation for transcription ID:', data.transcription_id);
        }
    }
}

// Clean up old transcriptions to prevent memory leaks
function cleanupOldTranscriptions() {
    const maxTranscriptions = 50; // Keep only last 50 transcriptions
    if (transcriptionMessages.size > maxTranscriptions) {
        const entries = Array.from(transcriptionMessages.entries());
        const toRemove = entries.slice(0, entries.length - maxTranscriptions);
        
        toRemove.forEach(([id, div]) => {
            div.remove();
            transcriptionMessages.delete(id);
        });
    }
}

// Create message element
function createMessageElement(data) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${data.role} partial`;
    
    const messageHeader = document.createElement('div');
    messageHeader.className = 'message-header';
    
    const roleBadge = document.createElement('div');
    roleBadge.className = `role-badge ${data.role}`;
    roleBadge.textContent = data.role === 'client' ? '👤 Client' : '👨‍💼 Operator';
    
    const timestamp = document.createElement('div');
    timestamp.className = 'timestamp';
    timestamp.textContent = new Date().toLocaleTimeString();
    
    messageHeader.appendChild(roleBadge);
    messageHeader.appendChild(timestamp);
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    // Block for original text
    const originalBlock = document.createElement('div');
    originalBlock.className = 'text-block';
    
    const originalLabel = document.createElement('div');
    originalLabel.className = 'text-label';
    originalLabel.textContent = 'Original:';
    
    const originalText = document.createElement('div');
    originalText.className = 'text-content';
    originalText.textContent = data.original_text;
    
    originalBlock.appendChild(originalLabel);
    originalBlock.appendChild(originalText);
    
    // Block for translation
    const translatedBlock = document.createElement('div');
    translatedBlock.className = 'text-block';
    
    const translatedLabel = document.createElement('div');
    translatedLabel.className = 'text-label';
    translatedLabel.textContent = 'Translated:';
    
    const translatedText = document.createElement('div');
    translatedText.className = 'text-content';
    translatedText.textContent = data.translated_text || 'Translation pending...';
    
    translatedBlock.appendChild(translatedLabel);
    translatedBlock.appendChild(translatedText);
    
    messageContent.appendChild(originalBlock);
    messageContent.appendChild(translatedBlock);
    
    messageDiv.appendChild(messageHeader);
    messageDiv.appendChild(messageContent);
    
    return messageDiv;
}

// Utility function to scroll to bottom
function scrollToBottom() {
    container.scrollTop = container.scrollHeight;
}

// Auto-scroll on new messages
document.addEventListener('DOMContentLoaded', function() {
    // Initial scroll to bottom
    scrollToBottom();
});

