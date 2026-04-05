from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import os
import shutil
import time
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
import argparse
import json
import sqlite3
from dotenv import load_dotenv
from google import genai
import fitz  # PyMuPDF
from langchain_core.documents import Document
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal



# Set API key for LangChain Google Generative AI integration
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY not found. Add it in .env as GOOGLE_API_KEY=...")

os.environ["GOOGLE_API_KEY"] = api_key
client = genai.Client(api_key=api_key)

WEB_LOGIN_USERNAME = os.getenv("BOT_LOGIN_USERNAME", "admin")
WEB_LOGIN_PASSWORD = os.getenv("BOT_LOGIN_PASSWORD", "admin123")
SESSION_COOKIE_NAME = "university_bot_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8
active_web_sessions: dict[str, dict] = {}

# Initialize embeddings
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

VECTOR_DB_DIR = BASE_DIR / "chroma_db"


def create_vector_store(persist_dir: Path) -> Chroma:
    return Chroma(
        collection_name="help_desk",
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )


# Create / load Chroma vector store. If an older incompatible DB exists, back it up and recreate.
try:
    vector_store = create_vector_store(VECTOR_DB_DIR)
except Exception as exc:
    if VECTOR_DB_DIR.exists():
        backup_dir = BASE_DIR / f"chroma_db_incompatible_backup_{int(time.time())}"
        shutil.move(str(VECTOR_DB_DIR), str(backup_dir))
        print(f"Existing Chroma DB is incompatible and was backed up to: {backup_dir}")
    print(f"Recreating Chroma DB due to startup error: {exc}")
    vector_store = create_vector_store(VECTOR_DB_DIR)



def read_pdf_page_by_page(pdf_path):
    data = []
    try:
        with fitz.open(pdf_path) as doc:
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                text = page.get_text()
                if text.strip() != "":
                    data.append({
                        "text": text,
                        "page": page_num + 1,
                        "path": pdf_path
                    })
        return data
    except:
        return []

def add_document_to_vdb(pdf_path, vector_store):
    data = []
    langchain_docs = []

    try:
        if os.path.isdir(pdf_path):
            for filename in os.listdir(pdf_path):
                if filename.endswith(".pdf"):
                    full_path = os.path.join(pdf_path, filename)
                    data.extend(read_pdf_page_by_page(full_path))
        else:
            data.extend(read_pdf_page_by_page(pdf_path))
    except:
        return vector_store, []

    if len(data) > 0:
        file_id = 0

        for doc in data:
            file_name = os.path.basename(doc["path"])
            langchain_docs.append(
                Document(
                    page_content=doc["text"],
                    metadata={
                        "page": doc["page"],
                        "file_name": file_name
                    },
                    id=f"{file_name}_{file_id}"
                )
            )
            file_id += 1

        try:
            vector_store.add_documents(documents=langchain_docs)
        except Exception as exc:
            print(f"Skipping vector DB load for '{pdf_path}': {exc}")
            return vector_store, []

    print("Data added successfully")
    return vector_store, langchain_docs

all_docs = []
pdf_files = [
    "Academics.pdf",
    "Cafeteria Menu & Rules.pdf",
    "Course Catalogue.pdf",
    "Department Syllabus.pdf",
    "Emergency Contacts.pdf",
    "Exam Rules.pdf",
    "Hostel Rules..pdf",
    "Library Handbook.pdf",
    "Scholarship.pdf",
    "Sports & Extracurricular.pdf",
    "Transportation Guides fares.pdf",
]
pdf_files = [str(BASE_DIR / file_name) for file_name in pdf_files]

existing_doc_count = 0
try:
    existing_doc_count = vector_store._collection.count()
except Exception:
    existing_doc_count = 0

if existing_doc_count == 0:
    for pdf in pdf_files:
        if not os.path.exists(pdf):
            print(f"Skipping missing PDF: {pdf}")
            continue
        _, docs = add_document_to_vdb(pdf, vector_store)
        all_docs.extend(docs)
