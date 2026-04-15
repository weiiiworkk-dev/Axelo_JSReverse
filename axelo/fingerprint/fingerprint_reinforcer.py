"""Device fingerprint reinforcer - Enhanced device fingerprint generation."""
from __future__ import annotations

import hashlib
import inspect
import random
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class DeviceFingerprint:
    """Complete device fingerprint."""
    canvas_hash: str
    audio_hash: str
    webgl_vendor: str
    webgl_renderer: str
    fonts: list[str]
    timezone: str
    screen_resolution: str
    platform: str
    
    def with_noise(self, noise_level: float = 0.05) -> "DeviceFingerprint":
        """Add realistic noise to fingerprint."""
        # Only add noise to hash values
        return DeviceFingerprint(
            canvas_hash=self._add_hash_noise(self.canvas_hash, noise_level),
            audio_hash=self._add_hash_noise(self.audio_hash, noise_level),
            webgl_vendor=self.webgl_vendor,
            webgl_renderer=self.webgl_renderer,
            fonts=self.fonts,
            timezone=self.timezone,
            screen_resolution=self.screen_resolution,
            platform=self.platform,
        )
    
    def _add_hash_noise(self, hash_val: str, level: float) -> str:
        """Add noise to hash by flipping a few characters."""
        if not hash_val or len(hash_val) < 8:
            return hash_val
        
        chars = list(hash_val)
        num_flips = max(1, int(len(chars) * level))
        
        for _ in range(num_flips):
            idx = random.randint(0, len(chars) - 1)
            chars[idx] = random.choice("0123456789abcdef")
        
        return ''.join(chars)


class CanvasFingerprintGenerator:
    """Canvas fingerprint generator - Generate unique canvas signatures."""
    
    def __init__(self, seed: int | None = None):
        self._random = random.Random(seed)
    
    def generate(self, profile: "BrowserProfile") -> str:
        """Generate canvas fingerprint.
        
        Args:
            profile: Browser profile with customization options
            
        Returns:
            MD5 hash of canvas data
        """
        # Create canvas element
        canvas_code = self._generate_canvas_code(profile)
        
        # Execute in browser context would produce actual fingerprint
        # For now, generate based on profile characteristics
        fingerprint_data = self._generate_fingerprint_data(profile)
        
        return hashlib.md5(fingerprint_data.encode()).hexdigest()
    
    def _generate_canvas_code(self, profile: "BrowserProfile") -> str:
        """Generate canvas rendering code."""
        # Text with various styles to create unique signature
        elements = [
            f"ctx.fillText('{self._random_text(10)}', 10, 50)",
            f"ctx.fillText('{self._random_text(8)}', 20, 80)",
            f"ctx.font = '{self._random.choice(['20px Arial', '18px Roboto', '16px sans-serif'])}'",
            f"ctx.fillStyle = '{self._random.choice(['#000', '#333', '#666'])}'",
            f"ctx.fillRect(5, 5, {self._random.randint(50, 100)}, {self._random.randint(20, 50)})",
        ]
        
        return "\n".join(elements)
    
    def _generate_fingerprint_data(self, profile: "BrowserProfile") -> str:
        """Generate fingerprint data from profile."""
        components = [
            getattr(profile, "user_agent", "") or "",
            getattr(profile, "platform", "") or "",
            getattr(profile, "webgl_vendor", "") or "",
            getattr(profile, "webgl_renderer", "") or "",
            getattr(profile, "timezone", "") or "",
            str(getattr(profile, "screen_resolution", "") or ""),
        ]
        
        # Add some randomness
        components.append(str(self._random.randint(0, 10000)))
        
        return "|".join(components)
    
    def _random_text(self, length: int) -> str:
        """Generate random text."""
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return ''.join(self._random.choice(chars) for _ in range(length))


