"""Mouse movement simulator - Natural human-like mouse behavior."""
from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class Point:
    """2D point."""
    x: float
    y: float


class VelocityModel:
    """Velocity model - Human mouse movement speed variation."""
    
    def get_velocity_at(self, progress: float) -> float:
        """Return current velocity based on progress (0-1).
        
        Human movement:
        - Start (0-20%): Acceleration
        - Middle (20-80%): Cruising with fluctuation
        - End (80-100%): Deceleration
        """
        if progress < 0.2:
            return self._accelerating_phase(progress)
        elif progress < 0.8:
            return self._cruising_phase(progress)
        else:
            return self._decelerating_phase(progress)
    
    def _accelerating_phase(self, p: float) -> float:
        """Acceleration phase: 20 -> 40 pixels/sec."""
        base = 20 + p * 100  # 20 -> 40
        return base + random.gauss(0, 10)
    
    def _cruising_phase(self, p: float) -> float:
        """Cruising phase: ~40 pixels/sec with fluctuation."""
        base = 40 + math.sin(p * 10) * 15  # fluctuation
        return base + random.gauss(0, 8)
    
    def _decelerating_phase(self, p: float) -> float:
        """Deceleration phase: 40 -> 10 pixels/sec."""
        base = 40 - (p - 0.8) * 150  # 40 -> 10
        return max(5, base + random.gauss(0, 5))


class JitterGenerator:
    """Jitter generator - Add random offset to simulate human imperfection."""
    
    def __init__(self, intensity: float = 3.0):
        self._intensity = intensity
    
    def get_jitter(self, progress: float) -> Point:
        """Return jitter offset based on progress.
        
        Jitter is higher in the middle of movement,
        lower at start and end.
        """
        # Parabolic jitter intensity
        if progress < 0.1 or progress > 0.9:
            factor = 0.3
        else:
            factor = 1.0
        
        jitter_range = self._intensity * factor
        
        return Point(
            x=random.uniform(-jitter_range, jitter_range),
            y=random.uniform(-jitter_range, jitter_range),
        )


class BezierCurve:
    """Cubic Bezier curve for natural path generation."""
    
    @staticmethod
    def generate_points(
        p0: Point, p1: Point, p2: Point, p3: Point, steps: int
    ) -> list[Point]:
        """Generate points along a cubic Bezier curve."""
        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            x = (1 - t) ** 3 * p0.x + \
                3 * (1 - t) ** 2 * t * p1.x + \
                3 * (1 - t) * t ** 2 * p2.x + \
                t ** 3 * p3.x
            y = (1 - t) ** 3 * p0.y + \
                3 * (1 - t) ** 2 * t * p1.y + \
                3 * (1 - t) * t ** 2 * p2.y + \
                t ** 3 * p3.y
            points.append(Point(x, y))
        return points
    
    @staticmethod
    def generate_control_points(start: Point, end: Point, distance: float) -> tuple[Point, Point]:
        """Generate control points for a natural curve."""
        # Calculate direction
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.sqrt(dx * dx + dy * dy)
        
        if length < 1:
            # Too close, just return start/end
            return start, end
        
        # Normalize direction
        ux = dx / length
        uy = dy / length
        
        # Perpendicular direction
        px = -uy
        py = ux
        
        # Control point offset (30-50% of distance)
        offset = distance * random.uniform(0.3, 0.5)
        
        # Randomize which side of the path
        side = random.choice([-1, 1])
        
        # Midpoint
        mid = Point(
            x=(start.x + end.x) / 2,
            y=(start.y + end.y) / 2,
        )
        
        # Control points with slight curve
        cp1 = Point(
            x=start.x + dx * 0.33 + px * offset * side * random.uniform(0.5, 1.0),
            y=start.y + dy * 0.33 + py * offset * side * random.uniform(0.5, 1.0),
        )
        cp2 = Point(
            x=start.x + dx * 0.66 + px * offset * side * random.uniform(0.5, 1.0),
            y=start.y + dy * 0.66 + py * offset * side * random.uniform(0.5, 1.0),
        )
        
        return cp1, cp2


