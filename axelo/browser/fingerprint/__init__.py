"""
Browser Fingerprint Randomization Module

Provides comprehensive anti-detection features:
- Canvas fingerprint randomization
- AudioContext fingerprint spoofing  
- WebGL fingerprint spoofing
- Navigator property spoofing
- Screen/Window property spoofing
"""

from __future__ import annotations

import random
from typing import Any


class CanvasFingerprintRandomizer:
    """Canvas fingerprint randomization - adds noise to Canvas rendering"""
    
    async def inject(self, page: Any) -> None:
        """Inject Canvas fingerprint randomization"""
        await page.add_init_script("""
            (function() {
                'use strict';
                
                // Canvas fingerprint randomization
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    try {
                        const ctx = this.getContext('2d');
                        if (ctx) {
                            // Get current image data
                            try {
                                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                                const data = imageData.data;
                                // Add subtle RGB noise
                                for (let i = 0; i < data.length; i += 4) {
                                    data[i] = (data[i] + (Math.random() * 2 - 1)) | 0;
                                    data[i+1] = (data[i+1] + (Math.random() * 2 - 1)) | 0;
                                    data[i+2] = (data[i+2] + (Math.random() * 2 - 1)) | 0;
                                }
                                ctx.putImageData(imageData, 0, 0);
                            } catch(e) {}
                        }
                    } catch(e) {}
                    return originalToDataURL.call(this, type);
                };
                
                // Canvas toBlob randomization
                const originalToBlob = HTMLCanvasElement.prototype.toBlob;
                HTMLCanvasElement.prototype.toBlob = function(callback, type) {
                    // Add noise before blob creation
                    try {
                        const ctx = this.getContext('2d');
                        if (ctx) {
                            try {
                                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                                const data = imageData.data;
                                for (let i = 0; i < data.length; i += 4) {
                                    data[i] = (data[i] + (Math.random() * 2 - 1)) | 0;
                                }
                                ctx.putImageData(imageData, 0, 0);
                            } catch(e) {}
                        }
                    } catch(e) {}
                    return originalToBlob.call(this, callback, type);
                };
                
                console.log('[Axelo] Canvas fingerprint randomizer loaded');
            })();
        """)


class AudioFingerprintRandomizer:
    """AudioContext fingerprint spoofing"""
    
    async def inject(self, page: Any) -> None:
        """Inject AudioContext fingerprint spoofing"""
        await page.add_init_script("""
            (function() {
                'use strict';
                
                // AudioContext fingerprint spoofing
                const originalCreateBuffer = AudioContext.prototype.createBuffer;
                AudioContext.prototype.createBuffer = function(channels, length, sampleRate) {
                    const buffer = originalCreateBuffer.call(this, channels, length, sampleRate);
                    try {
                        // Add subtle noise to audio data
                        for (let c = 0; c < channels; c++) {
                            const data = buffer.getChannelData(c);
                            for (let i = 0; i < data.length; i += 100) {
                                data[i] += (Math.random() - 0.5) * 0.0001;
                            }
                        }
                    } catch(e) {}
                    return buffer;
                };
                
                // AudioContext destination node
                const originalDestination = Object.getOwnPropertyDescriptor(AudioContext.prototype, 'destination');
                Object.defineProperty(AudioContext.prototype, 'destination', {
                    get: function() {
                        return originalDestination.get.call(this);
                    }
                });
                
                console.log('[Axelo] AudioContext fingerprint randomizer loaded');
            })();
        """)


class WebGLFingerprintRandomizer:
    """WebGL fingerprint spoofing"""
    
    VENDORS = [
        "NVIDIA GeForce RTX 3080/PCIe/SSE2",
        "AMD Radeon RX 6800 XT",
        "Intel Iris OpenGL Renderer",
        "Apple M1",
        "Google SwiftShader",
    ]
    
    RENDERERS = [
        "NVIDIA GeForce RTX 3080",
        "AMD Radeon RX 6800 XT",
        "Intel Iris OpenGL",
        "Apple M1",
        "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)",
    ]
    
    async def inject(self, page: Any) -> None:
        """Inject WebGL fingerprint spoofing"""
        vendor = random.choice(self.VENDORS)
        renderer = random.choice(self.RENDERERS)
        
        await page.add_init_script(f"""
            (function() {{
                'use strict';
                
                const VENDOR = "{vendor}";
                const RENDERER = "{renderer}";
                
                // WebGL vendor/renderer spoofing
                const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                    if (parameter === 37445) return VENDOR;  // UNMASKED_VENDOR_WEBGL
                    if (parameter === 37446) return RENDERER;  // UNMASKED_RENDERER_WEBGL
                    return originalGetParameter.call(this, parameter);
                }};
                
                // WebGL2
                const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                    if (parameter === 37445) return VENDOR;
                    if (parameter === 37446) return RENDERER;
                    return originalGetParameter2.call(this, parameter);
                }};
                
                console.log('[Axelo] WebGL fingerprint randomizer loaded');
            }})();
        """)


