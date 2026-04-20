import os
import json
import time
import datetime
import logging
import streamlit as st
from PIL import Image
from story_generator import generate_story
from image_generator import generate_all_images, generate_pdf
from config import OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="AI Storybook Generator", layout="wide")
st.title("AI Storybook Generator")
st.caption("Create a personalized illustrated storybook for your little one.")

# --- Sidebar: User Inputs ---
with st.sidebar:
    st.header("Create Your Story")

    keywords = st.text_input(
        "Keywords / Interests",
        placeholder="e.g. ice cream, dinosaurs, rainbows"
    )
    characters = st.text_input(
        "Characters",
        placeholder="e.g. a curious girl named Mia, a friendly dragon"
    )
    setting = st.text_input(
        "Setting",
        placeholder="e.g. magical forest, outer space, underwater kingdom"
    )
    story_type = st.selectbox(
        "Story Type",
        ["Adventure", "Bedtime", "Funny", "Learning"]
    )
    art_style = st.selectbox(
        "Art Style",
        ["Watercolor storybook illustration", "Cartoon illustration",
         "Pencil sketch illustration", "Pixel art illustration"]
    )

    generate_btn = st.button("Generate Story", type="primary", use_container_width=True)

# --- Main Area: Story Generation ---
if generate_btn:
    if not keywords or not characters or not setting:
        st.warning("Please fill in Keywords, Characters, and Setting before generating.")
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        story_dir = os.path.join(OUTPUT_DIR, f"story_{timestamp}")
        os.makedirs(story_dir, exist_ok=True)

        try:
            total_start = time.time()

            # Step 1: Generate story text and image prompts
            with st.spinner("Writing your story..."):
                story = generate_story(
                    keywords=keywords,
                    characters=characters,
                    setting=setting,
                    story_type=story_type.lower(),
                    art_style=art_style.lower()
                )

            with open(os.path.join(story_dir, "story.json"), "w") as f:
                json.dump(story, f, indent=2)

            st.success(f"Story written: **{story['title']}**")

            # Step 2: Generate all images with sliding window
            with st.spinner("Drawing all 5 scenes (this takes ~1-2 minutes)..."):
                image_paths = generate_all_images(story, story_dir)

            # Step 3: Display the storybook
            st.divider()
            st.header(story["title"])

            scenes = story["scenes"]
            for row_start in range(0, len(scenes), 2):
                cols = st.columns(2)
                for col_idx, scene_idx in enumerate(range(row_start, min(row_start + 2, len(scenes)))):
                    with cols[col_idx]:
                        img = Image.open(image_paths[scene_idx])
                        st.image(img, width=800)
                        st.caption(f"Scene {scenes[scene_idx]['scene_number']}: {scenes[scene_idx]['text']}")
            st.divider()

            total_elapsed = time.time() - total_start
            logger.info(f"Total generation time: {total_elapsed:.1f}s")
            st.info(f"Total generation time: {total_elapsed:.1f}s")

            # Store in session state so PDF button can access without re-running generation
            st.session_state["image_paths"] = image_paths
            st.session_state["story_title"] = story["title"]
            st.session_state["story_dir"] = story_dir

        except Exception as e:
            st.error(f"Something went wrong: {e}")

# --- PDF Download (only shown after a story has been generated) ---
if "image_paths" in st.session_state:
    if st.button("Download PDF", type="secondary"):
        with st.spinner("Generating PDF..."):
            pdf_bytes = generate_pdf(
                st.session_state["image_paths"],
                st.session_state["story_title"],
                st.session_state["story_dir"]
            )
        st.download_button(
            label="Click here to download",
            data=pdf_bytes,
            file_name=f"{st.session_state['story_title'].replace(' ', '_')}.pdf",
            mime="application/pdf"
        )