else:
    print(f"Vector store already has {existing_doc_count} records. Skipping PDF ingestion.")

def setup_database():
    conn = None
    try:
        # --- 1. Connect to the database ---
        conn = sqlite3.connect('university.db')
        cursor = conn.cursor()

        # --- 2. Create and Populate Tables ---

        # -- Table 1: faculty --
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS faculty (
                faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            );
        ''')

        faculty_data = [
            ('Dr. Alan Turing', 'alan.turing@university.edu'),
            ('Dr. Marie Curie', 'marie.curie@university.edu'),
            ('Dr. Evelyn Reed', 'evelyn.reed@university.edu')
        ]

        cursor.executemany(
            'INSERT OR IGNORE INTO faculty (name, email) VALUES (?, ?)',
            faculty_data
        )

        # -- Table 2: departments --
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS departments (
                department_id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_name TEXT NOT NULL UNIQUE,
                head_id INTEGER,
                FOREIGN KEY (head_id) REFERENCES faculty(faculty_id)
            );
        ''')

        departments_data = [
            ('Computer Science', 1),
            ('Physics', 2),
            ('History', 3)
        ]

        cursor.executemany(
            'INSERT OR IGNORE INTO departments (department_name, head_id) VALUES (?, ?)',
            departments_data
        )

        # -- Table 3: courses --
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS courses (
                course_id TEXT PRIMARY KEY,
                course_name TEXT NOT NULL,
                department_name TEXT,
                credits INTEGER,
                FOREIGN KEY (department_name) REFERENCES departments(department_name)
            );
        ''')

        courses_data = [
            ('CS101', 'Introduction to Python', 'Computer Science', 3),
            ('PHY201', 'Classical Mechanics', 'Physics', 4),
            ('HIS305', 'Modern European History', 'History', 3),
            ('CS303', 'Data Structures and Algorithms', 'Computer Science', 4)
        ]

        cursor.executemany(
            'INSERT OR IGNORE INTO courses VALUES (?, ?, ?, ?)',
            courses_data
        )

        # -- Table 4: students --
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                major TEXT,
                enrollment_year INTEGER,
                FOREIGN KEY (major) REFERENCES departments(department_name)
            );
        ''')

        students_data = [
            ('Alice Johnson', 'Computer Science', 2023),
            ('Bob Smith', 'Physics', 2022),
            ('Charlie Brown', 'History', 2024)
        ]

        cursor.executemany(
            'INSERT OR IGNORE INTO students (name, major, enrollment_year) VALUES (?, ?, ?)',
            students_data
        )

        # --- 3. Commit the transaction ---
        conn.commit()
        print("Database 'university.db' with 4 tables is ready. 🗃️✨")

    except sqlite3.Error as e:
        print(f"A database error occurred: {e}")
    finally:
        if conn:
            conn.close()

def _extract_json_from_response(raw_text: str, default: dict) -> dict:
    cleaned = (raw_text or "").strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return default.copy()


def _extract_fields_with_llm(prompt: str, default: dict) -> dict:
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.0}
        )
        return _extract_json_from_response(getattr(response, "text", ""), default)
    except Exception:
        return default.copy()


def _is_valid_email(email: str) -> bool:
    return bool(email) and "@" in email and "." in email


pending_registration: dict | None = None


