"""Versioned prompt contracts; users edit descriptions, never these constraints."""
from dataclasses import dataclass
import math

VERSION = 1
DEFAULT_APPEARANCE = (
    "角色：咕咕嘎嘎，穿企鹅连体服的两头身Q版少女。\n"
    "外貌：圆脸、大眼睛、短发，神态可爱温和。\n"
    "服装：深色企鹅连体服、浅色肚皮、\n"
    "带企鹅眼睛与黄色小嘴的帽兜、黄色脚掌。"
)
FIXED_IMAGE = """[FIXED TECHNICAL CONTRACT - NOT USER EDITABLE]

[PURPOSE AND REFERENCE PRIORITY]
Create ONE standard character master image for later desktop pet animation.
The custom appearance describes the character and art style; it is not a request
to animate the character. The technical requirements below take priority.
If a character reference image is supplied, preserve its identity: facial features,
hairstyle, colors, costume and accessories. Do not redesign that character.
Use the reference for identity while applying the canvas and neutral pose below.
If no reference is supplied, create an original character from the custom description.
This image will define the appearance, proportions, scale and placement of all
later animation clips. Do not include any specific example character unless requested.

[CANVAS, CAMERA AND PLACEMENT]
Target canvas: exactly 640 x 360 pixels, landscape 16:9.
Show only one complete character, facing forward, at eye level, with a
near-orthographic view. No wide-angle distortion or strong perspective.
Use two-head-tall chibi proportions: the head is approximately half the full height.
Coordinates start at the upper-left corner; x increases right, y increases down.
Center the body axis at x=320. Place the top of the hair near y=90 and the
standing shoe soles at y=330, for an approximate total character height of 240 pixels.
Keep the hair tips, hands or hand-covering sleeves, clothing hem, accessories and
both shoes fully inside the canvas. Leave clear empty margins on all four sides.
Do not auto-crop, zoom to fill the canvas, stretch the body or change its proportions.
If exact dimensions are unavailable, preserve 16:9 and the same relative placement.

[STANDARD NEUTRAL POSE]
Stand upright with both feet naturally planted at the same ground level.
Keep the head upright, without a sideways tilt.
Let both arms hang naturally, slightly separated from the torso.
Both hands, or the sleeves/mittens covering them, must be fully visible.
Preserve the intended hand design; do not invent exposed fingers for covered hands.
Look toward the viewer with a gentle, slight smile.
No jumping, waving, sitting, walking or handheld props in this master image.
Keep the silhouette reasonably balanced for later animation and horizontal mirroring,
without erasing intentional asymmetrical features of the character design.

[BACKGROUND AND FILE OUTPUT]
Output one PNG image with an opaque background.
Use an opaque, perfectly uniform solid #FF00FF magenta background (RGB 255, 0, 255).
Fill every background area, including gaps between limbs, with this same color.
Do not request or simulate transparency. Never draw a checkerboard.
Background removal will be performed separately after generation.
Reserve the key color for the background only: no magenta or near-magenta colors
on the character, including hair, eyes, clothing, accessories and outlines.
If the requested design requires these colors, ask for a different character
palette before generating; do not silently change the fixed background color.
No background gradients, textures, patterns or noise.
No scenery, visible floor, ground plane, cast shadow, text, watermark, border or glow.
Keep outlines clean, sharp and suitable for background removal.
No magenta reflections, color spill, fringe or colored halos around the character.
Output one full-body image only: no grid, sprite sheet, storyboard, collage,
turnaround, multiple views or multiple characters.
If the required size or file format cannot be produced, disclose the actual specification
outside the image. Do not claim compliance or place explanatory text in the artwork.

[PROHIBITED DEFECTS]
No cropped body parts, duplicate characters, extra or missing limbs, malformed hands
or fingers, mismatched eyes, realistic adult body proportions, strong perspective,
blurred outlines, complex backgrounds or background-colored character edges."""

