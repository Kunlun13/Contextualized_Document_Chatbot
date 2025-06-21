from flask import Flask, request, jsonify
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import requests
from flask_cors import CORS

app = Flask(__name__, , static_folder="../frontend/dist", static_url_path="/")
CORS(app)

# ==========================
# Configuration
# ==========================
PDF_PATH = "Final UG Ordinance 05 Sept 2024 (1).pdf"  # already available in your backend
API_KEY = "AIzaSyCjY69_DSYBTdAgRSgFKV7tu49s9331NJQ"
MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_SIZE = 500


# ==========================
# Step 1: Preprocessing
# ==========================
def extract_text_from_pdf(pdf_path):
    pdf_document = fitz.open(pdf_path)
    text = ""
    for page_num in range(pdf_document.page_count):
        page = pdf_document.load_page(page_num)
        text += page.get_text("text")
    return text

def split_text_into_chunks(text, chunk_size=500):
    paragraphs = text.split("\n")
    chunks = []
    chunk = ""
    for paragraph in paragraphs:
        if len(chunk) + len(paragraph) > chunk_size:
            chunks.append(chunk.strip())
            chunk = paragraph
        else:
            chunk += " " + paragraph
    if chunk:
        chunks.append(chunk.strip())
    return chunks

def generate_embeddings(chunks, model_name="all-MiniLM-L6-v2"):
    model = SentenceTransformer(model_name)
    embeddings = model.encode(chunks)
    return embeddings


# ==========================
# Step 2: Query Handling
# ==========================
def get_relevant_chunks(query, chunks, chunk_embeddings, top_k=3):
    model = SentenceTransformer(MODEL_NAME)
    query_embedding = model.encode([query])
    similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]
    top_indices = similarities.argsort()[-top_k:][::-1]
    return [(chunks[i], similarities[i]) for i in top_indices]

def generate_answer_with_gemini(query, document_chunks, chunk_embeddings, api_key):
    relevant_chunks = get_relevant_chunks(query, document_chunks, chunk_embeddings)
    context = "\n\n".join([chunk[0] for chunk in relevant_chunks])
    
    if not context.strip():
        return "No relevant content found in the document.", ""
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro-001:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"Answer the following question using the provided context.\n\nContext:\n{context}\n\nQuestion:\n{query}"
                    }
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        try:
            answer = response.json()['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            answer = "Error: Unexpected response structure from Gemini API."
    else:
        answer = f"Error generating answer. Status Code: {response.status_code}, Message: {response.text}"

    references = "\n\n".join([f"📌 Reference {i+1}:\n{chunk[0]}" for i, chunk in enumerate(relevant_chunks)])
    return answer, references


# ==========================
# Load Document on Startup
# ==========================
print("📥 Loading and preparing document...")
document_text = extract_text_from_pdf(PDF_PATH)
document_chunks = split_text_into_chunks(document_text, CHUNK_SIZE)
chunk_embeddings = generate_embeddings(document_chunks, MODEL_NAME)
print("✅ Document ready for question answering.")


# ==========================
# Flask Route
# ==========================
@app.route("/ask", methods=["POST"])
def ask_question():
    data = request.get_json()
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query not provided"}), 400

    answer, references = generate_answer_with_gemini(query, document_chunks, chunk_embeddings, API_KEY)
    return jsonify({
        "query": query,
        "answer": answer,
        "references": references
    })


# ==========================
# Run the Flask App
# ==========================
if __name__ == "__main__":
    app.run(debug=True)
