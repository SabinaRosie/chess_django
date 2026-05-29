import os
import requests
from django.conf import settings
import base64
import io
import numpy as np
Kokoro = None
# Lazy import Kokoro to prevent startup crash if soundfile/libsndfile is missing on Render
try:
    # pyrefly: ignore [missing-import]
    from kokoro_onnx import Kokoro
except Exception as e:
    print(f"DEBUG: Kokoro-onnx top-level import skipped/failed: {e}")
    Kokoro = None

    
class OllamaManager:
    """Handles interactions with a local Ollama instance."""
    
    def __init__(self):
        self.base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = os.environ.get('OLLAMA_MODEL', 'phi3')

    def generate_response(self, prompt, system_prompt=None):
        """Generate text response using Ollama."""
        url = f"{self.base_url}/api/chat"
        
        if not system_prompt:
            system_prompt = (
                "You are the user's digital twin. You should respond in a way that sounds like the user reflecting on themselves. "
                "Keep responses concise and empathetic."
            )
            
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 150
            }
        }
        
        try:
            print(f"DEBUG: [Ollama] Requesting response from {url} using {self.model}", flush=True)
            response = requests.post(url, json=data, timeout=120)
            
            if response.status_code != 200:
                print(f"ERROR: Ollama API Error {response.status_code}: {response.text}", flush=True)
                return f"Error: Ollama failed with status {response.status_code}"
                
            result = response.json()
            return result['message']['content']
        except Exception as e:
            print(f"CRITICAL: Exception during Ollama generation: {str(e)}", flush=True)
            return f"Error: {str(e)}"

class CoquiXTTSManager:
    """Handles interactions with a local Coqui XTTS API server."""
    
    def __init__(self):
        self.base_url = os.environ.get('XTTS_BASE_URL', 'http://localhost:8020')

    def synthesize(self, text, reference_audio_content):
        """
        Synthesize speech using zero-shot cloning on XTTS.
        reference_audio_content: Binary content of the user's voice sample.
        """
        # We'll try both common endpoints
        endpoints = ["/tts_to_audio", "/tts"]
        
        # Base64 encode the speaker audio for JSON requests
        speaker_b64 = base64.b64encode(reference_audio_content).decode('utf-8')
        
        all_errors = []
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            print(f"DEBUG: [XTTS] Trying synthesis at {url}...", flush=True)
            
            # --- ATTEMPT 1: JSON with Base64 ---
            payload = {
                "text": text,
                "language": "en",
                "speaker_wav": speaker_b64
            }
            try:
                response = requests.post(url, json=payload, timeout=120)
                if response.status_code == 200:
                    print(f"DEBUG: [XTTS] Success at {url} (JSON)", flush=True)
                    return response.content, None
                all_errors.append(f"{endpoint} (JSON): {response.status_code} - {response.text[:50]}")
            except Exception as e:
                all_errors.append(f"{endpoint} (JSON) Exception: {str(e)}")

            # --- ATTEMPT 2: Multipart Form-Data ---
            files = {'speaker_wav': ('reference.wav', reference_audio_content, 'audio/wav')}
            data = {'text': text, 'language': 'en'}
            try:
                response = requests.post(url, data=data, files=files, timeout=120)
                if response.status_code == 200:
                    print(f"DEBUG: [XTTS] Success at {url} (Multipart)", flush=True)
                    return response.content, None
                all_errors.append(f"{endpoint} (Multipart): {response.status_code} - {response.text[:50]}")
            except Exception as e:
                all_errors.append(f"{endpoint} (Multipart) Exception: {str(e)}")

        error_message = " | ".join(all_errors)
        return None, f"XTTS failed: {error_message[:200]}"

