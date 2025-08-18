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
┌─────────────┐    ┌─────────────┐    ┌───────────────────────┐
│   Client    │    │   Twilio    │    │   Websocket Server    │
│  (Phone)    │◄──►│  (Gateway)  │◄──►│      (FastAPI)        │
└─────────────┘    └─────────────┘    └───────────────────────┘
                           ▲                   ▲
                           │                   │
                           |                   │
                           │                   │
                           │                   ▼
                           │            ┌─────────────┐
                           │            │  Palabra    │
                           │            │     API     │
                           │            │             │
                           │            └─────────────┘
                           │                   
                           ▼                   
                    ┌─────────────┐            
                    │  Operator   │            
                    │  (Phone)    │            
                    └─────────────┘            
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

4. **Install development dependencies (optional)**
   ```bash
   pip install -e ".[lint]"
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root directory with the following variables:

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
PORT=7839

# Language Configuration
SOURCE_LANGUAGE=en
TARGET_LANGUAGE=ru
```

### Variable Descriptions

#### Twilio Configuration
- **`TWILIO_ACCOUNT_SID`** - Your Twilio Account SID
- **`TWILIO_AUTH_TOKEN`** - Your Twilio Auth Token
- **`TWILIO_NUMBER`** - Your Twilio phone number that clients will call

This Twilio [article](https://help.twilio.com/articles/14726256820123-What-is-a-Twilio-Account-SID-and-where-can-I-find-it-#h_01J7NVD4HY13NYHMVW1X4TFY7B) explains how to obtain both credentials.

#### Palabra AI Configuration
- **`PALABRA_CLIENT_ID`** - Your Palabra AI client identifier
- **`PALABRA_CLIENT_SECRET`** - Your Palabra AI client secret key

This Palabra [article](https://docs.palabra.ai/docs/auth/obtaining_api_keys) explains how to obtain both credentials.

#### Server Configuration
- **`HOST`** - Your server's hostname or IP address (for local development you may use Cloudflare Tunnel URL or its alternatives)
- **`OPERATOR_NUMBER`** - The operator's phone number for receiving calls
- **`PORT`** - Server port number (defaults to 7839)

#### Language Configuration
- **`SOURCE_LANGUAGE`** - Language spoken by the client (e.g., en, ru, de, es)
- **`TARGET_LANGUAGE`** - Language spoken by the operator (e.g., en, ru, de, es)

## 🌐 Local Development with Cloudflare Tunnel

For local development, you'll need to expose your local server to the internet so Twilio can send webhooks. The recommended tool for this is **Cloudflare Tunnel** (cloudflared).

### Setting up Cloudflare Tunnel

1. **Install cloudflared**
   Follow the [Cloudflare Tunnel documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) for installation instructions.

2. **Start cloudflared tunnel**
   ```bash
   cloudflared tunnel --url http://localhost:${PORT}
   ```

3. **Copy the tunnel URL**
   ```
   https://abc123.trycloudflare.com
   ```

4. **Set HOST variable**
   Use the tunnel URL (without protocol) as your `HOST` value:
   ```env
   HOST=abc123.trycloudflare.com
   ```

### Important Notes

- **HTTPS Required**: Twilio requires HTTPS for webhooks, which Cloudflare Tunnel provides
- **Stable URLs**: Cloudflare Tunnel provides stable URLs that don't change on restart
- **Update Twilio Webhooks**: Remember to update your Twilio webhook URLs when the tunnel URL changes


### Twilio Webhook Configuration

After setting up your tunnel, you need to configure Twilio webhooks to point to your server:

1. **Go to Twilio Console** → **Phone Numbers** → **Manage** → **Active numbers**
2. **Click on your phone number**
3. **In the "Voice Configuration" section, set:**
   - **Webhook URL**: `https://${HOST}/twiml/client`
   - **HTTP Method**: `POST`

For detailed instructions, see the [Twilio Phone Number Configuration documentation](https://support.twilio.com/hc/en-us/articles/223179948-Configure-Phone-Numbers-for-Voice-and-SMS).

**Important**: Replace `${HOST}` with your actual tunnel hostname (e.g., `abc123.trycloudflare.com`).

### Geographic Permissions

**Critical**: Ensure that the country of your operator's phone number is enabled in Twilio's Geographic Permissions. If the operator's country is not enabled, Twilio will block outbound calls to that number.

To configure Geographic Permissions:
1. Go to **Twilio Console** → **Voice** → **Geographic Permissions**
2. Enable calling to the country where your operator's phone number is located

For detailed information about Geographic Permissions and toll fraud protection, see the [Twilio Geographic Permissions documentation](https://www.twilio.com/docs/sip-trunking/voice-dialing-geographic-permissions#allow-legitimate-calls-block-unwanted-calls-on-programmable-voice-and-elastic-sip-trunking).

## 🚀 Usage

### Starting the Server

```bash
source .env
python main.py
```

The server will start on `http://0.0.0.0:${PORT}`

**Note**: Make sure you have created the `.env` file with all required environment variables before starting the server.

### Making a Call

1. **Client calls your Twilio number**
2. **System automatically calls the operator**
3. **Both parties are connected via WebSocket**
4. **Real-time translation begins automatically**

### Web Interface

Access the transcription interface at:
```
https://${HOST}:${PORT}/transcription
```

Replace `${HOST}` and `${PORT}` with your actual server hostname/IP address and port number.

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

## 📸 Screenshots

### Main Interface
![Main Interface](/static/readme/screen_1.png)

### Transcription Display
![Transcription Display](/static/readme/screen_2.png)

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
https://${HOST}:${PORT}/docs
```
