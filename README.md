# 🎓 University AI Assistant Chatbot

An intelligent, multi-functional AI chatbot designed to act as a centralized information hub for a university. This system leverages modern LLM capabilities to handle diverse user queries through dynamic routing and multiple backend pipelines.

---

## ✨ Key Features

### 🤖 Smart Intent Routing

A core classifier analyzes each user query and determines the user's intent (e.g., asking questions, registering a student, deleting records), routing it to the appropriate processing pipeline.

### 📚 Document Q&A (RAG)

Implements Retrieval-Augmented Generation (RAG) to answer questions about university policies, rules, and documents by retrieving relevant context from a vector database.

### 🗃️ Database Q&A (Text-to-SQL)

Handles structured queries such as:

* "Who teaches CS101?"
* "What courses are in the Physics department?"

The system dynamically generates and executes SQL queries to fetch real-time data.

### ✍️ Data Management (CRUD Operations)

Supports Create, Read, Update, and Delete operations through natural language. Authorized users can:

* Register students
* Add faculty
* Remove or update records

### 🗣️ Conversational Memory

Maintains context across interactions, enabling natural follow-up conversations.

---

## 🛠️ Tech Stack

### 🖥️ Backend

* Python
* FastAPI
* LangChain

### 🌐 Frontend

* HTML
* CSS
* JavaScript

### 🤖 AI Models

* Gemini 2.5 Flash
* Gemini Embedding Model (`gemini-embedding-001`)

### 🧠 Databases

* ChromaDB (Vector Store for RAG)
* SQLite (Structured Database for Text-to-SQL)

### ⚙️ Other Tools

* Pydantic (Data validation)
* Google Colab (Development environment)

---

## 🚀 How to Run

1. Clone the repository:

```bash
git clone https://github.com/your-username/your-repo.git
```

2. Navigate to the project directory:

```bash
cd your-repo
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set your API key:

```bash
export GOOGLE_API_KEY=your_api_key
```

5. Run the App:

```bash
python Bot.py
```

---

## 📌 Overview

This project combines LLMs, vector databases, and structured querying to create a powerful university assistant capable of answering both unstructured and structured queries intelligently.
