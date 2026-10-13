# AI Recruiter Agent

An AI-powered recruiter portfolio for exploring Sunculp Shukla’s professional profile and requesting an interview. Recruiters can ask profile questions, submit a job description for a concise profile comparison, and request an interview through the chat. Interview requests are screened against configurable rules, checked against generated availability, saved for owner approval, and then approved or declined from Telegram.

The application uses a FastAPI backend, a single-page HTML/CSS/JavaScript frontend, Groq-hosted chat completions, structured candidate data, and SQLite for interview requests and messages requiring review.

## Features

- **Profile Q&A:** Answers recruiter questions using the structured data in `candidate.json` and a profile-focused system prompt.
- **Job description review:** Asks the model to summarize a role, strong matches, missing skills, and overall suitability based on the candidate profile. This is an AI-generated comparison, not a formal scoring or ATS evaluation.
- **Interview request workflow:** Collects job details, checks them against screening rules, offers available slots, and records a selected slot as pending owner approval.
- **Availability checks:** Generates slots from configured working days, hours, blocked times, interview durations, notice period, booking limits, and time buffers. A chosen slot is checked again before it is saved.
- **Owner review:** Optional Telegram alerts include approval and decline buttons for interview requests. Only the configured Telegram chat owner can process those buttons.
- **Recruiter email updates:** After an owner approves or declines a request, the app can email the recruiter through Brevo.
- **Booking status lookup:** A recruiter can check a request using its booking ID and the same email address used to book.
- **Streaming chat UI:** The frontend reads server-sent events and displays the response in short chunks.
- **Per-visitor chat memory:** Each browser session has its own conversation history, which expires after inactivity.
- **Basic request throttling:** The backend limits requests by IP address in memory.

## How it works

1. A recruiter opens `index.html` and enters a question or interview request in the chat.
2. The page sends the message and a browser-generated session ID to the FastAPI `/chat` endpoint.
3. The backend builds the agent prompt from `candidate.json` and calls the Groq chat-completions API.
4. For scheduling, the model can request a narrowly defined tool. Python handlers perform screening, slot generation, booking validation, message saving, or booking status checks; the model does not directly access the database.
5. Booking and lead records are stored in SQLite. If Telegram is configured, the owner receives a background notification for new requests or messages requiring review.
6. An owner can approve or decline a pending booking in Telegram. The backend updates its status and attempts to send the recruiter an email through Brevo.
7. The backend streams the final answer to the browser as server-sent events.

## Architecture

```text
index.html (browser)
  └── POST /chat + session_id
        └── main.py (FastAPI, sessions, rate limiting, SSE)
              └── agent.py (Groq tool-calling loop and profile prompt)
                    ├── candidate.json (profile data)
                    └── tools.py (screening, availability, SQLite bookings/leads)
                          ├── telegram_bot.py (optional owner alerts and approvals)
                          └── emailer.py (optional Brevo decision emails)

config.py supplies owner, schedule, interview, and screening settings.
```

## Technology stack

- Python 3.14 (declared in `.python-version` and `pyproject.toml`)
- FastAPI, Uvicorn, Pydantic, and `python-dotenv`
- Groq Python SDK with model ID `openai/gpt-oss-120b`
- Function/tool calling for the scheduling workflow
- SQLite for booking requests and leads
- `httpx` for Brevo and Telegram HTTPS requests
- Python `zoneinfo` and `tzdata` for timezone-aware scheduling
- HTML, CSS, and vanilla JavaScript with the Fetch API and server-sent events
- Vercel and Render are referenced by the frontend and repository deployment links

## Repository layout

```text
.
├── agent.py          # Profile prompt and Groq tool-calling loop
├── candidate.json    # Structured profile content supplied to the agent
├── chatbot.py        # Older command-line profile chatbot
├── config.py         # Owner identity, availability, interview types, screening rules
├── emailer.py        # Optional Brevo recruiter decision emails
├── index.html        # Single-page portfolio, profile panel, and chat interface
├── main.py           # Active FastAPI service, / and /chat endpoints
├── main_old.py       # Earlier FastAPI implementation; not the active entry point
├── mini_proj.py      # Earlier resume-to-JSON extraction prototype
├── pyproject.toml    # Project metadata and dependency declarations
├── requirements.txt  # Pinned runtime dependencies
├── telegram_bot.py   # Optional Telegram alerts and approval polling
├── tools.py          # Scheduling, screening, SQLite persistence, and tool schemas
├── uv.lock           # uv dependency lock file
└── .gitignore        # Ignores local environments, secrets, and bookings.db
```

`main.py` is the backend entry point used by the current implementation. `main_old.py`, `chatbot.py`, and `mini_proj.py` are earlier or standalone experiments; they are not required to run the web application. `mini_proj.py` reads a machine-specific resume file path and should not be treated as a portable setup step.