FIXED_VIDEO = """[FIXED TECHNICAL CONTRACT - NOT USER EDITABLE]

[MASTER IMAGE AND IDENTITY]
Use the uploaded master image as the ONLY character identity reference.
If no master image was supplied, request it before generating the animation.
Preserve the face, eyes, hairstyle, costume, accessories, colors, outlines,
shading style and two-head-tall proportions shown in that image.
Do not redesign the character, change clothing or introduce new props.
Preserve covered hands or mitten-like sleeves; do not invent exposed fingers.
The custom appearance is supporting context. If it conflicts with the master image,
follow the master image for identity. Follow this contract for technical constraints
and the fixed action contract for orientation and loop/return behavior.

[CANVAS, CAMERA AND STABLE PLACEMENT]
Target video: exactly 640 x 360 pixels, landscape 16:9, at 24 fps.
Use the duration and frame count specified at the beginning of this prompt.
Show exactly one full-body character in one continuous shot.
Use a fixed eye-level, near-orthographic camera with no strong perspective.
Coordinates start at the upper-left corner; x increases right, y increases down.
Neutral pose reference: body axis x=320, hair top near y=90, standing soles y=330.
Keep the master image's character scale constant across the entire clip.
Keep hair tips, hands/sleeves, clothing, accessories and shoes inside the canvas
with clear margins in every frame. Reduce action amplitude if it would cause cropping.
Natural bending, sitting and small jumps may change the pose and height;
do not resize the character to compensate or lock each frame's head to one coordinate.
No camera movement, panning, rotation, zoom, reframing, cuts or scene changes.

[ACTION AND MOTION QUALITY]
Perform only the selected action. Do not combine it with unrelated actions.
Animate in place: no unplanned whole-character horizontal travel or root drift.
The desktop application provides movement across the screen, not this video.
For walking, step in place while keeping the body centered; the fixed action
contract specifies facing direction. Do not enter or leave the frame.
Keep grounded feet at the virtual contact level unless the action explicitly
requires lifting, jumping or suspension. Do not draw that virtual ground.
Use smooth, physically coherent movement, with natural acceleration and deceleration.
Hair, sleeves and clothing may follow the body with subtle secondary motion only.
Keep anatomy, limb count, facial features, outfit details and lighting consistent.
Avoid unintended pauses, sudden snaps, jitter, flicker, morphing, rubbery stretching,
foot sliding during planted contact, blurred edges or excessive motion blur.

[LOOP OR RETURN TO NEUTRAL]
Obey the fixed action contract appended to this prompt.
For cyclic actions, start in the action and make the end flow naturally into the
start with matching pose, position, scale and motion direction/speed.
Do not append a neutral-pose transition to a continuous walk or suspended drag loop.
Do not manufacture a loop by reversing the clip or adding a repeated endpoint frame.
For one-shot actions, begin in the master neutral pose, perform the action, and
ease back to the same neutral pose and placement before the end.
Do not snap back, fade out, cut to the first frame or freeze for an unintended interval.

[BACKGROUND AND FILE OUTPUT]
Output one MP4 video with an opaque background.
Use an opaque, perfectly uniform solid #FF00FF magenta background (RGB 255, 0, 255)
in every frame, including all gaps between limbs.
Do not request or simulate transparency. Never draw a checkerboard.
Background removal will be performed separately after generation.
Use the master image for character identity only; replace any reference background,
including a checkerboard, with the specified solid magenta background.
Reserve the key color for the background only: no magenta or near-magenta colors
on the character, including hair, eyes, clothing, accessories and outlines.
If the master character uses these colors, request a revised master before generating;
do not silently recolor the character or change the fixed background color.
No background gradients, textures, patterns, noise or changing background colors.
No scenery, visible floor, ground plane, cast shadow, text, subtitles, logos,
watermarks, borders, glow, audio, music or sound effects.
Keep clean outlines with no magenta reflections, spill, fringe or colored halos.
Output one animation video, not a still image, GIF, sprite sheet, storyboard,
multi-view collage or a collection of separate shots.
If exact size, fps, duration or file format are unsupported, preserve 16:9, framing and
identity, and disclose actual output values outside the video. Never claim false
compliance or burn explanatory text into the frames.

[PROHIBITED DEFECTS]
No cropped body parts, duplicate characters, extra or missing limbs, malformed hands
or fingers, face changes, accessory disappearance, realistic adult body proportions,
unstable scale, inconsistent linework, frame-to-frame color shifts or ghost trails."""

