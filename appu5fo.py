from fastapi import FastAPI
from fastapi import Request
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile, File

from pypdf import PdfReader
from docx import Document

from email import policy
from email.parser import BytesParser

import io

from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse
)

from starlette.middleware.sessions import (
    SessionMiddleware
)

from openai import OpenAI

import bcrypt
import chromadb
import json
import os
import time

from datetime import datetime, timedelta

import fitz
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

failed_logins = {}
uploaded_documents = {}

# ====================================================
# FastAPI
# ====================================================

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_TAJNY_KLUCZ_123456"
)

# ====================================================
# LM Studio
# ====================================================

client = OpenAI(
    base_url="http://10.0.20.220:1234/v1",
    api_key="lm-studio"
)

# ====================================================
# ChromaDB
# ====================================================

rag_client = chromadb.PersistentClient(
    path="./chroma_db"
)

collection = rag_client.get_or_create_collection(
    name="baza-wiedzy"
)

# ====================================================
# Katalog historii
# ====================================================

os.makedirs("history", exist_ok=True)

# ====================================================
# Użytkownicy
# ====================================================

USERS_FILE = "users.json"

if not os.path.exists(USERS_FILE):

    default_users = {
        "admin": bcrypt.hashpw(
            b"admin123",
            bcrypt.gensalt()
        ).decode("utf-8")
    }

    with open(
        USERS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            default_users,
            f,
            ensure_ascii=False,
            indent=2
        )

with open(
    USERS_FILE,
    "r",
    encoding="utf-8"
) as f:

    USERS = json.load(f)

# ====================================================
# Embedding przez BGE-M3
# ====================================================

def get_embedding(text):

    response = client.embeddings.create(
        model="text-embedding-bge-m3",
        input=text
    )

    return response.data[0].embedding

# ====================================================
# ChromaDB Search
# ====================================================

def search_context(question, k=3):

    embedding = get_embedding(question)

    results = collection.query(
        query_embeddings=[embedding],
        n_results=k
    )

    if not results["documents"]:
        return ""

    distance = results["distances"][0][0]

    print("DISTANCE:", distance)

    if distance > 0.8:
        return ""

    return "\n\n".join(
        results["documents"][0]
    )

# ====================================================
# Historia użytkownika
# ====================================================

def history_file(username):

    return f"history/{username}.json"

