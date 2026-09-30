"""
@file backend/app/skills/vision_skill.py
@description Native desktop vision and UI automation skill.

Provides screenshot capture, OCR-based text detection, and controlled
mouse/keyboard actions through regular Python callables. UI-changing actions
remain approval-gated by the ToolGateway.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Callable, Dict, List, Optional

import pyautogui
from PIL import Image, ImageGrab

from app.skills.base import (
    BaseSkill,
    RiskLevel,
    SkillMetadata,
    ToolMetadata,
)


# ==============================================================================
# VISION TOOLS
# ==============================================================================


def find_text_on_screen(
    text_to_find: str,
) -> str:
    """
    Locate matching text on the current screen using OCR.
    """
    if not text_to_find.strip():
        raise ValueError(
            "Text to find cannot be empty."
        )

    try:
        import easyocr
        import numpy as np

        reader = easyocr.Reader(
            ["en", "it"],
            gpu=False,
        )

        image = ImageGrab.grab()
        image_array = np.array(image)

        results = reader.readtext(
            image_array
        )

        matches: List[str] = []

        for bbox, detected_text, confidence in results:
            if text_to_find.lower() not in detected_text.lower():
                continue

            x = int(
                (
                    bbox[0][0]
                    + bbox[1][0]
                )
                / 2
            )

            y = int(
                (
                    bbox[0][1]
                    + bbox[2][1]
                )
                / 2
            )

            matches.append(
                (
                    f"Found '{detected_text}' at "
                    f"X={x}, Y={y} "
                    f"(confidence: {confidence:.2f})"
                )
            )

        if not matches:
            return (
                f"Text '{text_to_find}' "
                "was not found on screen."
            )

        return "\n".join(matches)

    except ImportError:
        return "OCR Error: easyocr is not installed."

    except Exception as exc:
        return f"OCR Error: {exc}"


def take_screenshot() -> str:
    """
    Capture the primary display and return a compact base64 JPEG payload.
    """
    try:
        image = ImageGrab.grab()

        image.thumbnail(
            (1280, 720),
            Image.Resampling.LANCZOS,
        )

        buffer = BytesIO()

        image.save(
            buffer,
            format="JPEG",
            quality=80,
        )

        encoded = base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")

        return (
            "data:image/jpeg;base64,"
            f"{encoded}"
        )

    except Exception as exc:
        return f"Screenshot Error: {exc}"


def execute_ui_action(
    action: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    text: Optional[str] = None,
    keys: Optional[str] = None,
    amount: Optional[int] = None,
) -> str:
    """
    Execute one explicit desktop UI action.

    Supported actions:
    - click
    - type
    - hotkey
    - scroll
    """
    try:
        if action == "click":
            if x is None or y is None:
                return (
                    "Error: x and y coordinates "
                    "are required for click."
                )

            pyautogui.click(
                x=x,
                y=y,
            )

            return f"Clicked at ({x}, {y})."

        if action == "type":
            if text is None:
                return (
                    "Error: text is required "
                    "for type."
                )

            pyautogui.write(
                text,
                interval=0.05,
            )

            return "Text input completed."

        if action == "hotkey":
            if not keys:
                return (
                    "Error: keys are required "
                    "for hotkey."
                )

            key_list = [
                key.strip()
                for key in keys.split(",")
                if key.strip()
            ]

            if not key_list:
                return "Error: no valid hotkey keys provided."

            pyautogui.hotkey(
                *key_list
            )

            return "Hotkey executed successfully."

        if action == "scroll":
            if amount is None:
                return (
                    "Error: amount is required "
                    "for scroll."
                )

            pyautogui.scroll(
                amount
            )

            return "Scroll action completed."

        return (
            f"Unknown UI action '{action}'."
        )

    except Exception as exc:
        return f"UI automation error: {exc}"


# ==============================================================================
# VISION SKILL
# ==============================================================================


class VisionSkill(BaseSkill):
    """
    Provides controlled screen perception and UI interaction.
    """

    def __init__(self) -> None:
        """
        Initialize the desktop automation safety settings.
        """
        super().__init__()

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

    @property
    def metadata(self) -> SkillMetadata:
        """
        Return desktop vision skill metadata.
        """
        return SkillMetadata(
            name="computer_vision",
            description=(
                "Provides screen capture, OCR-based text detection, "
                "and approval-gated desktop UI interaction."
            ),
            version="1.0.0",
        )

    @property
    def tools(self) -> List[Callable]:
        """
        Return executable vision tools.
        """
        return [
            take_screenshot,
            execute_ui_action,
            find_text_on_screen,
        ]

    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        """
        Return security and execution metadata for all vision tools.
        """
        return {
            "take_screenshot": ToolMetadata(
                name="take_screenshot",
                description=(
                    "Capture the current primary display "
                    "as a base64 JPEG image."
                ),
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                permissions_required=[],
                network_access=False,
                filesystem_access=False,
                max_runtime=15,
                max_output=2_000_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="desktop-vision",
                audit_policy="standard",
            ),
            "find_text_on_screen": ToolMetadata(
                name="find_text_on_screen",
                description=(
                    "Use OCR to locate matching text "
                    "on the current display."
                ),
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                permissions_required=[],
                network_access=False,
                filesystem_access=False,
                max_runtime=30,
                max_output=8_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "text_to_find": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": [
                        "text_to_find"
                    ],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="desktop-vision",
                audit_policy="standard",
            ),
            "execute_ui_action": ToolMetadata(
                name="execute_ui_action",
                description=(
                    "Perform a mouse or keyboard action "
                    "on the host desktop."
                ),
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                permissions_required=[],
                network_access=False,
                filesystem_access=False,
                max_runtime=15,
                max_output=2_000,
                max_cost=0.0,
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "click",
                                "type",
                                "hotkey",
                                "scroll",
                            ],
                        },
                        "x": {
                            "type": "integer",
                        },
                        "y": {
                            "type": "integer",
                        },
                        "text": {
                            "type": "string",
                        },
                        "keys": {
                            "type": "string",
                        },
                        "amount": {
                            "type": "integer",
                        },
                    },
                    "required": [
                        "action"
                    ],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "string",
                },
                sandbox_profile="desktop-control",
                audit_policy="standard",
            ),
        }

    @property
    def system_prompt_extension(self) -> Optional[str]:
        """
        Return desktop-vision instructions.
        """
        return (
            "You have controlled access to the host display. "
            "Use 'take_screenshot' to inspect the screen and "
            "'find_text_on_screen' to locate visible text precisely. "
            "Never guess UI coordinates. Any mouse or keyboard action "
            "is high risk and requires explicit approval."
        )


def get_skill() -> BaseSkill:
    """
    Create the computer vision skill instance.
    """
    return VisionSkill()