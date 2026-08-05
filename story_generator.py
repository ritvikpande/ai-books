import json
import time
import logging
from config import get_client, TEXT_MODEL
from prompt_assembly import assemble_mixed_media_prompt, compose_character_description

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a toddler's picture book author and illustrator.
Given user inputs, generate a 5-scene story for toddlers aged 2-5.

Return ONLY valid JSON — no markdown, no code blocks, no extra text.

Format:
{
  "title": "Story title",
  "scenes": [
    {
      "scene_number": 1,
      "text": "1-2 short sentences for this scene. Simple words, warm and fun tone.",
      "image_prompt": "Children's storybook illustration: [describe the scene visually]. 
      Characters: [describe each character with consistent physical details — colors, clothing, size]. 
      Setting: [describe background, time of day, colors]. Mood: [warm/playful/cozy/etc].
      Style: [ART_STYLE]. No text or words in the image, and no border, frame, or outline around the characters or the image."
    }
  ]
}

Rules:
- Story must have a clear beginning, middle, and end across 5 scenes
- Keep language simple — short sentences, common words
- In EVERY image_prompt, always describe the characters the same way (same colors, same clothing) so they look consistent across all images
- The ART_STYLE placeholder will be replaced with the user's chosen style
- Each image_prompt should be 60-100 words
- Never draw a border, frame, outline, or cut-out edge around the characters or the image — characters blend naturally into the scene
- No scary, violent, or inappropriate content"""


MIXED_MEDIA_SYSTEM_PROMPT = """You are a toddler's picture book author.
Given user inputs, generate a 5-scene story for toddlers aged 2-5.

The book is MIXED MEDIA: some characters are real photographed people
("photorealistic characters") and the rest of the world is flat 2D cartoon.
Each character's fixed appearance is already locked by a reference image and a
user-provided description, so you must NOT re-describe how they look. For each
scene you only write WHAT each character is doing.

Return ONLY valid JSON — no markdown, no code blocks, no extra text.

Format:
{
  "title": "Story title",
  "scenes": [
    {
      "scene_number": 1,
      "text": "1-2 short sentences for this scene. Simple words, warm and fun tone.",
      "photoreal_action": "what the photorealistic character(s) are DOING this scene — pose, action, expression, interaction. Refer to them BY NAME. Phrase it so it reads naturally after 'a photograph of ...', e.g. 'Dad kneeling to tie his shoe while Lily watches'. Do NOT mention their hair, skin, clothing, or any art style.",
      "cartoon_elements": "what the cartoon character(s) are doing, by name. Empty string if no cartoon characters appear in this scene. Do NOT re-describe their fixed appearance.",
      "background": "the background/setting for this scene: place, objects, time of day, plus any incidental cartoon children or animals"
    }
  ]
}

Rules:
- Story must have a clear beginning, middle, and end across 5 scenes
- Keep language simple — short sentences, common words
- Refer to every character BY NAME; their appearance is fixed by the reference images, so describe only their actions and the scene
- Do not include art style words (like "watercolor" or "vector") anywhere in photoreal_action — the photorealistic characters must read as a real photograph
- photoreal_action and background must never be empty
- No scary, violent, or inappropriate content"""


CLASSIC_SCENE_KEYS = ("scene_number", "text", "image_prompt")
MIXED_SCENE_KEYS = ("scene_number", "text", "photoreal_action", "cartoon_elements", "background")


def _describe_characters(chars: list) -> list:
    """Composed, non-empty description line per character (for the LLM prompt)."""
    return [d for d in (compose_character_description(c) for c in (chars or [])) if d]


def _bullets(lines: list) -> str:
    """Indented bullet list for the user prompt, or a '(none)' placeholder."""
    return "\n".join(f"  - {line}" for line in lines) if lines else "  - (none)"


def _validate_story(story: dict, mixed_media: bool = False) -> None:
    """Validate the parsed LLM response structure. Raises AssertionError on problems."""
    assert "title" in story, "Missing 'title' in response"
    assert "scenes" in story, "Missing 'scenes' in response"
    assert len(story["scenes"]) == 5, f"Expected 5 scenes, got {len(story['scenes'])}"
    required = MIXED_SCENE_KEYS if mixed_media else CLASSIC_SCENE_KEYS
    for scene in story["scenes"]:
        for key in required:
            assert key in scene, f"Scene missing '{key}'"
        if mixed_media:
            for field in ("photoreal_action", "background"):
                assert isinstance(scene[field], str) and scene[field].strip(), \
                    f"{field} must be a non-empty string"


def generate_story(keywords: str, characters: str, setting: str, story_type: str,
                   art_style: str, mixed_media: bool = False,
                   photoreal_characters: list = None, cartoon_characters: list = None) -> dict:
    """
    Generate a 5-scene children's story with image prompts.

    Classic mode: the LLM writes a complete image_prompt per scene.
    Mixed-media mode: photoreal_characters / cartoon_characters are lists of
    structured character objects. The LLM writes action-only visual fields
    (photoreal_action, cartoon_elements, background) referring to characters by
    name; the boilerplate template assembles the final image_prompt per scene,
    including the instruction to follow the attached reference images.

    Returns a dict with keys: title, scenes (list of 5 scene dicts).
    Every scene has scene_number, text, image_prompt after this function returns.
    """
    client = get_client()

    if mixed_media:
        system_prompt = MIXED_MEDIA_SYSTEM_PROMPT
        user_prompt = f"""Create a toddler's picture book with these inputs:
- Keywords/interests: {keywords}
- Photorealistic characters (fixed appearance — refer to them by name):
{_bullets(_describe_characters(photoreal_characters))}
- Cartoon characters:
{_bullets(_describe_characters(cartoon_characters))}
- Setting: {setting}
- Story type: {story_type}"""
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = f"""Create a toddler's picture book with these inputs:
- Keywords/interests: {keywords}
- Characters: {characters}
- Setting: {setting}
- Story type: {story_type}
- Art style: {art_style}

Remember to replace ART_STYLE in every image_prompt with: {art_style}"""

    logger.info(f"Generating story with Gemini... (mixed_media={mixed_media})")
    start = time.time()

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "temperature": 0.9,
        }
    )

    elapsed = time.time() - start
    logger.info(f"Story response received in {elapsed:.1f}s")

    raw = response.text.strip()
    logger.info("Parsing JSON...")

    # Strip markdown code blocks if Gemini wraps the JSON anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    story = json.loads(raw)
    _validate_story(story, mixed_media=mixed_media)

    if mixed_media:
        for scene in story["scenes"]:
            scene["image_prompt"] = assemble_mixed_media_prompt(
                scene, photoreal_characters or [], cartoon_characters or [], art_style
            )

    logger.info(f"Story generated: '{story['title']}'")
    return story


if __name__ == "__main__":
    # Quick test
    story = generate_story(
        keywords="ice cream, rainbows, butterflies",
        characters="a curious little girl named Mia, a friendly talking cat named Biscuit",
        setting="a magical candy forest",
        story_type="adventure",
        art_style="watercolor storybook illustration"
    )

    print(f"\nTitle: {story['title']}\n")
    for scene in story["scenes"]:
        print(f"--- Scene {scene['scene_number']} ---")
        print(f"Text: {scene['text']}")
        print(f"Image prompt: {scene['image_prompt']}\n")