def load_conversation(username):

    file = history_file(username)

    if os.path.exists(file):

        with open(
            file,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    return []

def save_conversation(
    username,
    conversation
):

    with open(
        history_file(username),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            conversation,
            f,
            ensure_ascii=False,
            indent=2
        )

# ====================================================
# Autoryzacja
# ====================================================

def current_user(request: Request):

    username = request.session.get("user")

    if not username:

        raise HTTPException(
            status_code=401,
            detail="Zaloguj się"
        )

    return username

# ====================================================
# Login HTML
# ====================================================

login_html = """
<h3>MW - Logowanie do Agenta AI</h3>

<form method="post" action="/login">

Login:<br>
<input
    type="text"
    name="username"
    required
>

<br><br>

Hasło:<br>
<input
    type="password"
    name="password"
    required
>

<br><br>

<button type="submit">
Zaloguj
</button>

</form>
"""

# ====================================================
# Chat HTML
# ====================================================

chat_html = """
<h3>MW - Agent AI korzystający z bazy wiedzy (RAG)</h3>

<button onclick="logout()">
Wyloguj
</button>

<hr>

<textarea
id="q"
rows="3"
placeholder="Zadaj pytanie"
style="width:97%;padding:8px;"></textarea>

<br><br>

<button id="sendBtn"
onclick="send()">
Wyślij
</button>

<button onclick="resetChat()">
Reset
</button>

<label
    for="fileInput"
    style="
        padding:8px;
        border:1px solid #aaa;
        cursor:pointer;
    "
>
📎 Dodaj plik
</label>

<p>UWAGA: Można wczytać plik: .txt .pdf .docx .elm; </p>

<input
    type="file"
    id="fileInput"
    style="display:none"
    onchange="uploadFile()"
>

<hr>

<div id="chat"></div>

<script>

async function loadHistory(){

 let res=
 await fetch("/history");

 let data=
 await res.json();

 let chat=
 document.getElementById("chat");

 chat.innerHTML="";

 data.forEach(msg=>{

   if(msg.role==="user"){

      chat.innerHTML +=
      "<p><b>Ty:</b> "
      + msg.content +
      "</p>";

   }else{

      chat.innerHTML +=
      "<p><b>AI:</b> "
      + msg.content +
      "</p>";

   }

 });

}

let sending=false;

async function send(){

 if(sending) return;

 let q=
 document.getElementById("q").value;

 if(!q.trim())
    return;

 sending=true;

 let btn=
 document.getElementById("sendBtn");

 btn.disabled=true;

 try{

   let res=
   await fetch(
   "/chat?q="
   + encodeURIComponent(q)
   );

   let text=
   await res.text();

   let chat=
   document.getElementById("chat");

   chat.innerHTML +=
     "<p><b>Ty:</b> "
     + q +
     "</p>";

   chat.innerHTML +=
     "<p><b>AI:</b> "
     + text +
     "</p>";

   document.getElementById(
     "q"
   ).value="";

 }finally{

   sending=false;
   btn.disabled=false;

 }

}

async function resetChat(){

 await fetch("/reset");

 document.getElementById(
   "chat"
 ).innerHTML="";

}

async function uploadFile() {

    const file =
        document.getElementById(
            "fileInput"
        ).files[0];

    if (!file)
        return;

    const formData =
        new FormData();

    formData.append(
        "file",
        file
    );

    await fetch(
        "/upload",
        {
            method: "POST",
            body: formData
        }
    );

    alert(
        "Plik został załadowany do bieżącej rozmowy"
    );
}

async function logout(){

 await fetch("/logout");

 location.href="/";

}

window.onload=loadHistory;

</script>
"""

# ====================================================
# Strona główna
# ====================================================

@app.get("/")
def home(request: Request):

    if request.session.get("user"):
        return HTMLResponse(chat_html)

    return HTMLResponse(login_html)

# ====================================================
# Login
# ====================================================

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):

    user_key = username.lower()

    if user_key not in failed_logins:

        failed_logins[user_key] = {
            "count": 0,
            "blocked_until": None
        }

    login_data = failed_logins[user_key]

    # sprawdzenie blokady

    if login_data["blocked_until"]:

        if datetime.now() < login_data["blocked_until"]:

            minutes_left = int(
                (login_data["blocked_until"] - datetime.now()).total_seconds() / 60
            ) + 1

            return HTMLResponse(
                f"""
                <h3 style="color:red">
                Konto zablokowane.
                Spróbuj ponownie za około {minutes_left} minut.
                </h3>

                {login_html}
                """,
                status_code=429
            )

        # blokada wygasła

        login_data["count"] = 0
        login_data["blocked_until"] = None

    # nie istnieje użytkownik

    if username not in USERS:

        login_data["count"] += 1

    # błędne hasło

    elif not bcrypt.checkpw(
        password.encode("utf-8"),
        USERS[username].encode("utf-8")
    ):

        login_data["count"] += 1

    else:

        # poprawne logowanie

        login_data["count"] = 0
        login_data["blocked_until"] = None

        request.session["user"] = username

        return RedirectResponse(
            url="/",
            status_code=302
        )

    # blokada po 5 błędnych próbach

    if login_data["count"] >= 5:

        login_data["blocked_until"] = (
            datetime.now() +
            timedelta(minutes=15)
        )

        return HTMLResponse(
            f"""
            <h3 style="color:red">
            Za dużo błędnych prób logowania.
            Konto zablokowane na 15 minut.
            </h3>

            {login_html}
            """,
            status_code=429
        )

    return HTMLResponse(
        f"""
        <h3 style="color:red">
        Błędny login lub hasło.
        Próba {login_data['count']}/5.
        </h3>

        {login_html}
        """,
        status_code=401
    )

# ====================================================
# Logout
# ====================================================

@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return "OK"

# ====================================================
# Historia rozmowy
# ====================================================

@app.get("/history")
def history(request: Request):

    username = current_user(request)

    conversation = load_conversation(
        username
    )

    return JSONResponse(
        conversation
    )

# ====================================================
# Ładowanie Endpointa
# ====================================================

