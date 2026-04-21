import os
import json
import time
import datetime
import logging
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory

from story_generator import generate_story
from image_generator import generate_all_images, generate_pdf
from config import OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    keywords = data.get('keywords')
    characters = data.get('characters')
    setting = data.get('setting')
    story_type = data.get('story_type', 'Adventure').lower()
    art_style = data.get('art_style', 'Watercolor storybook illustration').lower()

    if not keywords or not characters or not setting:
        return jsonify({"error": "Please fill in Keywords, Characters, and Setting."}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    story_dir = os.path.join(OUTPUT_DIR, f"story_{timestamp}")
    os.makedirs(story_dir, exist_ok=True)

    try:
        total_start = time.time()

        # Generate story
        story = generate_story(
            keywords=keywords,
            characters=characters,
            setting=setting,
            story_type=story_type,
            art_style=art_style
        )

        with open(os.path.join(story_dir, "story.json"), "w") as f:
            json.dump(story, f, indent=2)

        # Generate all images
        image_paths = generate_all_images(story, story_dir)

        total_elapsed = time.time() - total_start
        logger.info(f"Total generation time: {total_elapsed:.1f}s")

        return jsonify({
            "message": "Success",
            "story": story,
            "image_paths": image_paths, 
            "story_title": story["title"],
            "story_dir": story_dir,
            "time_elapsed": round(total_elapsed, 1)
        })

    except Exception as e:
        logger.error(f"Generation error: {e}")
        return jsonify({"error": str(e)}), 500

# Endpoint to serve generated images to the frontend
@app.route('/images', methods=['GET'])
def get_image():
    filepath = request.args.get('path')
    if not filepath or not os.path.exists(filepath):
        return "Image not found", 404
    
    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    return send_from_directory(directory, filename)

# Endpoint to generate and download the PDF
@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    data = request.json
    try:
        pdf_bytes = generate_pdf(
            data['image_paths'],
            data['story_title'],
            data['story_dir']
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{data['story_title'].replace(' ', '_')}.pdf"
        )
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)