class NavigatorFingerprintRandomizer:
    """Navigator property spoofing"""
    
    async def inject(self, page: Any) -> None:
        """Inject Navigator fingerprint spoofing"""
        await page.add_init_script("""
            (function() {
                'use strict';
                
                // hardwareConcurrency spoofing
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: function() { return 8; }
                });
                
                // deviceMemory spoofing
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: function() { return 8; }
                });
                
                // connection spoofing
                if (navigator.connection) {
                    Object.defineProperty(navigator, 'connection', {
                        get: function() {
                            return {
                                effectiveType: '4g',
                                downlink: 10,
                                rtt: 50,
                                saveData: false,
                                type: 'wifi'
                            };
                        }
                    });
                }
                
                // Permissions spoofing
                const originalQuery = navigator.permissions ? navigator.permissions.query.bind(navigator.permissions) : null;
                if (originalQuery) {
                    navigator.permissions.query = function(permission) {
                        if (permission.name === 'notifications') {
                            return Promise.resolve({ state: 'prompt' });
                        }
                        return originalQuery(permission);
                    };
                }
                
                console.log('[Axelo] Navigator fingerprint randomizer loaded');
            })();
        """)


class ScreenFingerprintRandomizer:
    """Screen property spoofing"""
    
    async def inject(self, page: Any) -> None:
        """Inject Screen fingerprint spoofing"""
        await page.add_init_script("""
            (function() {
                'use strict';
                
                // Screen spoofing
                Object.defineProperty(screen, 'availWidth', {
                    get: function() { return 1920; }
                });
                Object.defineProperty(screen, 'availHeight', {
                    get: function() { return 1080; }
                });
                Object.defineProperty(screen, 'width', {
                    get: function() { return 1920; }
                });
                Object.defineProperty(screen, 'height', {
                    get: function() { return 1080; }
                });
                Object.defineProperty(screen, 'colorDepth', {
                    get: function() { return 24; }
                });
                Object.defineProperty(screen, 'pixelDepth', {
                    get: function() { return 24; }
                });
                
                // Window spoofing
                Object.defineProperty(window, 'innerWidth', {
                    get: function() { return 1920; }
                });
                Object.defineProperty(window, 'innerHeight', {
                    get: function() { return 969; }
                });
                Object.defineProperty(window, 'outerWidth', {
                    get: function() { return 1920; }
                });
                Object.defineProperty(window, 'outerHeight', {
                    get: function() { return 1080; }
                });
                Object.defineProperty(window, 'screenX', {
                    get: function() { return 0; }
                });
                Object.defineProperty(window, 'screenY', {
                    get: function() { return 0; }
                });
                Object.defineProperty(window, 'screenLeft', {
                    get: function() { return 0; }
                });
                Object.defineProperty(window, 'screenTop', {
                    get: function() { return 0; }
                });
                
                console.log('[Axelo] Screen fingerprint randomizer loaded');
            })();
        """)


class FingerprintInjector:
    """Unified fingerprint injection system"""
    
    def __init__(self):
        self.canvas = CanvasFingerprintRandomizer()
        self.audio = AudioFingerprintRandomizer()
        self.webgl = WebGLFingerprintRandomizer()
        self.navigator = NavigatorFingerprintRandomizer()
        self.screen = ScreenFingerprintRandomizer()
    
    async def inject_all(self, page: Any) -> None:
        """Inject all fingerprint randomizations"""
        await self.canvas.inject(page)
        await self.audio.inject(page)
        await self.webgl.inject(page)
        await self.navigator.inject(page)
        await self.screen.inject(page)


# Export all classes
__all__ = [
    "CanvasFingerprintRandomizer",
    "AudioFingerprintRandomizer", 
    "WebGLFingerprintRandomizer",
    "NavigatorFingerprintRandomizer",
    "ScreenFingerprintRandomizer",
    "FingerprintInjector",
]