@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...)
):

    username = current_user(request)

    filename = file.filename.lower()

    content = await file.read()

    text = ""

    # TXT

    if filename.endswith(".txt"):

        text = content.decode(
            "utf-8",
            errors="ignore"
        )

    # PDF

    elif filename.endswith(".pdf"):

        pdf = PdfReader(
            io.BytesIO(content)
        )

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        # OCR jeśli nie znaleziono tekstu

        if not text.strip():

            print("Uruchamiam OCR PDF")

            pdf_doc = fitz.open(
                stream=content,
                filetype="pdf"
            )

            for page_num in range(
                    len(pdf_doc)
            ):

                page = pdf_doc[page_num]

                pix = page.get_pixmap(
                    dpi=300
                )

                img = Image.frombytes(
                    "RGB",
                    [pix.width, pix.height],
                    pix.samples
                )

                text += pytesseract.image_to_string(
                    img,
                    lang="pol"
                )

    # DOCX

    elif filename.endswith(".docx"):

        doc = Document(
            io.BytesIO(content)
        )

        text = "\n".join(
            p.text
            for p in doc.paragraphs
        )

    # EML

    elif filename.endswith(".eml"):

        msg = BytesParser(
            policy=policy.default
        ).parsebytes(content)

        if msg["Subject"]:

            text += (
                "Temat: "
                + str(msg["Subject"])
                + "\n\n"
            )

        if msg.is_multipart():

            for part in msg.walk():

                if (
                    part.get_content_type()
                    == "text/plain"
                ):

                    text += (
                        part.get_content()
                        + "\n"
                    )

        else:

            text += msg.get_content()

    else:

        return JSONResponse(
            {
                "status": "error",
                "message":
                "Obsługiwane są tylko: TXT, PDF, DOCX, EML"
            },
            status_code=400
        )

    uploaded_documents[username] = {
        "filename": file.filename,
        "content": text
    }

    print(
        f"Załadowano plik: {file.filename}"
    )

    print(
        f"Długość tekstu: {len(text)}"
    )

    return {
        "status": "ok"
    }

# ====================================================
# Chat + RAG
# ====================================================

@app.get("/chat")
def chat(
    request: Request,
    q: str
):

    username = current_user(request)

    file_data = uploaded_documents.get(
        username
    )

    if file_data:

        filename = file_data["filename"]

        file_context = file_data["content"]

    else:

        filename = ""
        file_context = ""

    conversation = load_conversation(
        username
    )

    context = search_context(q)

    messages = [

        {
            "role": "system",
            "content": """
Jesteś pomocnym asystentem, korzystającym z bazy wiedzy.

Jeżeli w sekcji KONTEKST znajdują się informacje potrzebne do odpowiedzi,
wykorzystaj informacje z KONTEKSTU.

Sekcja ZAŁADOWANY PLIK może zawierać:
- treść dokumentu,
- pytania użytkownika,
- dodatkowe informacje do analizy.

Wykorzystuj informacje z KONTEKSTU, ZAŁADOWANEGO PLIKU lub z obu źródeł,
w zależności od treści pytania.

Jeżeli odpowiedź znajduje się w KONTEKŚCIE lub ZAŁADOWANYM PLIKU,
udziel odpowiedzi na podstawie dostępnych informacji.

Jeżeli odpowiedzi nie ma ani w KONTEKŚCIE ani w ZAŁADOWANYM PLIKU,
odpowiedz korzystając z własnej wiedzy.

Nie informuj użytkownika, skąd pochodzi odpowiedź.

Nie twórz fikcyjnych procedur, regulacji, instrukcji ani dokumentów.

Jeżeli nie istnieją informacje pozwalające odpowiedzieć,
powiedz o tym wprost.

Odpowiadaj naturalnie po polsku.
"""
        }

    ]

    messages.extend(conversation[-10:])

    parts = []

    if context:
        parts.append(
            f"""KONTEKST:

    {context}"""
        )

    if file_context:
        parts.append(
            f"""ZAŁADOWANY PLIK:

    Nazwa pliku: {filename}

    Treść:

    {file_context}"""
        )

    parts.append(
        f"""PYTANIE:

    {q}"""
    )

    prompt = "\n\n".join(parts)

    print("PROMPT:")
    print(prompt)

    messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    print(
        "PLIK:",
        len(file_context)
    )

    response = client.chat.completions.create(
        model="bielik-11b-v3.0-instruct",
        messages=messages,
        temperature=0.3
    )

    print("MESSAGE:")
    print(response.choices[0].message)

    answer = response.choices[0].message.content

    print("ANSWER:")
    print(repr(answer))

    if not answer:
        answer = "Model nie zwrócił odpowiedzi."

    conversation.append(
        {
            "role": "user",
            "content": q
        }
    )

    conversation.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    save_conversation(
        username,
        conversation
    )

    return PlainTextResponse(
        str(answer)
    )

# ====================================================
# Reset rozmowy
# ====================================================

@app.get("/reset")
def reset(
    request: Request
):

    username = current_user(
        request
    )

    file = history_file(
        username
    )

    if os.path.exists(file):

        timestamp = int(
            time.time()
        )

        archive = (
            f"history/"
            f"{username}_"
            f"{timestamp}.json"
        )

        os.rename(
            file,
            archive
        )

    save_conversation(
        username,
        []
    )

    if username in uploaded_documents:
        del uploaded_documents[username]

    return "OK"