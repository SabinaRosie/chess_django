from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import UserVoiceProfile, VoiceResponseCache
from .voice_service import VoiceAIManager, SiliconFlowManager, CoquiXTTSManager, KokoroTTSManager
import uuid
import hashlib
from django.db import transaction
import os
import threading
import requests

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_voice_samples(request):
    """
    Upload voice samples. One is saved to Cloudinary as a reference for SiliconFlow.
    """
    user = request.user
    audio_files = request.FILES.getlist('samples')
    
    if not audio_files:
        return Response({"error": "No voice samples provided"}, status=400)
    
    # 1. Update or create voice profile
    profile, created = UserVoiceProfile.objects.get_or_create(user=user)
    
    # 2. Save the first sample to Cloudinary as our persistent reference
    # CloudinaryField handles the upload automatically when assigned a file object
    profile.reference_audio = audio_files[0]
    profile.is_trained = True
    
    # NEW: Also upload to SiliconFlow immediately to get a voice URI
    # This is required for SiliconFlow Zero-Shot as it doesn't support URLs directly
    sf_manager = SiliconFlowManager()
    try:
        # Reposition file pointer to start before reading
        audio_files[0].seek(0)
        audio_content = audio_files[0].read()
        
        # Training text is known from the Flutter UI instructions
        training_text = "Hello, I am training my digital assistant in the Chess Mobile App."
        
        uri, error = sf_manager.upload_voice(
            audio_content, 
            f"user_{user.id}_{uuid.uuid4().hex[:8]}", 
            training_text
        )
        if uri:
            profile.siliconflow_voice_uri = uri
            print(f"DEBUG: Saved SiliconFlow Voice URI to profile: {uri}", flush=True)
    except Exception as e:
        print(f"ERROR: Failed to upload voice to SiliconFlow during profile creation: {str(e)}", flush=True)

    # CRITICAL: Reset file pointer again before profile.save() 
    # This ensures Cloudinary can read the file correctly
    audio_files[0].seek(0)
    profile.save()
    
    # 3. (Optional) Still try ElevenLabs if key exists, but do it asynchronously to avoid timeouts
    if os.environ.get('ELEVENLABS_API_KEY'):
        def train_elevenlabs():
            ai_manager = VoiceAIManager()
            # Note: Re-read files as the pointers might have moved
            for f in audio_files: f.seek(0)
            v_id, v_err = ai_manager.create_user_voice(user.username, audio_files)
            if not v_err:
                profile.elevenlabs_voice_id = v_id
                profile.save()
        
        # Start background training
        threading.Thread(target=train_elevenlabs).start()

    return Response({
        "message": "Voice profile received and reference saved. Training in background.",
        "reference_url": profile.reference_audio.url if profile.reference_audio else None,
        "sf_uri": profile.siliconflow_voice_uri
    })

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_voice_profile(request):
    """Securely delete user samples and profile"""
    user = request.user
    try:
        profile = user.voice_profile
        # Note: CloudinaryField deletion typically happens on model delete 
        # but we can also manually clear the field if we want to keep the profile record
        profile.delete()
        VoiceResponseCache.objects.filter(user=user).delete()
        return Response({"message": "Voice profile and samples deleted successfully"})
    except UserVoiceProfile.DoesNotExist:
        return Response({"error": "No voice profile found"}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chat_with_self(request):
    print(f"DEBUG: [VOICE] chat_with_self called by {request.user.username}", flush=True)
    user = request.user
    message = request.data.get('message', '').strip()
    
    if not message:
        return Response({"error": "No message provided"}, status=400)
    
    try:
        profile = user.voice_profile
    except UserVoiceProfile.DoesNotExist:
        return Response({"error": "Voice profile not trained."}, status=400)
    
    try:
        # 1. Caching Check: Has this user said this before?
        text_hash = hashlib.sha256(message.lower().encode()).hexdigest()
        cache_entry = VoiceResponseCache.objects.filter(user=user, text_hash=text_hash).first()
        
        ai_manager = VoiceAIManager()
        sf_manager = SiliconFlowManager()
        xtts_manager = CoquiXTTSManager()
        kokoro_manager = KokoroTTSManager()

        # 2. Generate text response
        response_text = ai_manager.generate_response(message)
        
        if response_text.startswith("Error"):
            print(f"ERROR: AI Generation failed: {response_text}", flush=True)
            return Response({"error": response_text}, status=500)
        
        # 3. Audio Generation (from Cache, ElevenLabs, SiliconFlow, or Local XTTS)
        audio_url = None
        synth_error = None
        audio_content = None  # Always initialize so it's never unbound
        
        if cache_entry:
            print(f"DEBUG: Cache hit for message hash {text_hash}", flush=True)
            audio_url = cache_entry.audio_file.url
        else:
            # Prioritize Kokoro for lightweight mode or as high-efficiency local fallback
            if ai_manager.ai_mode == 'lightweight':
                print(f"DEBUG: [Kokoro] Attempting lightweight synthesis", flush=True)
                audio_content, synth_error = kokoro_manager.synthesize(response_text)
                if audio_content:
                    print(f"DEBUG: [Kokoro] Synthesis success", flush=True)
                else:
                    print(f"ERROR: [Kokoro] Lightweight synthesis failed: {synth_error}. Trying SiliconFlow TTS...", flush=True)
                    # Kokoro is unavailable on Render (model files not downloaded) — use SiliconFlow CosyVoice
                    if profile.siliconflow_voice_uri or profile.reference_audio:
                        voice_id = profile.siliconflow_voice_uri or profile.reference_audio.url
                        audio_content, sf_error = sf_manager.zero_shot_tts(response_text, voice_id)
                        if sf_error:
                            synth_error = f"Kokoro: {synth_error} | SiliconFlow TTS: {sf_error}"
                            print(f"ERROR: [SiliconFlow TTS] Failed: {sf_error}", flush=True)
                        else:
                            print(f"DEBUG: [SiliconFlow TTS] Synthesis success", flush=True)
                    else:
                        synth_error = f"Kokoro failed and no voice profile found for SiliconFlow TTS."

            # Only try XTTS if we're NOT in lightweight mode and have a configured server
            if not audio_content and ai_manager.ai_mode != 'lightweight':
                xtts_url = os.environ.get('XTTS_BASE_URL', '')
                if xtts_url and profile.reference_audio:
                    try:
                        print(f"DEBUG: [XTTS] Fetching reference audio from {profile.reference_audio.url}", flush=True)
                        ref_response = requests.get(profile.reference_audio.url, timeout=30)
                        if ref_response.status_code == 200:
                            audio_content, synth_error = xtts_manager.synthesize(response_text, ref_response.content)
                            print(f"DEBUG: [XTTS] Synthesis result — content={bool(audio_content)}, error={synth_error}", flush=True)
                        else:
                            synth_error = f"Failed to download reference audio: {ref_response.status_code}"
                    except Exception as e:
                        synth_error = f"Error during local synthesis prep: {str(e)}"
                        print(f"CRITICAL: [XTTS] {synth_error}", flush=True)

            # Try ElevenLabs if still no audio and not in local mode
            if not audio_content and ai_manager.ai_mode != 'local' and profile.elevenlabs_voice_id:
                audio_content, synth_error = ai_manager.text_to_speech(response_text, profile.elevenlabs_voice_id)
            
        if audio_content:
            # Save to Cloudinary for caching
            filename = f"voice_{user.id}_{uuid.uuid4().hex}.mp3"
            # Use SimpleUploadedFile to avoid 'can't adapt type ContentFile' error with psycopg2/Cloudinary
            audio_file = SimpleUploadedFile(filename, audio_content, content_type="audio/mpeg")
            
            new_cache = VoiceResponseCache.objects.create(
                user=user,
                text_hash=text_hash,
                audio_file=audio_file
            )
            audio_url = new_cache.audio_file.url

        return Response({
            "text": response_text,
            "audio_url": audio_url,
            "audio_id": audio_url,
            "is_cached": cache_entry is not None,
            "error": synth_error if not audio_url else None
        })
    except Exception as e:
        print(f"CRITICAL: Unhandled error in chat_with_self: {str(e)}", flush=True)
        import traceback
        print(traceback.format_exc(), flush=True)
        return Response({"error": f"Internal Server Error: {str(e)}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_voice_status(request):
    """Check if the user has a trained voice profile."""
    try:
        profile = request.user.voice_profile
        return Response({
            "is_trained": profile.is_trained,
            "voice_id": profile.elevenlabs_voice_id,
            "sf_uri": profile.siliconflow_voice_uri,
            "has_reference": profile.reference_audio is not None,
            "reference_url": profile.reference_audio.url if profile.reference_audio else None
        })
    except UserVoiceProfile.DoesNotExist:
        return Response({"is_trained": False})
