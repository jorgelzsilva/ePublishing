import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Centralized configuration for the ePublishing project.
    Following Pragmatic Programming principles (Uniform Access Principle).
    """
    
    # AI Provider Settings
    AI_PROVIDER = os.getenv("AI_PROVIDER", "lm-studio")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "http://192.168.28.70:1234/v1")
    AI_API_KEY = os.getenv("AI_API_KEY", "lm-studio")
    AI_MODEL = os.getenv("AI_MODEL", "qwen3-vl-8b")
    
    # Feature Flags
    ENABLE_VISION_AI = os.getenv("ENABLE_VISION_AI", "False").lower() in ("true", "1", "t", "yes")
    
    # Paths
    EPUBCHECK_JAR = os.getenv("EPUBCHECK_JAR", "epubcheck-5.1.0/epubcheck.jar")
    REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")
    INPUT_DIR = os.getenv("INPUT_DIR", "input")
    
    # Image Validation
    MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "5600000"))
    IMAGE_QUALITY_TOLERANCE = int(os.getenv("IMAGE_QUALITY_TOLERANCE", "2"))
    IMAGE_QUALITY_THRESHOLD = float(os.getenv("IMAGE_QUALITY_THRESHOLD", "0.45"))
