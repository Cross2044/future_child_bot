import os
import requests
from flask import Flask, request, jsonify, send_file
from io import BytesIO

app = Flask(__name__)

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
# Здесь укажи модель, например FaceFusion Space
MODEL_URL = "https://api-inference.huggingface.co/models/leonelhs/FaceFusion"

headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}

@app.route("/generate", methods=["POST"])
def generate():
    if "mother" not in request.files or "father" not in request.files:
        return jsonify({"error": "Нужно загрузить два фото: mother и father"}), 400

    mother = request.files["mother"].read()
    father = request.files["father"].read()

    # Отправляем фото в Hugging Face API
    resp = requests.post(
        MODEL_URL,
        headers=headers,
        files={"image1": mother, "image2": father}
    )

    if resp.status_code != 200:
        return jsonify({"error": resp.text}), resp.status_code

    # Возвращаем картинку напрямую
    return send_file(BytesIO(resp.content), mimetype="image/png")

@app.route("/")
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