class KokoroTTSManager:
    """Handles high-efficiency local TTS using Kokoro-82M (ONNX)."""
    
    _instance = None
    _kokoro = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KokoroTTSManager, cls).__new__(cls)
        return cls._instance

    def _initialize(self):
        if self._kokoro is not None or Kokoro is None:
            return

        model_path = os.path.join(settings.BASE_DIR, 'media', 'models', 'kokoro-v0_19.onnx')
        voices_path = os.path.join(settings.BASE_DIR, 'media', 'models', 'voices.bin')

        if os.path.exists(model_path) and os.path.exists(voices_path):
            try:
                print(f"DEBUG: [Kokoro] Initializing with {model_path}", flush=True)
                self._kokoro = Kokoro(model_path, voices_path)
            except Exception as e:
                print(f"ERROR: [Kokoro] Initialization failed: {e}", flush=True)
        else:
            print(f"WARNING: [Kokoro] Model files not found at {model_path}. Local Kokoro TTS disabled.", flush=True)

    def synthesize(self, text, voice='af_bella'):
        """
        Synthesize speech using Kokoro-82M.
        Returns bytes (WAV) and error message.
        """
        self._initialize()
        if not self._kokoro:
            return None, "Kokoro not initialized or model files missing."

        try:
            print(f"DEBUG: [Kokoro] Synthesizing: {text[:50]}...", flush=True)
            samples, sample_rate = self._kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
            
            # Convert float32 samples to int16 PCM for WAV
            try:
                # pyrefly: ignore [missing-import]
                import soundfile as sf
            except Exception as e:
                print(f"ERROR: [Kokoro] soundfile import failed (likely missing libsndfile1 on Render): {e}", flush=True)
                return None, f"System library missing: {e}"
                
            buffer = io.BytesIO()
            sf.write(buffer, samples, sample_rate, format='WAV', subtype='PCM_16')
            return buffer.getvalue(), None
        except Exception as e:
            print(f"ERROR: [Kokoro] Synthesis failed: {e}", flush=True)
            return None, str(e)

class VoiceAIManager:
    """Handles interactions with Groq, Ollama, and ElevenLabs."""
    
    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self):
        self.groq_key = os.environ.get('GROQ_API_KEY')
        self.elevenlabs_key = os.environ.get('ELEVENLABS_API_KEY')
        self.ai_mode = os.environ.get('AI_MODE', 'lightweight') # 'cloud', 'local', or 'lightweight'
        self.preferred_model = os.environ.get('LLM_MODEL', 'Qwen/Qwen2.5-0.5B-Instruct')

    def generate_response(self, prompt, context="", user=None, conversation_history=None):
        """Generate text response using the configured engine."""
        from datetime import datetime
        import pytz

        # Build a rich, personalized system prompt
        now = datetime.now(pytz.timezone('Asia/Kathmandu'))
        time_context = now.strftime("Today is %A, %B %d, %Y. The current time is %I:%M %p (Nepal Time).")

        user_context = ""
        if user:
            user_context = f"The user's name is {user.first_name or user.username}."
            try:
                profile = user.profile
                user_context += f" They have {profile.coins} coins in the app."
            except Exception:
                pass

        system_prompt = (
            f"You are {user.first_name or user.username if user else 'the user'}'s digital twin — an AI replica that thinks and talks exactly like them. "
            f"You speak in first person as if you ARE the user reflecting on their own thoughts. "
            f"You are warm, friendly, thoughtful, and conversational. "
            f"{time_context} "
            f"{user_context} "
            f"Keep responses concise (1-3 sentences) but natural and intelligent. "
            f"Never say you are an AI. You are the user's inner voice."
        )

        # Build message list with conversation history
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                role = "user" if msg.get("is_me") else "assistant"
                messages.append({"role": role, "content": msg.get("text", "")})
        messages.append({"role": "user", "content": prompt})

        # Prioritize Groq if available (extremely fast LPU inference)
        if self.groq_key:
            print(f"DEBUG: [Groq] Requesting smart chat completion", flush=True)
            return self._groq_generate(messages)

        # Lightweight mode: Use SiliconFlow with Qwen2.5-7B
        if self.ai_mode == 'lightweight':
            sf_manager = SiliconFlowManager()
            if sf_manager.api_key:
                print(f"DEBUG: [SiliconFlow] Requesting chat completion", flush=True)
                content, error = sf_manager.chat_completion(prompt, system_prompt=system_prompt)
                if not error:
                    return content
                print(f"ERROR: [SiliconFlow] LLM failed: {error}.", flush=True)
            return f"Error: AI service unavailable. Please check SILICONFLOW_API_KEY."

        # Cloud mode: Try Groq
        if self.ai_mode == 'cloud' and self.groq_key:
            return self._groq_generate(messages)

        # Local mode: Use Ollama
        if self.ai_mode == 'local':
            return OllamaManager().generate_response(prompt)

        # Default
        if self.groq_key:
            return self._groq_generate(messages)
        return "Error: No AI service configured. Please set SILICONFLOW_API_KEY or GROQ_API_KEY."

    def _groq_generate(self, messages):
        """Generate using Groq API with a smart, fast model."""
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "llama-3.3-70b-versatile",  # Smart and still very fast on Groq LPU
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 150
        }
        try:
            user_msg = messages[-1]["content"] if messages else "?"
            print(f"DEBUG: [Groq] Requesting response for prompt: {user_msg[:50]}...", flush=True)
            response = requests.post(self.GROQ_API_URL, headers=headers, json=data, timeout=15)
            if response.status_code != 200:
                print(f"ERROR: Groq API Error {response.status_code}: {response.text}", flush=True)
                return f"Error: Groq API Error {response.status_code}"
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            print(f"CRITICAL: Exception during Groq generation: {str(e)}", flush=True)
            return f"Error: {str(e)}"
    
    def create_user_voice(self, user_name, audio_files):
        """Create an Instant Voice Clone on ElevenLabs."""
        if not self.elevenlabs_key:
            print("ERROR: ELEVENLABS_API_KEY is missing from environment variables.")
            return None, "Error: ELEVENLABS_API_KEY not found."
            
        url = f"{self.ELEVENLABS_API_URL}/voices/add"
        headers = {"xi-api-key": self.elevenlabs_key}
        
        files = []
        for i, f in enumerate(audio_files):
            # Ensure pointer is at start
            f.seek(0)
            # Detect extension from filename or default to wav
            orig_name = getattr(f, 'name', f'sample_{i}.wav')
            ext = 'wav' if orig_name.endswith('.wav') else 'm4a'
            files.append(('files', (f'sample_{i}.{ext}', f, f'audio/{ext}')))
        
        data = {
            'name': f"User_{user_name}",
            'description': f"Cloned voice for {user_name}"
        }
        
        try:
            print(f"DEBUG: Sending {len(files)} samples to ElevenLabs for user {user_name}")
            response = requests.post(url, headers=headers, data=data, files=files)
            
            if response.status_code != 200:
                print(f"ERROR: ElevenLabs API returned {response.status_code}")
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get('detail', {}).get('message', response.text)
                except:
                    pass
                return None, f"ElevenLabs Error: {error_detail}"
                
            voice_id = response.json().get('voice_id')
            return voice_id, None
        except Exception as e:
            return None, str(e)

    def text_to_speech(self, text, voice_id):
        """Synthesize speech using ElevenLabs."""
        if not self.elevenlabs_key:
            return None, "Error: ELEVENLABS_API_KEY not found."
            
        url = f"{self.ELEVENLABS_API_URL}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code != 200:
                return None, f"ElevenLabs TTS Error: {response.text}"
            
            return response.content, None
        except Exception as e:
            return None, str(e)

