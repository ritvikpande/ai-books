import json
import logging
from config import get_client, TEXT_MODEL

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
      Style: [ART_STYLE]. No text or words in the image."
    }
  ]
}

Rules:
- Story must have a clear beginning, middle, and end across 5 scenes
- Keep language simple — short sentences, common words
- In EVERY image_prompt, always describe the characters the same way (same colors, same clothing) so they look consistent across all images
- The ART_STYLE placeholder will be replaced with the user's chosen style
- Each image_prompt should be 60-100 words
- No scary, violent, or inappropriate content"""


def generate_story(keywords: str, characters: str, setting: str, story_type: str, art_style: str) -> dict:
    """
    Generate a 5-scene children's story with image prompts.

    Returns a dict with keys: title, scenes (list of 5 scene dicts)
    Each scene has: scene_number, text, image_prompt
    """
    client = get_client()

    user_prompt = f"""Create a toddler's picture book with these inputs:
- Keywords/interests: {keywords}
- Characters: {characters}
- Setting: {setting}
- Story type: {story_type}
- Art style: {art_style}

Remember to replace ART_STYLE in every image_prompt with: {art_style}"""

    logger.info("Generating story with Gemini...")

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=user_prompt,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.9,
        }
    )

    raw = response.text.strip()
    logger.info("Story received, parsing JSON...")

    # Strip markdown code blocks if Gemini wraps the JSON anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    story = json.loads(raw)

    # Basic validation
    assert "title" in story, "Missing 'title' in response"
    assert "scenes" in story, "Missing 'scenes' in response"
    assert len(story["scenes"]) == 5, f"Expected 5 scenes, got {len(story['scenes'])}"
    for scene in story["scenes"]:
        assert "scene_number" in scene
        assert "text" in scene
        assert "image_prompt" in scene

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