@dataclass(frozen=True)
class Action:
    id: str
    label: str
    category: str
    seconds: float
    example: str
    contract: str


LOOP = ("Start directly in the action. Continue cyclic motion throughout. "
        "The last frame must flow into the first with continuous pose and velocity. "
        "No extra duplicate endpoint, hold, fade or reversed playback.")
ONCE = ("Start in the master neutral pose. Perform the action, then ease back to "
        "the exact same neutral pose before the end. No sudden reset.")
ACTIONS = (
    Action("idle", "待机", "idle", 3, "轻轻呼吸，偶尔眨眼，双脚站稳，保持温和微笑。", LOOP),
    Action("walk", "走路", "move", 2, "轻松原地踏步，左右脚交替，双臂交错摆动，完成两个完整步行周期。",
           "Face LEFT throughout, side view slightly toward the viewer. Feet step in place; "
           "one support foot stays on the virtual ground. No turn-in or stopping. " + LOOP),
    Action("wave", "挥手", "click", 3, "抬起一只手，开心挥手两次，缓慢放下。", ONCE),
    Action("happy", "开心", "click", 3, "露出开心的笑容，双手在胸前轻拍两次，放松恢复。", ONCE),
    Action("jump", "跳跃", "random", 2, "轻轻下蹲蓄力，向上小跳一次，落地后缓冲站稳。",
           "Keep the jump low enough to fit the canvas; return soles to y=330. " + ONCE),
    Action("sit", "坐下", "random", 4, "缓慢坐下，安静停留片刻，再起身回到站姿。", ONCE),
    Action("sleep", "打盹", "random", 4, "站着闭眼打盹，头轻轻点一下，醒来后恢复精神。", ONCE),
    Action("surprise", "惊讶", "click", 2, "睁大双眼，双手轻轻抬起，随后放松恢复微笑。", ONCE),
    Action("sad", "难过", "random", 3, "稍微低头，露出委屈表情，再抬头恢复温和微笑。", ONCE),
    Action("drag", "拖拽", "drag", 2, "表现被轻轻提起的姿态，双脚悬空轻晃，表情好奇。",
           "Stay centered. No travel across the canvas. Maintain a gently suspended pose. " + LOOP),
)


def action_by_id(action_id):
    return next((a for a in ACTIONS if a.id == action_id), None)


def build_prompt(appearance, action_id="portrait", description=None, seconds=None):
    appearance = str(appearance).strip()
    if not appearance or len(appearance) > 5000:
        raise ValueError("形象描述需为1至5000字。")
    if action_id == "portrait":
        return f"Create a desktop pet character master.\n\n[CUSTOM APPEARANCE]\n{appearance}\n\n{FIXED_IMAGE}"
    action = action_by_id(action_id)
    if action is None:
        raise ValueError("未知动作。")
    seconds = action.seconds if seconds is None else float(seconds)
    if not math.isfinite(seconds) or not 1 <= seconds <= 12 or abs(seconds * 24 - round(seconds * 24)) > .01:
        raise ValueError("时长应为1至12秒，且对应整数帧。")
    description = str(description if description is not None else action.example).strip()
    if not description or len(description) > 5000:
        raise ValueError("动作描述需为1至5000字。")
    return (
        f"Create ONE desktop pet animation. Duration: {seconds:g} seconds, "
        f"{round(seconds * 24)} frames at 24 fps.\n\n"
        f"[CUSTOM APPEARANCE]\n{appearance}\n\n[CUSTOM ACTION]\n{description}\n\n"
        f"{FIXED_VIDEO}\n\n[FIXED ACTION CONTRACT - NOT USER EDITABLE]\n{action.contract}"
    )
