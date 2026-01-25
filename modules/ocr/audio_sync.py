"""
Audio Sync Module - Voice onset detection and OCR-Audio synchronization

Pipeline:
1. Extract audio waveform from video
2. Detect voice activity segments (VAD)
3. Match OCR text with voice onset timing
4. Apply "Audio Priority" rule: delay subtitle until voice onset
"""

import os
import subprocess
import tempfile
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Try to import audio processing libraries
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("Warning: librosa not installed. Install with: pip install librosa")


@dataclass
class VoiceSegment:
    """Represents a detected voice/speech segment"""
    start: float
    end: float
    energy: float = 0.0  # Average energy level


class AudioSync:
    """
    Voice Activity Detection and OCR-Audio synchronization.
    Uses energy-based VAD for simplicity (no WebRTC VAD dependency).
    """
    
    def __init__(self, 
                 energy_threshold: float = 0.01,
                 min_speech_duration: float = 0.2,
                 min_silence_duration: float = 0.3):
        """
        Args:
            energy_threshold: Minimum energy level to consider as speech
            min_speech_duration: Minimum duration (seconds) for valid speech segment
            min_silence_duration: Minimum silence gap to separate segments
        """
        self.energy_threshold = energy_threshold
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
    
    def extract_audio(self, video_path: str, output_path: str = None) -> str:
        """
        Extract audio from video using FFmpeg.
        Returns path to extracted audio file.
        """
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".wav")
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"[AudioSync] FFmpeg error: {e}")
            return None
    
    def load_audio(self, audio_path: str) -> Tuple[any, int]:
        """Load audio file and return (waveform, sample_rate)"""
        if not LIBROSA_AVAILABLE:
            raise ImportError("librosa not available. Install with: pip install librosa")
        
        waveform, sr = librosa.load(audio_path, sr=16000, mono=True)
        return waveform, sr
    
    def detect_voice_segments(self, waveform, sr: int) -> List[VoiceSegment]:
        """
        Detect speech segments using energy-based VAD.
        
        Returns: List of VoiceSegment with start, end times
        """
        if not NUMPY_AVAILABLE:
            raise ImportError("numpy not available")
        
        # Calculate short-time energy
        frame_length = int(sr * 0.025)  # 25ms frames
        hop_length = int(sr * 0.010)    # 10ms hop
        
        # Compute RMS energy per frame
        energy = librosa.feature.rms(y=waveform, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Normalize energy
        energy = energy / (np.max(energy) + 1e-10)
        
        # Find frames above threshold
        speech_frames = energy > self.energy_threshold
        
        # Convert frame indices to time
        frame_times = librosa.frames_to_time(np.arange(len(energy)), sr=sr, hop_length=hop_length)
        
        # Find contiguous speech regions
        segments = []
        in_speech = False
        start_time = 0
        
        for i, is_speech in enumerate(speech_frames):
            time = frame_times[i]
            
            if is_speech and not in_speech:
                # Speech start
                in_speech = True
                start_time = time
            elif not is_speech and in_speech:
                # Speech end
                in_speech = False
                duration = time - start_time
                if duration >= self.min_speech_duration:
                    avg_energy = float(np.mean(energy[max(0, i-int(duration/0.01)):i]))
                    segments.append(VoiceSegment(
                        start=start_time,
                        end=time,
                        energy=avg_energy
                    ))
        
        # Handle case where speech continues to end
        if in_speech:
            end_time = frame_times[-1]
            duration = end_time - start_time
            if duration >= self.min_speech_duration:
                segments.append(VoiceSegment(
                    start=start_time,
                    end=end_time,
                    energy=float(np.mean(energy[-int(duration/0.01):]))
                ))
        
        print(f"[AudioSync] Detected {len(segments)} voice segments")
        return segments
    
    def detect_from_video(self, video_path: str) -> List[VoiceSegment]:
        """
        Full pipeline: Extract audio from video and detect voice segments.
        """
        print(f"[AudioSync] Extracting audio from: {video_path}")
        
        audio_path = self.extract_audio(video_path)
        if not audio_path:
            return []
        
        try:
            waveform, sr = self.load_audio(audio_path)
            segments = self.detect_voice_segments(waveform, sr)
            return segments
        finally:
            # Cleanup temp audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
    
    def sync_ocr_with_audio(self, 
                            ocr_segments: List[dict], 
                            voice_segments: List[VoiceSegment],
                            max_delay: float = 1.5) -> List[dict]:
        """
        Sync OCR text with voice onset timing.
        
        Rule: If OCR detects text at T1 but voice starts at T2 > T1,
              delay subtitle to T2 (but max delay = max_delay seconds).
        
        Args:
            ocr_segments: List of {"start": float, "end": float, "text": str}
            voice_segments: List of VoiceSegment from VAD
            max_delay: Maximum allowed delay in seconds
        
        Returns: List of synced segments with adjusted timing
        """
        if not ocr_segments or not voice_segments:
            return ocr_segments
        
        synced = []
        
        for ocr_seg in ocr_segments:
            ocr_start = ocr_seg["start"]
            ocr_end = ocr_seg["end"]
            text = ocr_seg["text"]
            
            # Find nearest voice onset after OCR start
            voice_onset = self._find_voice_onset(ocr_start, voice_segments, max_delay)
            
            if voice_onset is not None and voice_onset > ocr_start:
                # Apply audio priority: delay subtitle to voice onset
                delay = voice_onset - ocr_start
                new_start = voice_onset
                new_end = ocr_end + delay
                
                # print(f"[Sync] Delayed '{text[:20]}...' by {delay:.2f}s")
            else:
                # No voice found, keep original timing
                new_start = ocr_start
                new_end = ocr_end
            
            synced.append({
                "start": new_start,
                "end": new_end,
                "text": text
            })
        
        return synced
    
    def _find_voice_onset(self, 
                          target_time: float, 
                          voice_segments: List[VoiceSegment],
                          max_delay: float) -> Optional[float]:
        """Find the nearest voice onset time after target_time within max_delay"""
        for seg in voice_segments:
            # Check if voice starts within acceptable range
            if seg.start >= target_time and seg.start <= target_time + max_delay:
                return seg.start
            # Check if we're inside a voice segment
            if seg.start <= target_time <= seg.end:
                return target_time  # Already during speech
        
        return None


def detect_voice_segments(video_path: str, **kwargs) -> List[dict]:
    """
    Convenience function to detect voice segments from video.
    
    Returns: List of {"start": float, "end": float}
    """
    sync = AudioSync(**kwargs)
    segments = sync.detect_from_video(video_path)
    return [{"start": s.start, "end": s.end} for s in segments]


def sync_ocr_with_audio(ocr_segments: List[dict], 
                        voice_segments: List[dict],
                        **kwargs) -> List[dict]:
    """
    Convenience function to sync OCR segments with audio timing.
    """
    sync = AudioSync(**kwargs)
    voice_segs = [VoiceSegment(start=v["start"], end=v["end"]) for v in voice_segments]
    return sync.sync_ocr_with_audio(ocr_segments, voice_segs)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python audio_sync.py <video_path>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    print(f"Detecting voice segments in: {video_path}")
    
    segments = detect_voice_segments(video_path)
    
    print(f"\nFound {len(segments)} voice segments:")
    for i, seg in enumerate(segments[:20]):  # Show first 20
        print(f"  {i+1}. [{seg['start']:.2f}s - {seg['end']:.2f}s]")
