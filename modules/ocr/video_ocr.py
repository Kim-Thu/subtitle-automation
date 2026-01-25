"""
Video OCR Module - Extract hardcoded subtitles from video frames

Pipeline:
1. Extract frames at regular intervals (every 0.5s)
2. Crop to subtitle region (bottom 15-20% of frame)
3. OCR each frame using Tesseract or PaddleOCR
4. Deduplicate consecutive same text
5. Output: List of {start, end, text} segments
"""

import os
import subprocess
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Try to import CV2 and OCR libraries
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: opencv-python not installed. Install with: pip install opencv-python")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("Warning: pytesseract not installed. Install with: pip install pytesseract")


@dataclass
class SubtitleSegment:
    """Represents a detected subtitle segment"""
    start: float
    end: float
    text: str


class VideoOCR:
    """
    Extract hardsub (burned-in subtitles) from video using OCR.
    """
    
    def __init__(self, 
                 frame_interval: float = 0.5,
                 subtitle_region: Tuple[float, float] = (0.80, 1.0),
                 lang: str = "chi_sim+eng",
                 tesseract_path: str = None):
        """
        Args:
            frame_interval: Seconds between frame extractions (default 0.5s)
            subtitle_region: Vertical region as (top%, bottom%) where subtitles appear
            lang: Tesseract language code (chi_sim for Chinese Simplified)
            tesseract_path: Path to tesseract executable (Windows)
        """
        self.frame_interval = frame_interval
        self.subtitle_region = subtitle_region
        self.lang = lang
        
        if tesseract_path and TESSERACT_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Try to find tesseract on Windows
        if TESSERACT_AVAILABLE and os.name == 'nt':
            default_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for path in default_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
    
    def extract_frames(self, video_path: str, output_dir: str = None) -> List[Tuple[float, any]]:
        """
        Extract frames from video at regular intervals.
        
        Returns: List of (timestamp_seconds, frame_array)
        """
        if not CV2_AVAILABLE:
            raise ImportError("OpenCV not available. Install with: pip install opencv-python")
        
        frames = []
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise Exception(f"Cannot open video: {video_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        print(f"[OCR] Video: {duration:.1f}s, {fps:.1f}fps")
        
        frame_skip = int(fps * self.frame_interval)
        frame_num = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_num % frame_skip == 0:
                timestamp = frame_num / fps
                frames.append((timestamp, frame))
            
            frame_num += 1
        
        cap.release()
        print(f"[OCR] Extracted {len(frames)} frames")
        return frames
    
    def crop_subtitle_region(self, frame) -> any:
        """Crop frame to subtitle region (bottom portion)"""
        height = frame.shape[0]
        top = int(height * self.subtitle_region[0])
        bottom = int(height * self.subtitle_region[1])
        return frame[top:bottom, :]
    
    def preprocess_frame(self, frame) -> any:
        """Preprocess frame for better OCR accuracy"""
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Increase contrast
        # Apply thresholding for white text on dark background
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        
        return thresh
    
    def ocr_frame(self, frame, preprocess: bool = True) -> str:
        """Run OCR on a frame and return detected text"""
        if not TESSERACT_AVAILABLE:
            raise ImportError("Tesseract not available. Install with: pip install pytesseract")
        
        if preprocess:
            frame = self.preprocess_frame(frame)
        
        # OCR configuration for subtitle text
        config = '--psm 6 --oem 3'  # Assume uniform block of text
        
        try:
            text = pytesseract.image_to_string(frame, lang=self.lang, config=config)
            return text.strip()
        except Exception as e:
            print(f"[OCR] Error: {e}")
            return ""
    
    def extract_hardsub(self, video_path: str, progress_callback=None) -> List[SubtitleSegment]:
        """
        Full pipeline: Extract all hardsub text with timestamps from video.
        
        Returns: List of SubtitleSegment with start, end, text
        """
        frames = self.extract_frames(video_path)
        
        if not frames:
            return []
        
        # OCR each frame
        raw_detections = []
        total = len(frames)
        
        for i, (timestamp, frame) in enumerate(frames):
            if progress_callback:
                progress_callback(int((i / total) * 100))
            
            # Crop to subtitle region
            sub_region = self.crop_subtitle_region(frame)
            
            # OCR
            text = self.ocr_frame(sub_region)
            
            if text:
                raw_detections.append({
                    "timestamp": timestamp,
                    "text": text
                })
        
        print(f"[OCR] Detected text in {len(raw_detections)} frames")
        
        # Merge consecutive same text
        segments = self._merge_detections(raw_detections)
        
        print(f"[OCR] Merged into {len(segments)} segments")
        return segments
    
    def _merge_detections(self, detections: List[dict]) -> List[SubtitleSegment]:
        """Merge consecutive frames with same text into segments"""
        if not detections:
            return []
        
        segments = []
        current_text = detections[0]["text"]
        start_time = detections[0]["timestamp"]
        end_time = start_time + self.frame_interval
        
        for detection in detections[1:]:
            text = detection["text"]
            timestamp = detection["timestamp"]
            
            # Check if text is similar (fuzzy match for OCR errors)
            if self._text_similar(current_text, text):
                # Extend current segment
                end_time = timestamp + self.frame_interval
            else:
                # Save current segment and start new one
                if current_text.strip():
                    segments.append(SubtitleSegment(
                        start=start_time,
                        end=end_time,
                        text=self._clean_text(current_text)
                    ))
                current_text = text
                start_time = timestamp
                end_time = timestamp + self.frame_interval
        
        # Don't forget last segment
        if current_text.strip():
            segments.append(SubtitleSegment(
                start=start_time,
                end=end_time,
                text=self._clean_text(current_text)
            ))
        
        return segments
    
    def _text_similar(self, text1: str, text2: str, threshold: float = 0.8) -> bool:
        """Check if two texts are similar (fuzzy match for OCR errors)"""
        if not text1 or not text2:
            return False
        
        # Simple character overlap ratio
        set1 = set(text1.replace(" ", ""))
        set2 = set(text2.replace(" ", ""))
        
        if not set1 or not set2:
            return False
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return (intersection / union) >= threshold
    
    def _clean_text(self, text: str) -> str:
        """Clean OCR text"""
        # Remove excessive whitespace
        text = " ".join(text.split())
        # Remove common OCR artifacts
        text = text.replace("|", "").replace("_", "")
        return text.strip()


def extract_hardsub(video_path: str, **kwargs) -> List[dict]:
    """
    Convenience function to extract hardsub from video.
    
    Returns: List of {"start": float, "end": float, "text": str}
    """
    ocr = VideoOCR(**kwargs)
    segments = ocr.extract_hardsub(video_path)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python video_ocr.py <video_path>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    print(f"Extracting hardsub from: {video_path}")
    
    segments = extract_hardsub(video_path)
    
    print(f"\nFound {len(segments)} subtitle segments:")
    for i, seg in enumerate(segments[:10]):  # Show first 10
        print(f"  {i+1}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text'][:50]}...")