class AudioFingerprintGenerator:
    """Audio fingerprint generator - Generate unique audio context signatures."""
    
    def __init__(self, seed: int | None = None):
        self._random = random.Random(seed)
    
    def generate(self, profile: "BrowserProfile") -> str:
        """Generate audio context fingerprint.
        
        Args:
            profile: Browser profile
            
        Returns:
            MD5 hash of audio fingerprint
        """
        # Generate audio processing chain that creates unique output
        audio_data = self._generate_audio_data(profile)
        
        return hashlib.md5(audio_data.encode()).hexdigest()
    
    def _generate_audio_data(self, profile: "BrowserProfile") -> str:
        """Generate audio fingerprint data."""
        components = [
            getattr(profile, "platform", "") or "",
            str(self._random.randint(1000, 10000)),
            self._random.choice(["44100", "48000", "22050"]),
            self._random.choice(["float32", "int16", "int32"]),
        ]
        
        return "|".join(components)


class FontDetector:
    """Font detector - Detect available fonts on system."""
    
    # Common font families to check
    FONT_LIST = [
        "Arial", "Arial Black", "Calibri", "Cambria", "Candara",
        "Comic Sans MS", "Consolas", "Constantia", "Corbel", "Courier New",
        "Georgia", "Impact", "Lucida Console", "Lucida Sans Unicode",
        "Microsoft Sans Serif", "Palatino Linotype", "Segoe UI",
        "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
        "Segoe Print", "Bradley Hand ITC", "Brush Script MT",
        "Algerian", "Baskerville Old Face", "Garamond",
        # Chinese fonts
        "Microsoft YaHei", "SimSun", "SimHei", "KaiTi",
        # Japanese fonts
        "MS Gothic", "MS Mincho", "Yu Gothic", "Meiryo",
        # Korean fonts
        "Malgun Gothic", "Batang", "Gulim",
    ]
    
    def __init__(self):
        self._detected_fonts: set[str] = set()
    
    def detect(self, page: Any | None = None) -> list[str]:
        """Detect available fonts.
        
        Args:
            page: Optional Playwright page for runtime detection
            
        Returns:
            List of detected font names
        """
        if page is not None:
            return self._detect_in_browser_sync(page)
        else:
            # Return default common fonts
            return self._get_default_fonts()
    
    async def detect_async(self, page: Any) -> list[str]:
        """Async detection in browser context."""
        return await self._detect_in_browser_async(page)
    
    def _detect_in_browser_sync(self, page: Any) -> list[str]:
        """Detect fonts in sync-only contexts.

        Playwright's async page API returns awaitables. In sync callers we fall back
        to a default font set instead of creating un-awaited coroutines.
        """
        try:
            evaluate = getattr(page, "evaluate", None)
            if evaluate is None:
                return self._get_default_fonts()
            if inspect.iscoroutinefunction(evaluate):
                return self._get_default_fonts()
            detected = evaluate(self._font_probe_script())
            if inspect.isawaitable(detected):
                return self._get_default_fonts()
            return detected or self._get_default_fonts()
        except Exception as e:
            log.warning("font_detection_failed", error=str(e))
            return self._get_default_fonts()

    async def _detect_in_browser_async(self, page: Any) -> list[str]:
        """Detect fonts by comparing rendered widths."""
        try:
            detected = await page.evaluate(self._font_probe_script())
            return detected or self._get_default_fonts()
        except Exception as e:
            log.warning("font_detection_failed", error=str(e))
            return self._get_default_fonts()

    @staticmethod
    def _font_probe_script() -> str:
        return """
            () => {
                const testFonts = [
                    'Arial', 'Arial Black', 'Calibri', 'Cambria', 'Candara',
                    'Comic Sans MS', 'Consolas', 'Corbel', 'Courier New',
                    'Georgia', 'Impact', 'Lucida Console', 'Microsoft Sans Serif',
                    'Palatino Linotype', 'Segoe UI', 'Tahoma', 'Times New Roman',
                    'Trebuchet MS', 'Verdana'
                ];
                
                const testString = 'mmmmmmmmmmlli';
                const testSize = '72px';
                const testDiv = document.createElement('div');
                
                const defaultWidth = (() => {
                    testDiv.style.fontFamily = 'sans-serif';
                    testDiv.style.fontSize = testSize;
                    testDiv.style.position = 'absolute';
                    testDiv.style.left = '-9999px';
                    testDiv.innerHTML = testString;
                    document.body.appendChild(testDiv);
                    const width = testDiv.offsetWidth;
                    document.body.removeChild(testDiv);
                    return width;
                })();
                
                const available = [];
                for (const font of testFonts) {
                    testDiv.style.fontFamily = `'${font}', sans-serif`;
                    testDiv.innerHTML = testString;
                    document.body.appendChild(testDiv);
                    const width = testDiv.offsetWidth;
                    document.body.removeChild(testDiv);
                    
                    if (width !== defaultWidth) {
                        available.push(font);
                    }
                }
                
                return available;
            }
        """
    
    def _get_default_fonts(self) -> list[str]:
        """Get default font list (when no browser available)."""
        return [
            "Arial", "Calibri", "Consolas", "Courier New",
            "Georgia", "Segoe UI", "Tahoma", "Times New Roman",
            "Verdana", "Microsoft Sans Serif",
        ]


