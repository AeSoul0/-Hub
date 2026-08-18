"""
@file backend/app/skills/vision_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import base64
from io import BytesIO
from typing import List, Callable, Dict
from PIL import Image, ImageGrab
import pyautogui
from langchain_core.tools import tool

from app.skills.base import BaseSkill, SkillMetadata, ToolMetadata, RiskLevel

class VisionSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        # PyAutoGUI fail-safe config
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="computer_vision",
            description="Allows A.U.R.O.R.A. to perceive the screen and control the mouse/keyboard.",
            version="1.0.0"
        )
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "take_screenshot": ToolMetadata(
                name="take_screenshot",
                description="Captures the current screen. Returns a base64 encoded image.",
                risk_level=RiskLevel.LOW
            ),
            "execute_ui_action": ToolMetadata(
                name="execute_ui_action",
                description="Executes a mouse or keyboard action. Actions: 'click', 'type', 'hotkey', 'scroll'.",
                risk_level=RiskLevel.HIGH,
                requires_approval=True
            ),
            "find_text_on_screen": ToolMetadata(
                name="find_text_on_screen",
                description="Finds text coordinates on screen using OCR.",
                risk_level=RiskLevel.LOW
            )
        }

    @property
    def tools(self) -> List[Callable]:
        return [take_screenshot, execute_ui_action, find_text_on_screen]
        
    @property
    def system_prompt_extension(self) -> str:
        return (
            "You have direct vision of the host computer. You can use 'take_screenshot' to see the screen.\n"
            "If you need to click on specific text, DO NOT guess the coordinates. Use 'find_text_on_screen' to get the exact X, Y coordinates.\n"
            "To interact, you can use 'execute_ui_action' with actions like 'click' (provide x, y), "
            "'type' (provide text), 'hotkey' (provide keys separated by comma, e.g. 'ctrl,c'), 'scroll' (provide amount).\n"
            "Always rely on 'find_text_on_screen' for precise UI interactions."
        )

@tool
def find_text_on_screen(text_to_find: str) -> str:
    """Finds the exact X, Y coordinates of specific text on the screen using OCR."""
    import easyocr
    import numpy as np
    
    try:
        reader = easyocr.Reader(['en', 'it'], gpu=False)
        image = ImageGrab.grab()
        img_np = np.array(image)
        
        results = reader.readtext(img_np)
        
        matches = []
        for (bbox, text, prob) in results:
            if text_to_find.lower() in text.lower():
                # calculate center of bounding box
                x = int((bbox[0][0] + bbox[1][0]) / 2)
                y = int((bbox[0][1] + bbox[2][1]) / 2)
                matches.append(f"Found '{text}' at X={x}, Y={y} (confidence: {prob:.2f})")
                
        if not matches:
            return f"Text '{text_to_find}' not found on screen."
            
        return "\n".join(matches)
    except Exception as e:
        return f"OCR Error: {str(e)}"

@tool
def take_screenshot() -> str:
    """Captures the primary monitor screen and returns the image as a base64 string."""
    image = ImageGrab.grab()
    
    # Resize if too large to save tokens and speed up parsing
    max_size = (1280, 720)
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=80)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/jpeg;base64,{img_str}"

@tool
def execute_ui_action(action: str, x: int = None, y: int = None, text: str = None, keys: str = None, amount: int = None) -> str:
    """
    Executes a UI automation action.
    - action: 'click', 'type', 'hotkey', 'scroll'
    - x, y: coordinates for click
    - text: string to type
    - keys: comma separated keys for hotkey (e.g. 'ctrl,c')
    - amount: integer for scroll amount
    """
    try:
        if action == "click":
            if x is None or y is None:
                return "Error: x and y coordinates required for click."
            pyautogui.click(x=x, y=y)
            return f"Clicked at ({x}, {y})"
            
        elif action == "type":
            if text is None:
                return "Error: text required for type."
            pyautogui.write(text, interval=0.05)
            return f"Typed: '{text}'"
            
        elif action == "hotkey":
            if keys is None:
                return "Error: keys required for hotkey."
            key_list = [k.strip() for k in keys.split(",")]
            pyautogui.hotkey(*key_list)
            return f"Executed hotkey: {keys}"
            
        elif action == "scroll":
            if amount is None:
                return "Error: amount required for scroll."
            pyautogui.scroll(amount)
            return f"Scrolled by {amount}"
            
        return f"Unknown action: {action}"
    except Exception as e:
        return f"UI Automation Error: {str(e)}"

def get_skill():
    return VisionSkill()