class MouseMovementSimulator:
    """Mouse movement simulator - Generate natural human-like movement轨迹."""
    
    def __init__(
        self,
        min_duration: float = 300,
        max_duration: float = 800,
        jitter_intensity: float = 3.0,
    ):
        """Initialize simulator.
        
        Args:
            min_duration: Minimum movement duration in ms
            max_duration: Maximum movement duration in ms
            jitter_intensity: Jitter intensity in pixels
        """
        self._current_position = Point(0, 0)
        self._velocity_model = VelocityModel()
        self._jitter_generator = JitterGenerator(jitter_intensity)
        self._min_duration = min_duration
        self._max_duration = max_duration
    
    @property
    def current_position(self) -> Point:
        """Get current position."""
        return self._current_position
    
    @current_position.setter
    def current_position(self, pos: Point) -> None:
        """Set current position (e.g., after page load)."""
        self._current_position = pos
    
    async def move_to_element(
        self, page: Any, selector: str, click: bool = True
    ) -> None:
        """Move to element and optionally click.
        
        Args:
            page: Playwright page
            selector: Target element selector
            click: Whether to click after moving
        """
        try:
            # Get target element position
            locator = page.locator(selector)
            box = await locator.bounding_box()
            
            if box is None:
                log.warning("element_not_found", selector=selector)
                return
            
            # Target point (center of element with small random offset)
            target = Point(
                x=box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                y=box["y"] + box["height"] / 2 + random.uniform(-5, 5),
            )
            
            # Move to target
            await self.move_to(page, target)
            
            # Small pause before click (human-like)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Click if requested
            if click:
                await self.click(page)
                
        except Exception as e:
            log.error("move_to_element_failed", selector=selector, error=str(e))
            raise
    
    async def move_to(self, page: Any, target: Point) -> None:
        """Move to target point using natural movement.
        
        Args:
            page: Playwright page
            target: Target point
        """
        # Calculate duration (longer for longer distance)
        distance = self._calculate_distance(self._current_position, target)
        base_duration = random.uniform(self._min_duration, self._max_duration)
        duration = base_duration * (1 + distance / 1000)  # Scale by distance
        duration = max(200, min(duration, 1500))  # Clamp 200-1500ms
        
        # Generate path
        path = self._generate_path(self._current_position, target, duration)
        
        # Execute movement
        await self._execute_path(page, path)
        
        # Update current position
        self._current_position = target
    
    async def click(self, page: Any, button: str = "left") -> None:
        """Perform a human-like click.
        
        Args:
            page: Playwright page
            button: Mouse button ('left', 'right', 'middle')
        """
        # Add small position jitter before click
        jitter_x = random.uniform(-2, 2)
        jitter_y = random.uniform(-2, 2)
        
        current = self._current_position
        await page.mouse.move(current.x + jitter_x, current.y + jitter_y)
        
        # Click with slight randomness
        await asyncio.sleep(random.uniform(0.02, 0.08))
        
        if button == "left":
            await page.mouse.click(
                current.x + jitter_x,
                current.y + jitter_y,
            )
        elif button == "right":
            await page.mouse.click(
                current.x + jitter_x,
                current.y + jitter_y,
                button="right",
            )
        else:
            await page.mouse.click(
                current.x + jitter_x,
                current.y + jitter_y,
                button="middle",
            )
        
        log.debug("mouse_clicked", position=(current.x, current.y))
    
    async def double_click(self, page: Any) -> None:
        """Perform a human-like double click."""
        await self.click(page)
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await self.click(page)
    
    async def hover(self, page: Any, selector: str) -> None:
        """Hover over element without clicking."""
        await self.move_to_element(page, selector, click=False)
    
    def _generate_path(
        self, start: Point, end: Point, duration: float
    ) -> list[Point]:
        """Generate natural movement path."""
        # Calculate distance
        distance = self._calculate_distance(start, end)
        
        # Generate bezier control points
        cp1, cp2 = BezierCurve.generate_control_points(start, end, distance)
        
        # Generate points along curve
        steps = max(10, int(duration / 16))  # ~60fps
        raw_path = BezierCurve.generate_points(start, cp1, cp2, end, steps)
        
        # Add jitter to each point
        path = []
        for i, point in enumerate(raw_path):
            progress = i / len(raw_path)
            jitter = self._jitter_generator.get_jitter(progress)
            path.append(Point(
                x=point.x + jitter.x,
                y=point.y + jitter.y,
            ))
        
        return path
    
    async def _execute_path(self, page: Any, path: list[Point]) -> None:
        """Execute movement along path."""
        if not path:
            return
        
        # First point is current position, skip
        for point in path[1:]:
            await page.mouse.move(point.x, point.y)
            # Variable sleep for natural timing
            await asyncio.sleep(random.uniform(0.014, 0.020))  # 50-70fps
    
    def _calculate_distance(self, p1: Point, p2: Point) -> float:
        """Calculate distance between two points."""
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        return math.sqrt(dx * dx + dy * dy)


