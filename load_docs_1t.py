from openai import OpenAI
import chromadb
import os

# =====================================
# LM Studio
# =====================================

client = OpenAI(
    base_url="http://10.0.20.220:1234/v1",
    api_key="lm-studio"
)

# =====================================
# ChromaDB
# =====================================

rag_client = chromadb.PersistentClient(
    path="./chroma_db"
)

# usuń starą kolekcję
try:
    rag_client.delete_collection("baza-wiedzy")
    print("Usunięto starą kolekcję.")
except Exception:
    print("Kolekcja nie istniała.")

# utwórz nową
collection = rag_client.get_or_create_collection(
    name="baza-wiedzy"
)

print("Utworzono nową kolekcję.")

# =====================================
# Embedding
# =====================================

def get_embedding(text):
    response = client.embeddings.create(
        model="text-embedding-bge-m3",
        input=text
    )

    return response.data[0].embedding

# =====================================
# Dzielenie tekstu na fragmenty
# =====================================

def chunk_text(text, chunk_size=1000):

    chunks = []

    for i in range(0, len(text), chunk_size):
        chunks.append(
            text[i:i + chunk_size]
        )

    return chunks

# =====================================
# Indeksowanie katalogu
# =====================================

DOCUMENTS_DIR = "Documents"

counter = 0

for filename in os.listdir(DOCUMENTS_DIR):

    if not filename.endswith(".txt"):
        continue

    full_path = os.path.join(
        DOCUMENTS_DIR,
        filename
    )

    print(f"Przetwarzam: {filename}")

    with open(
        full_path,
        "r",
        encoding="utf-8"
    ) as f:

        text = f.read()

    chunks = chunk_text(text)

    for idx, chunk in enumerate(chunks):

        embedding = get_embedding(chunk)

        collection.add(
            ids=[
                f"{filename}_{idx}"
            ],
            documents=[
                chunk
            ],
            embeddings=[
                embedding
            ],
            metadatas=[
                {
                    "source": filename
                }
            ]
        )

        counter += 1

print()
print(f"Zapisano {counter} fragmentów.")
