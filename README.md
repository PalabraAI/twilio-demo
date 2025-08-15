# Twilio Demo - Real-time Audio Translation

A real-time audio translation application built with FastAPI, Twilio, and Palabra AI that enables live voice conversations between speakers of different languages.

## 🚀 Features

- **Real-time Audio Processing**: Live audio streaming and processing using Twilio Media Streams
- **Automatic Speech Recognition**: Real-time transcription with language detection (English/Russian)
- **Live Translation**: Instant translation among different languages
- **Web Interface**: Real-time transcription display with WebSocket updates
- **Multi-party Calls**: Support for client-operator conversations
- **Audio Mixing**: Intelligent mixing of original and translated audio

## 🏗️ Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │    │   Twilio    │    │   Server    │
│  (Phone)    │◄──►│  (Gateway)  │◄──►│ (FastAPI)   │
└─────────────┘    └─────────────┘    └─────────────┘
                           │                   │
                           │                   ▼
                           │            ┌─────────────┐
                           │            │  Palabra    │
                           │            │     API     │
                           │            │             │
                           │            └─────────────┘
                           │                   │
                           ▼                   │
                    ┌─────────────┐            │
                    │  Operator   │            │
                    │  (Phone)    │            │
                    └─────────────┘            │
```

## 🛠️ Technology Stack

- **Backend**: FastAPI, Python 3.11+
- **Audio Processing**: NumPy, audioop
- **WebSocket**: Starlette WebSockets
- **Telephony**: Twilio API
- **AI Services**: Palabra AI (ASR, Translation, TTS)
- **Frontend**: HTML, CSS, JavaScript
- **Process Management**: Multiprocessing with async workers

## 📋 Prerequisites

- Python 3.11 or higher
- Twilio account with phone numbers
- Palabra AI API credentials
- Environment variables configured

## 🔧 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd twilio-demo
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

## ⚙️ Configuration (TODO: specify more details)

Create a `.env` file with the following variables:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_NUMBER=your_twilio_phone_number

# Palabra AI Configuration
PALABRA_CLIENT_ID=your_client_id
PALABRA_CLIENT_SECRET=your_client_secret

# Server Configuration
HOST=your_server_hostname_or_ip
OPERATOR_NUMBER=operator_phone_number
```

## 🚀 Usage

### Starting the Server

```bash
python main.py
```

The server will start on `http://0.0.0.0:7839`

### Making a Call

1. **Client calls your Twilio number**
2. **System automatically calls the operator**
3. **Both parties are connected via WebSocket**
4. **Real-time translation begins automatically**

### Web Interface

Access the transcription interface at:
```
http://your-server:7839/transcription
```

## 📁 Project Structure

```
twilio-demo/
├── main.py                 # FastAPI application entry point
├── bridge.py               # Audio bridge and WebSocket handling
├── settings.py             # Configuration and role settings
├── transcription.py        # Transcription broadcasting
├── utils/
│   ├── audio.py           # Audio processing workers
│   ├── calls.py           # Call session management
│   └── worker.py          # Async process manager
├── templates/
│   └── transcription.html # Web interface template
├── static/
│   ├── css/
│   │   └── styles.css     # Styling for web interface
│   └── js/
│       └── app.js         # WebSocket client logic
├── pyproject.toml         # Project configuration
└── README.md              # This file
```

## 🔌 API Endpoints

### HTTP Endpoints

- `POST /twiml/client` - Handle incoming client calls
- `POST /voice/callback/{session_id}` - Handle call status updates
- `POST /voice/disconnect/{role}/{session_id}` - Handle call termination
- `GET /transcription` - Web interface for transcriptions

### WebSocket Endpoints

- `WS /voice/{role}/{session_id}` - Audio streaming for calls
- `WS /transcription-ws` - Real-time transcription updates

## 🎵 Audio Processing

The application processes audio in the following pipeline:

1. **Input**: μ-law encoded audio from Twilio (8kHz, mono)
2. **Conversion**: Convert to PCM (24kHz, 16-bit, mono)
3. **Processing**: Send to Palabra AI for ASR and translation
4. **Output**: Receive translated audio and mix with original
5. **Delivery**: Send mixed audio back to participants

### Audio Specifications

- **Input Format**: μ-law, 8kHz, 1 channel
- **Processing Format**: PCM s16le, 24kHz, 1 channel
- **Output Format**: μ-law, 8kHz, 1 channel
- **Twilio Buffer Size**: 960 bytes (20ms at 24kHz)

## 🌐 Web Interface

The web interface provides:

- **Real-time Transcription**: Live display of conversation
- **Translation Status**: Indicates when translations are pending
- **Connection Status**: WebSocket connection monitoring
- **Responsive Design**: Works on desktop and mobile devices

## 🔒 Security

- **Twilio Signature Validation**: All webhooks are verified
- **Environment Variables**: Sensitive data stored securely
- **Input Validation**: All user inputs are validated
- **Error Handling**: Comprehensive error handling and logging

## 🧪 Development

### Code Quality Tools

- **Black**: Code formatting
- **Ruff**: Linting and formatting
- **isort**: Import sorting
- **Vulture**: Dead code detection

### Running Development Tools

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Sort imports
ruff check --select I .

# Check for dead code
vulture .
```

## 🐛 Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check if server is running
   - Verify firewall settings
   - Check WebSocket URL configuration

2. **Audio Not Processing**
   - Verify Palabra AI credentials
   - Check audio format compatibility
   - Monitor server logs for errors

3. **Calls Not Connecting**
   - Verify Twilio credentials
   - Check phone number configuration
   - Ensure proper webhook URLs

### Logs

The application provides detailed logging:
- **INFO**: Connection status and call events
- **WARNING**: Non-critical issues
- **ERROR**: Errors and exceptions

## 📝 API Documentation

Once the server is running, access the interactive API documentation at:
```
http://your-server:your-port/demo/docs
```
