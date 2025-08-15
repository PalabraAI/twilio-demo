// WebSocket connection
const ws = new WebSocket(`wss://${window.location.host}/transcription-ws`);
const statusElement = document.getElementById('connection-status');
const container = document.getElementById('messages-container');

// Storage for partial transcriptions of each participant
const partialMessages = {
    client: null,
    operator: null
};

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
    switch (data.action) {
        case "new":
            createNewDiv(data);
            break;
        case "update":
            updateExistingDiv(data);
            break;
        case "replace":
            replaceWithComplete(data);
            break;
        default:
            console.error("Unknown action:", data.action);
    }
    container.scrollTop = container.scrollHeight;
}

// Create new transcription div
function createNewDiv(data) {
    const messageDiv = createMessageElement(data, true);
    partialMessages[data.role] = messageDiv;
    container.appendChild(messageDiv);
}

// Replace existing div with complete transcription
function replaceWithComplete(data) {
    const div = partialMessages[data.role];
    if (div) {
        const originalText = div.querySelector('.text-block:first-child .text-content');
        const translatedText = div.querySelector('.text-block:last-child .text-content');
        
        originalText.textContent = data.original_text;
        translatedText.textContent = data.translated_text;
        div.classList.remove('partial');
        partialMessages[data.role] = null;
    }
}

// Update existing div
function updateExistingDiv(data) {
    const partialDiv = partialMessages[data.role];
    if (partialDiv) {
        const originalText = partialDiv.querySelector('.text-block:first-child .text-content');
        originalText.textContent = data.original_text;
        
        // Clear translation as this is only original
        const translatedText = partialDiv.querySelector('.text-block:last-child .text-content');
        translatedText.textContent = 'Translation pending...';
    }
}

// Create message element
function createMessageElement(data, isPartial) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${data.role} ${isPartial ? 'partial' : ''}`;
    
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