def register_student(user_query: str, interactive: bool = True) -> str:
    """
    Register a student via LLM extraction. In interactive mode it prompts for
    missing details, and in non-interactive mode it asks for complete details.
    """
    prompt = f"""
    You are an intelligent data parsing assistant for a university system.
    Your goal is to identify and extract a person's name, major, and enrollment year from a query.

    First, understand the difference between a 'role' and a 'name':
    - A 'role' is a category like 'Student', 'Faculty', or 'Professor'.
    - A 'name' is the personal identifier, such as 'Alice' or 'John Doe'.

    Your primary instruction is to extract only the 'name'. The 'role' must be ignored.

    Return a JSON object with these keys:
    - "name": The person's name, excluding their role. Use null if not found.
    - "major": The academic field of study. Use null if not found.
    - "enrollment_year": The four-digit year. Use null if not found.

    Now extract from this query: "{user_query}"
    """
    global pending_registration

    parsed = _extract_fields_with_llm(
        prompt, {"name": None, "major": None, "enrollment_year": None}
    )

    name = parsed.get("name")
    major = parsed.get("major")
    year = parsed.get("enrollment_year")

    if pending_registration and pending_registration.get("type") == "student":
        previous = pending_registration.get("data", {})
        if not name:
            name = previous.get("name")
        if not major:
            major = previous.get("major")
        if year is None or str(year).strip() == "":
            year = previous.get("enrollment_year")

    missing_fields = []

    if not name:
        if interactive:
            name = input("Enter student name: ")
        else:
            missing_fields.append("name")

    if not major:
        if interactive:
            major = input("Enter student major: ")
        else:
            missing_fields.append("major")

    year_int = None
    if year is not None and str(year).strip() != "":
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            if interactive:
                print("❌ Please enter a valid year.")
            else:
                pending_registration = {
                    "type": "student",
                    "data": {"name": name, "major": major, "enrollment_year": None},
                }
                return (
                    "Enrollment year is invalid. Please provide a valid enrollment year "
                    "between 2000 and 2030. I will continue student registration once you share it."
                )

    if year_int is not None and not (2000 <= year_int <= 2030):
        if interactive:
            print("❌ Invalid year, must be between 2000 and 2030.")
            year_int = None
        else:
            pending_registration = {
                "type": "student",
                "data": {"name": name, "major": major, "enrollment_year": None},
            }
            return (
                "Enrollment year is invalid. Please provide a valid enrollment year "
                "between 2000 and 2030. I will continue student registration once you share it."
            )

    if interactive:
        while year_int is None:
            try:
                year_input = input("Enter enrollment year: ")
                candidate = int(year_input)
                if 2000 <= candidate <= 2030:
                    year_int = candidate
                else:
                    print("❌ Invalid year, must be between 2000 and 2030.")
            except ValueError:
                print("❌ Please enter a valid number.")
    elif year_int is None:
        missing_fields.append("enrollment year")

    if missing_fields:
        pending_registration = {
            "type": "student",
            "data": {
                "name": name,
                "major": major,
                "enrollment_year": year_int,
            },
        }
        return (
            "I need a few more student details. Missing: "
            + ", ".join(missing_fields)
            + ". Share them and I will complete the student registration."
        )

    try:
        with sqlite3.connect("university.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO students (name, major, enrollment_year) VALUES (?, ?, ?)",
                (name, major, year_int),
            )
            conn.commit()
        if pending_registration and pending_registration.get("type") == "student":
            pending_registration = None
        return f"✅ Student '{name}' has been added to the database."
    except sqlite3.IntegrityError:
        if pending_registration and pending_registration.get("type") == "student":
            pending_registration = None
        return f"⚠️ Student '{name}' already exists in the database."
    except sqlite3.Error:
        return "I couldn't register the student due to a database error."


def delete_student(user_query: str, interactive: bool = True) -> str:
    """
    Deletes a student by name. In interactive mode it can ask for the name.
    """
    prompt = f"""
    You are an intelligent data parsing assistant. Your goal is to extract the
    name of a student to be deleted from a query.

    Return a JSON object with one key:
    - "name": The name of the student to delete. Use null if not found.

    Analyze the query: "{user_query}"
    """
    parsed = _extract_fields_with_llm(prompt, {"name": None})
    name_to_delete = (parsed.get("name") or "").strip()

    with sqlite3.connect("university.db") as conn:
        cursor = conn.cursor()

        if not name_to_delete:
            if not interactive:
                return "Please provide the exact student name to delete. Example: Delete student Alice Johnson."

            print("Bot: Which student would you like to delete? Here are the current students:")
            cursor.execute("SELECT student_id, name FROM students ORDER BY name")
            all_students = cursor.fetchall()
            if not all_students:
                return "There are no students in the database to delete."

            for student in all_students:
                print(f"  ID: {student[0]}, Name: {student[1]}")
            name_to_delete = input("Enter the exact name of the student to delete: ").strip()

        if not name_to_delete:
            return "No student name was provided."

        cursor.execute("DELETE FROM students WHERE name = ?", (name_to_delete,))
        conn.commit()

        if cursor.rowcount > 0:
            return f"✅ Student '{name_to_delete}' has been deleted."
        return f"⚠️ No student found with the name '{name_to_delete}'."


