# AI Oral Exam Grader – Planning Skeleton

Below is the current design outline and module structure for the team. This document explains how the application is organized and what it is intended to accomplish.

The project skeleton is designed as a layered Python system rather than one big script. FastAPI and Uvicorn provide the student-facing web server, which is responsible only for presenting pages and receiving input. A dedicated exam service manages session state, timers, and question order so that each exam instance remains consistent once a student starts. All long-term data is handled through SQLAlchemy and migrations, keeping questions, attempts, and grading results stored safely in a database that professors can later inspect.

Interaction with the AI models is isolated in core/llm/ and core/grading/. Prompt templates live as external text files containing placeholders, and Python code completes those templates in real time based on the current domain and exam rules. The LLM client module sends the finished prompts to together.ai and receives structured JSON responses. Guardrail code then validates that the model output matches Pydantic schemas before anything is shown to a student or saved. This makes the system reproducible, auditable, and easy for multiple developers to work on at the same time.

These technical pieces directly support the main requirements of the application. As CS seniors building a real AI-assisted tool, we must accomplish a full exam workflow: automatically generate essay-style exam questions with background information and a grading rubric, present those questions to students through a browser, collect written answers, evaluate them against the rubric, and store the graded results. The app also needs to produce a final exam grade and explanation at the end, potentially with follow-up questions when answers are weak. The skeleton gives us a clear structure for meeting those goals in a way that can later scale to many students and more advanced features.

---

## Project Skeleton

```
ai-oral-exam-grader/
├─ README.md
├─ pyproject.toml
├─ .env.example
├─ .gitignore
│
├─ prompts/
│  ├─ question_gen_v1.txt
│  ├─ grade_response_v1.txt
│  ├─ final_grade_v1.txt
│  └─ followup_gen_v1.txt
│
├─ app/
│  ├─ main.py
│  ├─ settings.py
│  ├─ logging_config.py
│  │
│  ├─ api/
│  │  ├─ router.py
│  │  ├─ health.py
│  │  ├─ auth.py
│  │  └─ exam.py
│  │
│  ├─ core/
│  │  ├─ llm/
│  │  │  ├─ client.py
│  │  │  ├─ prompts.py
│  │  │  └─ guardrails.py
│  │  │
│  │  ├─ grading/
│  │  │  ├─ generator.py
│  │  │  ├─ grader.py
│  │  │  ├─ finalizer.py
│  │  │  └─ thresholds.py
│  │  │
│  │  └─ schemas/
│  │     ├─ llm_contracts.py
│  │     └─ api_models.py
│  │
│  ├─ db/
│  │  ├─ session.py
│  │  ├─ base.py
│  │  ├─ models.py
│  │  └─ repo.py
│  │
│  ├─ services/
│  │  └─ exam_service.py
│  │
│  ├─ templates/
│  │  ├─ login.html
│  │  ├─ question.html
│  │  └─ complete.html
│  │
│  └─ static/
│     └─ styles.css
│
└─ tests/
   ├─ test_prompt_loading.py
   ├─ test_llm_contract_validation.py
   └─ fixtures/
```

---

## Module Responsibilities Summary

### prompts/

This folder stores all prompt templates used to communicate with the language models. These files define exactly how questions are generated and how answers must be graded.

### app/main.py

Creates the FastAPI application and includes all routers.

### app/settings.py

Loads environment variables and global configuration such as API keys and database connection strings.

### app/api/

Contains only HTTP routes. This layer deals with students and professors through the web, validating input and returning responses.

### app/core/llm/

Wraps communication with together.ai. Responsible for loading prompt files, filling placeholders, sending them to the LLM, and receiving responses.

### app/core/grading/

The main logic layer. Orchestrates question generation, grading, threshold checks, optional follow-ups, and final grade compilation.

### app/core/schemas/

Holds Pydantic models that act as contracts between Python and the LLM outputs so structured JSON responses can be trusted.

### app/db/

SQLAlchemy and Alembic boundary. Manages database sessions, ORM models, and CRUD operations.

### services/exam_service.py

Coordinates the overall exam workflow and maintains per-student session state.

### tests/

Contains unit and integration tests along with sample model outputs used as fixtures for validation.

---

## What the Application Must Accomplish

To meet the real-world needs of professors and students, the program must:

1. Generate essay-style exam questions automatically in real time.
2. Present those questions to students through a standard web browser.
3. Collect written responses from each student.
4. Evaluate those essays using a clear, structured grading rubric.
5. Store graded questions, answers, scores, and explanations in a database.
6. Produce a final exam grade with a summary explanation.

This design outline is the current foundation the team will build on and improve throughout the quarter.

---

## Quick Start (For Team Members)

### 🚀 Fastest Way to Get Started

**Windows (PowerShell):**
```powershell
git clone <your-repo-url>
cd ai-oral-exam-grader
.\setup.ps1
python run.py
```

**Mac/Linux:**
```bash
git clone <your-repo-url>
cd ai-oral-exam-grader
chmod +x setup.sh
./setup.sh
python run.py
```

Then open **http://localhost:8000** in your browser!

Current working Login
(Both have same results until dashboards are added)

Student: 
student@test.com
password123

Teacher:
teacher@test.com
password123

### Manual Setup (5 Steps)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd ai-oral-exam-grader
   ```

2. **Install dependencies:**
   ```bash
   pip install -e .
   pip install together
   ```

3. **Initialize the database:**
   ```bash
   python -m app.db.init_db
   ```

4. **Run the application(Run seed_users.py once):**
   ```bash
   python run.py
   ```

5. **Open your browser:**
   - Navigate to `http://localhost:8000`
   - Enter a username to start an exam

### ✅ Key Points

- **No API key required!** The app works in demo mode with pre-written questions
- **3 different questions** ready to test the full workflow
- **Basic grading** works immediately without any setup
- See `TEAM_SETUP.md` for detailed team setup instructions
- See `API_KEY_GUIDE.md` if you want AI features (optional)

### Troubleshooting

- **Import errors?** → Run `pip install -e .` again
- **Port 8000 in use?** → Change port in `run.py` or stop other app
- **Database errors?** → Delete `exam_grader.db` and run `python -m app.db.init_db`

**Need more help?** Check `TEAM_SETUP.md` for detailed troubleshooting.