class KeyboardSimulator:
    """Keyboard simulator - Natural typing behavior."""
    
    def __init__(
        self,
        base_delay: float = 50,
        delay_variance: float = 30,
        error_rate: float = 0.02,
    ):
        """Initialize keyboard simulator.
        
        Args:
            base_delay: Base delay between keystrokes in ms
            delay_variance: Random variance in ms
            error_rate: Probability of keystroke error (0-1)
        """
        self._base_delay = base_delay
        self._delay_variance = delay_variance
        self._error_rate = error_rate
    
    async def type_text(self, page: Any, text: str, selector: str = None) -> None:
        """Type text with human-like timing.
        
        Args:
            page: Playwright page
            text: Text to type
            selector: Optional input selector to focus first
        """
        if selector:
            await page.locator(selector).click()
            await asyncio.sleep(random.uniform(0.1, 0.2))
        
        for char in text:
            # Randomly make mistakes
            if random.random() < self._error_rate:
                # Type wrong character then backspace
                wrong_char = self._get_wrong_char(char)
                await self._type_char(page, wrong_char)
                await asyncio.sleep(random.uniform(50, 150))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(50, 100))
            
            # Type correct character
            await self._type_char(page, char)
        
        # Small pause after typing
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    async def _type_char(self, page: Any, char: str) -> None:
        """Type a single character."""
        # Handle special characters
        if char in "!@#$%^&*()":
            await page.keyboard.down("Shift")
            await page.keyboard.press(char)
            await page.keyboard.up("Shift")
        elif char == " ":
            await page.keyboard.press("Space")
        elif char == "\n":
            await page.keyboard.press("Enter")
        else:
            await page.keyboard.type(char, delay=random.uniform(20, 80))
        
        # Delay between keystrokes
        delay = self._base_delay + random.uniform(-self._delay_variance, self._delay_variance)
        await asyncio.sleep(max(10, delay) / 1000)
    
    def _get_wrong_char(self, char: str) -> str:
        """Get a plausible wrong character."""
        # QWERTY nearby keys
        nearby = {
            "a": ["q", "w", "s", "x", "z"],
            "b": ["v", "g", "h", "n", " "],
            "c": ["x", "d", "f", "v", " "],
            "d": ["s", "e", "r", "f", "c", "x"],
            "e": ["w", "s", "d", "r", " "],
            "f": ["d", "r", "t", "g", "v", "c"],
            "g": ["f", "t", "y", "h", "b", "v"],
            "h": ["g", "y", "u", "j", "n", "b"],
            "i": ["u", "j", "k", "o", " "],
            "j": ["h", "u", "i", "k", "m", "n"],
            "k": ["j", "i", "o", "l", "m"],
            "l": ["k", "o", "p", " "],
            "m": ["n", "j", "k", " "],
            "n": ["b", "h", "j", "m", " "],
            "o": ["i", "k", "l", "p", " "],
            "p": ["o", "l", " "],
            "q": ["w", "a", " "],
            "r": ["e", "d", "f", "t", " "],
            "s": ["a", "w", "e", "d", "x", "z"],
            "t": ["r", "d", "f", "g", "y"],
            "u": ["y", "h", "j", "i", " "],
            "v": ["c", "f", "g", "b", " "],
            "w": ["q", "a", "s", "e", " "],
            "x": ["z", "s", "d", "c", " "],
            "y": ["t", "g", "h", "u", " "],
            "z": ["a", "s", "x", " "],
        }
        
        if char.lower() in nearby:
            return random.choice(nearby[char.lower()])
        return char


class ScrollSimulator:
    """Scroll simulator - Natural scrolling behavior."""
    
    def __init__(
        self,
        min_pause: float = 500,
        max_pause: float = 2000,
        scroll_amount: int = 300,
    ):
        """Initialize scroll simulator.
        
        Args:
            min_pause: Minimum pause between scrolls in ms
            max_pause: Maximum pause between scrolls in ms
            scroll_amount: Pixels per scroll
        """
        self._min_pause = min_pause
        self._max_pause = max_pause
        self._scroll_amount = scroll_amount
    
    async def scroll_down(self, page: Any, times: int = 3) -> None:
        """Scroll down multiple times with natural pauses.
        
        Args:
            page: Playwright page
            times: Number of scroll actions
        """
        for i in range(times):
            # Random scroll amount
            amount = self._scroll_amount + random.randint(-50, 50)
            
            # Smooth scroll
            await page.evaluate(f"window.scrollBy(0, {amount})")
            
            # Natural pause between scrolls
            if i < times - 1:
                pause = random.uniform(self._min_pause, self._max_pause)
                await asyncio.sleep(pause / 1000)
    
    async def scroll_to_element(self, page: Any, selector: str) -> None:
        """Scroll to element.
        
        Args:
            page: Playwright page
            selector: Target element selector
        """
        # Scroll in chunks
        await page.locator(selector).scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.2, 0.5))


class IdlePatternGenerator:
    """Idle pattern generator - Random idle behavior."""
    
    def __init__(
        self,
        min_idle: float = 1000,
        max_idle: float = 5000,
    ):
        """Initialize idle generator.
        
        Args:
            min_idle: Minimum idle time in ms
            max_idle: Maximum idle time in ms
        """
        self._min_idle = min_idle
        self._max_idle = max_idle
    
    async def random_idle(self, page: Any) -> None:
        """Generate random idle time."""
        idle_time = random.uniform(self._min_idle, self._max_idle)
        log.debug("random_idle", duration_ms=idle_time)
        await asyncio.sleep(idle_time / 1000)
    
    async def micro_idle(self, page: Any) -> None:
        """Generate short idle (micro-break)."""
        idle_time = random.uniform(100, 500)
        await asyncio.sleep(idle_time / 1000)


# Factory function
def create_behavior_simulator() -> dict:
    """Create all behavior simulator instances."""
    return {
        "mouse": MouseMovementSimulator(),
        "keyboard": KeyboardSimulator(),
        "scroll": ScrollSimulator(),
        "idle": IdlePatternGenerator(),
    }