def register_faculty(user_query: str, interactive: bool = True) -> str:
    """
    Register faculty via LLM extraction. In interactive mode it prompts for
    missing details, and in non-interactive mode it asks for complete details.
    """
    prompt = f"""
    You are an intelligent data parsing assistant for a university system.
    Your goal is to identify and extract a person's name and email from a query.

    Return a JSON object with these keys:
    - "name": The person's name, excluding role words like faculty/professor. Use null if not found.
    - "email": The person's email address. Use null if not found.

    Now extract from this query: "{user_query}"
    """
    global pending_registration

    parsed = _extract_fields_with_llm(prompt, {"name": None, "email": None})
    name = parsed.get("name")
    email = parsed.get("email")

    if pending_registration and pending_registration.get("type") == "faculty":
        previous = pending_registration.get("data", {})
        if not name:
            name = previous.get("name")
        if not email:
            email = previous.get("email")

    if not name:
        if interactive:
            name = input("Enter faculty name: ")
        else:
            pending_registration = {
                "type": "faculty",
                "data": {"name": None, "email": email},
            }
            return (
                "I need the faculty name to continue registration. Share the name and I will complete it."
            )

    if interactive:
        while not _is_valid_email(email):
            if email is not None:
                print("❌ Invalid email format! Please enter a valid email.")
            email = input("Enter faculty email: ").strip()
    else:
        if not _is_valid_email(email):
            pending_registration = {
                "type": "faculty",
                "data": {"name": name, "email": None},
            }
            return (
                "Faculty email is missing or invalid. Please share a valid email and I will complete "
                "the faculty registration."
            )

    try:
        with sqlite3.connect("university.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO faculty (name, email) VALUES (?, ?)",
                (name, email),
            )
            conn.commit()
        if pending_registration and pending_registration.get("type") == "faculty":
            pending_registration = None
        return f"✅ Faculty '{name}' has been added to the database."
    except sqlite3.IntegrityError:
        if pending_registration and pending_registration.get("type") == "faculty":
            pending_registration = None
        return "⚠️ That faculty email already exists in the database."
    except sqlite3.Error:
        return "I couldn't register the faculty member due to a database error."


def delete_faculty(user_query: str, interactive: bool = True) -> str:
    """
    Deletes a faculty member by name. In interactive mode it can ask for the name.
    """
    prompt = f"""
    You are an intelligent data parsing assistant. Your goal is to extract the
    name of a faculty member to be deleted from a query.

    Return a JSON object with one key:
    - "name": The name of the faculty member to delete. Use null if not found.

    Analyze the query: "{user_query}"
    """
    parsed = _extract_fields_with_llm(prompt, {"name": None})
    name_to_delete = (parsed.get("name") or "").strip()

    with sqlite3.connect("university.db") as conn:
        cursor = conn.cursor()

        if not name_to_delete:
            if not interactive:
                return "Please provide the exact faculty name to delete. Example: Delete faculty Dr. Evelyn Reed."

            print("Bot: Which faculty member would you like to delete? Here are the current faculty:")
            cursor.execute("SELECT faculty_id, name FROM faculty ORDER BY name")
            all_faculty = cursor.fetchall()
            if not all_faculty:
                return "There are no faculty members in the database to delete."

            for faculty in all_faculty:
                print(f"  ID: {faculty[0]}, Name: {faculty[1]}")
            name_to_delete = input("Enter the exact name of the faculty member to delete: ").strip()

        if not name_to_delete:
            return "No faculty name was provided."

        cursor.execute("DELETE FROM faculty WHERE name = ?", (name_to_delete,))
        conn.commit()

        if cursor.rowcount > 0:
            return f"✅ Faculty member '{name_to_delete}' has been deleted."
        return f"⚠️ No faculty member found with the name '{name_to_delete}'."