class DeviceFingerprintReinforcer:
    """Device fingerprint reinforcer - Generate complete device fingerprints."""
    
    def __init__(self):
        self._canvas_generator = CanvasFingerprintGenerator()
        self._audio_generator = AudioFingerprintGenerator()
        self._font_detector = FontDetector()
    
    def generate_fingerprint(
        self,
        profile: "BrowserProfile",
        page: Any | None = None
    ) -> DeviceFingerprint:
        """Generate complete device fingerprint.
        
        Args:
            profile: Browser profile
            page: Optional Playwright page for runtime detection
            
        Returns:
            Complete DeviceFingerprint
        """
        # Canvas fingerprint
        canvas_hash = self._canvas_generator.generate(profile)
        
        # Audio fingerprint
        audio_hash = self._audio_generator.generate(profile)
        
        # Font detection
        fonts = self._font_detector.detect(page)
        
        return DeviceFingerprint(
            canvas_hash=canvas_hash,
            audio_hash=audio_hash,
            webgl_vendor=getattr(profile, "webgl_vendor", "") or "",
            webgl_renderer=getattr(profile, "webgl_renderer", "") or "",
            fonts=fonts,
            timezone=getattr(profile, "timezone", "") or "UTC",
            screen_resolution=str(getattr(profile, "screen_resolution", "") or "1920x1080"),
            platform=getattr(profile, "platform", "") or "Win32",
        )

    async def generate_fingerprint_async(
        self,
        profile: "BrowserProfile",
        page: Any | None = None
    ) -> DeviceFingerprint:
        """Generate fingerprint with async browser-aware font detection."""
        canvas_hash = self._canvas_generator.generate(profile)
        audio_hash = self._audio_generator.generate(profile)
        fonts = await self._font_detector.detect_async(page) if page is not None else self._font_detector.detect()

        return DeviceFingerprint(
            canvas_hash=canvas_hash,
            audio_hash=audio_hash,
            webgl_vendor=getattr(profile, "webgl_vendor", "") or "",
            webgl_renderer=getattr(profile, "webgl_renderer", "") or "",
            fonts=fonts,
            timezone=getattr(profile, "timezone", "") or "UTC",
            screen_resolution=str(getattr(profile, "screen_resolution", "") or "1920x1080"),
            platform=getattr(profile, "platform", "") or "Win32",
        )
    
    def make_realistic(
        self, 
        fingerprint: DeviceFingerprint,
        noise_level: float = 0.05
    ) -> DeviceFingerprint:
        """Add realistic noise to fingerprint.
        
        Args:
            fingerprint: Base fingerprint
            noise_level: Amount of noise to add
            
        Returns:
            Fingerprint with noise applied
        """
        return fingerprint.with_noise(noise_level)


# For backward compatibility
class BrowserProfile:
    """Placeholder for browser profile data."""
    user_agent: str = ""
    platform: str = ""
    webgl_vendor: str = ""
    webgl_renderer: str = ""
    timezone: str = ""
    screen_resolution: str = ""


def create_fingerprint_reinforcer() -> DeviceFingerprintReinforcer:
    """Create fingerprint reinforcer instance."""
    return DeviceFingerprintReinforcer()