class SiliconFlowManager:
    """Handles interactions with SiliconFlow (CosyVoice) for free-tier cloning."""
    
    API_URL = "https://api.siliconflow.com/v1"
    
    def __init__(self):
        self.api_key = os.environ.get('SILICONFLOW_API_KEY')
        if isinstance(self.api_key, str):
            self.api_key = self.api_key.strip().strip('"').strip("'").strip()
        else:
            self.api_key = None

    def upload_voice(self, audio_content, custom_name, transcription_text, is_wav=True):
        if not self.api_key:
            return None, "Error: SILICONFLOW_API_KEY not found."

        url = f"{self.API_URL}/uploads/audio/voice"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        ext = "wav" if is_wav else "mp3"
        mimetype = "audio/wav" if is_wav else "audio/mpeg"
        
        files = {"file": (f"{custom_name}.{ext}", audio_content, mimetype)}
        data = {
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "customName": custom_name,
            "text": transcription_text
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, files=files)
            if response.status_code != 200:
                return None, response.text
                
            uri = response.json().get("uri")
            return uri, None
        except Exception as e:
            return None, str(e)

    def zero_shot_tts(self, text, voice_identifier):
        if not self.api_key:
            return None, "Error: SILICONFLOW_API_KEY not found."

        url = f"{self.API_URL}/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "input": text,
            "voice": voice_identifier,
            "response_format": "mp3"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code != 200:
                return None, response.text
            return response.content, None
        except Exception as e:
            return None, str(e)

    def chat_completion(self, prompt, system_prompt=None):
        """Generate text response using SiliconFlow (OpenAI-compatible)."""
        if not self.api_key:
            return None, "Error: SILICONFLOW_API_KEY not found."

        url = f"{self.API_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        if not system_prompt:
            system_prompt = (
                "You are the user's digital twin. You should respond in a way that sounds like the user reflecting on themselves. "
                "Keep responses concise and empathetic."
            )

        data = {
            "model": os.environ.get('LLM_MODEL', 'Qwen/Qwen2.5-7B-Instruct'),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code != 200:
                return None, f"SiliconFlow API Error {response.status_code}: {response.text}"
            
            result = response.json()
            return result['choices'][0]['message']['content'], None
        except Exception as e:
            return None, str(e)