class Classifier(BaseModel):
    """Classifies the user query into supported university assistant intents."""
    label: Literal[
        "structured",
        "unstructured",
        "chit_chat",
        "register_student",
        "register_faculty",
        "delete_student",
        "delete_faculty",
        "help_register_student",
        "help_register_faculty",
        "help_delete_student",
        "help_delete_faculty",
    ] = Field(
        ...,
        description=(
            "Classify into: structured (database questions), unstructured (document/policy questions), "
            "chit_chat (casual greeting/thanks), register_student/register_faculty (adding records), "
            "delete_student/delete_faculty (removing records), help_register_student/help_register_faculty "
            "(steps to register), and help_delete_student/help_delete_faculty (steps to delete)."
        ),
    )

  # # --- PIPELINE 1: Unstructured (Text-to-RAG for Documents) ---

def get_unstructured_response(user_query: str, past_conversation: str) -> str:
    """
    Handles questions by searching documents and citing the sources (RAG pipeline).
    """

    # 1. Create a retriever to search the vector store.
    retriever = vector_store.as_retriever(search_kwargs={"k": 25})

    # 2. Find the relevant documents based on the user's query.
    retrieved_docs = retriever.invoke(user_query)

    # 3. If no documents are found, return a helpful message.
    if not retrieved_docs:
        return "I couldn't find any specific information about that in the university documents."

    # 4. Combine the content of the retrieved documents into a single "context".
    context = ""
    context = ""
    for i, doc in enumerate(retrieved_docs):
        source_info = f"Source {i+1} (from {doc.metadata.get('file_name', 'N/A')}, page {doc.metadata.get('page', 'N/A')}):"
        context += f"{source_info}\n{doc.page_content}\n\n---\n\n"

    # 5. Create the final prompt for the AI with instructions to cite sources.
    prompt = f"""You are a helpful university assistant. Answer the user's question based ONLY on the context provided below.
Your answer must be concise. After each piece of information, cite the source number in brackets, like this [file_name , page X].

If the answer cannot be found in the context, reply with:
"No information found in the provided documents."

Conversation history:
{past_conversation}



Context:
{context}

Question: {user_query}
"""

    # 6. Generate the final answer using the AI model.
    final_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

    return final_response.text

# # --- PIPELINE 2: STRUCTURED (Text-to-SQL for Database) ---
def get_database_response(user_query: str , past_conversation: str) -> str:
    """Handles specific data questions by querying the university database."""
    db_schema = """
    CREATE TABLE faculty (faculty_id INTEGER PRIMARY KEY, name TEXT, email TEXT);
    CREATE TABLE departments (department_id INTEGER PRIMARY KEY, department_name TEXT, head_id INTEGER);
    CREATE TABLE courses (course_id TEXT PRIMARY KEY, course_name TEXT, department_name TEXT, credits INTEGER);
    CREATE TABLE students (student_id INTEGER PRIMARY KEY, name TEXT, major TEXT, enrollment_year INTEGER);
    """

    prompt = f"""Given the database schema below, generate a valid SQLite query
to answer the user's question. Respond with ONLY the SQL query.


Conversation_History: {past_conversation}
Schema: {db_schema}
Question: '{user_query}'
SQL Query:"""

    try:

        sql_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        sql_query = sql_response.candidates[0].content.parts[0].text.strip()


        sql_query = (
            sql_query.replace("```sql", "")
            .replace("```", "")
            .replace("SQLQuery:", "")
            .replace("SQL Query:", "")
            .strip()
        )


    # Split into lines and find the first SQL statement
        lines = sql_query.split('\n')
        sql_lines = []
        found_statement = False
        for line in lines:
            if line.strip().upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
              found_statement = True
            if found_statement:
               sql_lines.append(line)
        sql_query = '\n'.join(sql_lines).strip()


        conn = sqlite3.connect("university.db")
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        conn.close()

        if not rows:
            return "I couldn't find any data in the database for that query."

        result_context = f"Query result: {[dict(zip(col_names, row)) for row in rows]}"
        final_prompt = f"""You are a helpful assistant. A database was queried to answer the user's question.
Convert the following raw data into a clear, natural language answer.

Data: {result_context}
User Question: '{user_query}'
Answer:"""


        final_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=final_prompt
        )
        return final_response.candidates[0].content.parts[0].text

    except Exception as e:
        return "I had trouble querying the database. Please rephrase your question."