## Requirements

- Python 3.14, as specified by this repository
- A Groq API key
- Internet access from the backend to call Groq
- For optional interview decisions by Telegram: a Telegram bot and the owner’s Telegram chat ID
- For optional recruiter decision emails: a Brevo API key and a verified sender address

## Local setup and run

1. Clone the repository and change into its directory.
2. Create and activate a virtual environment with Python 3.14.
3. Install the dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root. Add the required Groq key and, if using the optional integrations, their settings:

   ```dotenv
   GROQ_API_KEY=your_groq_api_key

   # Optional: Telegram owner alerts and approval buttons
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id

   # Optional: recruiter emails after approval or decline
   BREVO_API_KEY=your_brevo_api_key
   SENDER_EMAIL=your_verified_sender@example.com
   # Optional email settings
   SENDER_NAME=Your Name
   REPLY_TO_EMAIL=your_reply_address@example.com
   COPY_TO_EMAIL=your_copy_address@example.com

   # Optional SQLite file path; defaults to bookings.db
   BOOKINGS_DB=bookings.db
   ```

   The variable names above are read by the application. Do not commit `.env` or real credentials. Telegram and email settings are optional; the chatbot can run without them. Without Telegram, bookings can be saved but the built-in Telegram approval flow is unavailable. Without Brevo settings, decision emails cannot be sent.

5. Start the API:

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

6. Open `index.html` in a browser. The checked-in frontend currently points to the deployed backend URL in its `API_URL` constant. For local use, set that constant to `http://localhost:8000` before opening the page.

The backend’s root endpoint (`GET /`) returns a small running-status message. The chat endpoint is `POST /chat`; it accepts a non-empty `message` (up to 4,000 characters) and an optional `session_id`, and responds as a server-sent event stream.

## Configuration

Scheduling and screening behavior is configured in `config.py`:

- Owner name and owner timezone
- Working days, daily hours, blocked windows, maximum daily interviews, minimum notice, buffer, slot step, and scheduling horizon
- Durations for `hr`, `technical`, and `final` interviews
- Target role keywords, allowed work modes, and preferred locations

The current screening logic checks whether the role contains one of the configured keywords and whether the work mode and location pass the configured rules. It is a simple rule-based screen, not an AI hiring decision. The preferred locations list is empty by default, which means location is not restricted.

## Deployment notes

- The repository’s frontend contains a configured Render backend URL, and the repository page links to a Vercel portfolio. These are source configuration references; confirm that the deployments and URLs are still active before relying on them.
- A typical backend start command is `uvicorn main:app --host 0.0.0.0 --port $PORT` on a host that provides a `PORT` variable. Set `GROQ_API_KEY` and any optional integration settings in the hosting provider’s environment configuration.
- The app creates `bookings.db` by default in its working directory. On hosts with ephemeral filesystems, configure a persistent disk and point `BOOKINGS_DB` to a path on it if interview requests must survive restarts or redeployments.
- Chat sessions, their one-hour expiry, and per-IP rate-limit counters are held in process memory. They are not shared across multiple backend instances and reset when the process restarts.
- CORS currently allows all origins. Restrict `allow_origins` in `main.py` to the deployed frontend domain before using the service broadly.
- Telegram uses long polling in a background thread. Run only one backend instance with the same bot token to avoid competing pollers.

## Limitations

- Profile answers and job-description comparisons depend on the contents of `candidate.json` and model output. The prompt asks the model not to invent facts, but this does not guarantee error-free answers.
- The job-description comparison is generated text; there is no implemented numeric match score, resume upload, document ingestion, RAG pipeline, or vector database in the active web application.
- Screening uses configurable keyword and preference checks. It does not evaluate a recruiter or candidate beyond those rules.
- Interview requests remain pending until the owner approves them. Slot generation and booking validation are implemented, but there is no external calendar integration, meeting-link generation, or automatic confirmation.
- Booking and lead data use SQLite; deployment durability depends on the host’s storage configuration.
- Session and rate-limit state is in memory and intended for a small, single-instance portfolio deployment.
- The frontend API URL is hard-coded in `index.html`, so it must be changed when using a different backend.

## Possible next improvements

These follow directly from the current implementation’s boundaries:

- Restrict CORS to the actual portfolio domain and add production-focused request protections.
- Use shared persistent storage for bookings, sessions, and rate limits if scaling beyond one backend instance.
- Add a calendar provider integration if calendar conflict checking and calendar event creation are needed.
- Add automated tests for slot generation, double-booking prevention, approval permissions, and email outcomes.

## Author

**Sunculp Shukla**

- [GitHub](https://github.com/Sunculp09)
- [LinkedIn](https://www.linkedin.com/in/sunculp-shukla-2640232a1/)
- [Portfolio](https://sunculp-ai.vercel.app)