def route_query(user_query: str) -> str:
    """
    Classifies a user query and returns ONLY the label of the intent.
    """
    prompt = """You are a query classifier for a university chatbot.
Return ONLY valid JSON in this exact format:
{"label":"<one_label>"}

Allowed labels:
- structured
- unstructured
- chit_chat
- register_student
- register_faculty
- delete_student
- delete_faculty
- help_register_student
- help_register_faculty
- help_delete_student
- help_delete_faculty

Decision rules (strict priority):
1) If user asks HOW / STEPS / PROCESS / REQUIREMENTS / WHAT DETAILS to register a STUDENT
   -> help_register_student
2) If user asks HOW / STEPS / PROCESS / REQUIREMENTS / WHAT DETAILS to register FACULTY/PROFESSOR/TEACHER
   -> help_register_faculty
3) If user asks HOW / STEPS / PROCESS / REQUIREMENTS / WHAT DETAILS to delete/remove a STUDENT
   -> help_delete_student
4) If user asks HOW / STEPS / PROCESS / REQUIREMENTS / WHAT DETAILS to delete/remove FACULTY/PROFESSOR/TEACHER
   -> help_delete_faculty
5) If user wants to actually perform student registration now, or provides student details
   -> register_student
6) If user wants to actually perform faculty registration now, or provides faculty details
   -> register_faculty
7) Student delete/remove/unenroll/drop
   -> delete_student
8) Faculty/professor/teacher delete/remove
   -> delete_faculty
9) Greetings/thanks/casual non-university
   -> chit_chat
10) Database-style factual university data query
   -> structured
11) Policy/rules/handbook/general doc query
   -> unstructured

Examples:
- "How can I register a student?" -> {"label":"help_register_student"}
- "How can I register faculty?" -> {"label":"help_register_faculty"}
- "How can I delete a student?" -> {"label":"help_delete_student"}
- "How can I remove faculty?" -> {"label":"help_delete_faculty"}
- "Register student Alice, CS, 2025" -> {"label":"register_student"}
- "Add faculty Dr. Reed, reed@university.edu" -> {"label":"register_faculty"}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"**Query:** {user_query}",
            config={
                "temperature": 0.0,
                "system_instruction": prompt,
                "response_mime_type": "application/json",
                "response_schema": Classifier
            }
        )
        parsed_json = json.loads(response.text)
        result = Classifier(**parsed_json)

        # print(f"\n--- DEBUG: Intent classified as: '{result.label}' ---\n")

        # The function's ONLY job is to return the label.
        return result.label

    except Exception as e:
        print(f"An error occurred in route_query: {e}")
        return "unstructured"


conversation_history = []


def university_chatbot(user_query: str, interactive: bool = True):
    """
    The main chatbot function that routes and answers the user's query.
    """
    global pending_registration

    # Add the new user message to the conversation history.
    conversation_history.append(("User", user_query))

    # Create the conversation history context.
    past_conversation = "\n".join(
        [f"{speaker}: {message}" for speaker, message in conversation_history]
    )

    # 1. Get the decision (the label) from the router
    intent = route_query(user_query)
    answer = ""

    # 2. Explicit help intents should return steps, not trigger registration parsing.
    if intent == "help_register_student":
        pending_registration = None
        answer = (
            "To register a student, share these details:\n"
            "1. Name\n"
            "2. Major\n"
            "3. Enrollment year (2000-2030)\n"
            "Example: Register student Alice Johnson, major Computer Science, enrollment year 2025."
        )
        conversation_history.append(("Assistant", answer))
        return answer

    if intent == "help_register_faculty":
        pending_registration = None
        answer = (
            "To register a faculty member, share these details:\n"
            "1. Name\n"
            "2. Email (valid format)\n"
            "Example: Register faculty Dr. Evelyn Reed, email evelyn.reed@university.edu."
        )
        conversation_history.append(("Assistant", answer))
        return answer

    if intent == "help_delete_student":
        pending_registration = None
        answer = (
            "To delete a student, share these details:\n"
            "1. Exact student name\n"
            "2. Optional confirmation message\n"
            "Example: Delete student Alice Johnson."
        )
        conversation_history.append(("Assistant", answer))
        return answer

    if intent == "help_delete_faculty":
        pending_registration = None
        answer = (
            "To delete a faculty member, share these details:\n"
            "1. Exact faculty name\n"
            "2. Optional confirmation message\n"
            "Example: Delete faculty Dr. Evelyn Reed."
        )
        conversation_history.append(("Assistant", answer))
        return answer

    # 3. Continue incomplete registration flows only for registration intents.
    # This prevents pending registration from hijacking unrelated queries (e.g. chit-chat).
    if not interactive and pending_registration:
        pending_type = pending_registration.get("type")
        if pending_type == "student" and intent in ("register_student", "help_register_student"):
            answer = register_student(user_query, interactive=False)
            conversation_history.append(("Assistant", answer))
            return answer
        elif pending_type == "faculty" and intent in ("register_faculty", "help_register_faculty"):
            answer = register_faculty(user_query, interactive=False)
            conversation_history.append(("Assistant", answer))
            return answer
        elif pending_type == "student" and intent == "register_faculty":
            pending_registration = None
        elif pending_type == "faculty" and intent == "register_student":
            pending_registration = None

    # 4. Call the correct pipeline based on the decision
    if intent == "structured":
        answer = get_database_response(user_query, past_conversation)
    elif intent == "unstructured":
        answer = get_unstructured_response(user_query, past_conversation)
    elif intent == "register_student":
        answer = register_student(user_query, interactive=interactive)
    elif intent == "register_faculty":
        answer = register_faculty(user_query, interactive=interactive)
    elif intent == "delete_student":
        answer = delete_student(user_query, interactive=interactive)
    elif intent == "delete_faculty":
        answer = delete_faculty(user_query, interactive=interactive)
    elif intent == "chit_chat":
        # The chit-chat response is now correctly generated here
        chit_chat_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"You are a friendly university assistant chatbot. Respond conversationally to this message, considering the history:\nHistory:\n{past_conversation}\n\nUser: {user_query}",
            config={"temperature": 0.7}
        )
        answer = chit_chat_response.text
    else:
        # A fallback for any unknown intents
        answer = get_unstructured_response(user_query, past_conversation)

    # Save assistant response for future context.
    conversation_history.append(("Assistant", answer))

    return answer


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")


class ChatResponse(BaseModel):
    reply: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Login username")
    password: str = Field(..., min_length=1, description="Login password")


class SessionStatusResponse(BaseModel):
    logged_in: bool
    username: str | None = None
    session_started: bool = False


FRONTEND_DIR = BASE_DIR / "frontend"


def _clear_chat_state() -> None:
    global pending_registration
    conversation_history.clear()
    pending_registration = None


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )


def _get_session(request: Request) -> tuple[str, dict] | tuple[None, None]:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None, None

    session = active_web_sessions.get(session_token)
    if not session:
        return None, None

    if time.time() >= session.get("expires_at", 0):
        active_web_sessions.pop(session_token, None)
        return None, None

    session["expires_at"] = time.time() + SESSION_MAX_AGE_SECONDS
    return session_token, session


def _require_session(request: Request) -> tuple[str, dict]:
    session_token, session = _get_session(request)
    if not session_token or not session:
        raise HTTPException(status_code=401, detail="Please login first.")
    return session_token, session


def _require_started_session(request: Request) -> tuple[str, dict]:
    session_token, session = _require_session(request)
    if not session.get("session_started", False):
        raise HTTPException(status_code=403, detail="Start a session first.")
    return session_token, session


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    setup_database()
    yield


app = FastAPI(title="University Bot API", lifespan=app_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return FileResponse(index_path)


@app.post("/api/login")
def login(payload: LoginRequest, response: Response):
    if payload.username != WEB_LOGIN_USERNAME or payload.password != WEB_LOGIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    session_token = secrets.token_urlsafe(32)
    active_web_sessions[session_token] = {
        "username": payload.username,
        "session_started": False,
        "expires_at": time.time() + SESSION_MAX_AGE_SECONDS,
    }
    _set_session_cookie(response, session_token)
    _clear_chat_state()
    return {"message": "Login successful.", "username": payload.username}


@app.get("/api/session/status", response_model=SessionStatusResponse)
def session_status(request: Request):
    _, session = _get_session(request)
    if not session:
        return SessionStatusResponse(logged_in=False, username=None, session_started=False)
    return SessionStatusResponse(
        logged_in=True,
        username=session.get("username"),
        session_started=session.get("session_started", False),
    )


@app.post("/api/session/start")
def start_session(request: Request):
    _, session = _require_session(request)
    session["session_started"] = True
    _clear_chat_state()
    return {"message": "Bot session started."}


@app.post("/api/session/exit")
def exit_session(request: Request, response: Response):
    session_token, _ = _require_session(request)
    active_web_sessions.pop(session_token, None)
    response.delete_cookie(SESSION_COOKIE_NAME)
    _clear_chat_state()
    return {"message": "Session ended. Logged out."}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request):
    _require_started_session(request)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    reply = university_chatbot(message, interactive=False)
    return ChatResponse(reply=reply)


@app.post("/api/reset")
def reset_chat(request: Request):
    _require_started_session(request)
    _clear_chat_state()
    return {"message": "Conversation reset."}


def chatbot_loop():
    """The main loop to interact with the chatbot."""
    print("\n" + "="*50)
    print("🎓 Welcome to the University AI Assistant! 🎓")
    print("You can ask about courses, faculty, or university policies.")
    print("Type 'exit' to quit.")
    print("="*50)

    while True:
        user_query = input("You: ")
        if user_query.lower() == "exit":
            print("Bot: Goodbye! 👋")
            break
        response = university_chatbot(user_query)
        print(f"Bot: {response}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="University chatbot CLI and web server")
    parser.add_argument("--cli", action="store_true", help="Run terminal/CLI chat mode")
    parser.add_argument("--host", default="127.0.0.1", help="Host for web mode")
    parser.add_argument("--port", type=int, default=8080, help="Port for web mode")
    args = parser.parse_args()

    if args.cli:
        setup_database()
        chatbot_loop()
    else:
        try:
            import uvicorn
        except ImportError:
            raise RuntimeError("uvicorn is required for web mode. Install it with: pip install uvicorn")
        uvicorn.run(app, host=args.host, port=args.port, reload=False)













import sqlite3

def view_table(table_name):
    conn = sqlite3.connect("university.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    print(f"\nTable: {table_name}")
    for row in rows:
        print(row)
    conn.close()


view_table("students")
view_table("faculty")

# !mv /content/vdb/* /content/drive/MyDrive/projects/vdb

# !mkdir /content/vdb
# !mv /content/drive/MyDrive/projects/vdb/* /content/vdb
