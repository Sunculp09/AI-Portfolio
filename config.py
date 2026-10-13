"""
config.py - everything Sunculp can tune WITHOUT touching the agent logic.

Edit the values below to match your real availability and preferences.
"""

OWNER_NAME = "Sunculp Shukla"
OWNER_TZ = "Asia/Kolkata"  # IANA timezone name

# ---------------------------------------------------------------------------
# Availability rules (all times are in OWNER_TZ)
# ---------------------------------------------------------------------------
AVAILABILITY = {
    "working_days": [0, 1, 2, 3, 4, 5],   # Monday=0 ... Sunday=6 (Mon-Sat)
    "start": "10:00",                      # earliest interview start
    "end": "18:00",                        # latest interview end
    "blocked": [("13:00", "14:00")],       # daily blocked windows (lunch, prayer, classes)
    "max_per_day": 2,                      # max interviews on one day
    "min_notice_hours": 24,                # do not offer slots sooner than this
    "buffer_minutes": 15,                  # gap kept before/after each interview
    "horizon_days": 14,                    # how far ahead slots are offered
    "step_minutes": 30,                    # slot start times: 10:00, 10:30, ...
}

# Interview types and their duration in minutes
INTERVIEW_TYPES = {
    "hr": 20,
    "technical": 45,
    "final": 60,
}

# ---------------------------------------------------------------------------
# Screening rules - used by the check_fit tool
# ---------------------------------------------------------------------------
SCREENING = {
    # A role is a "match" if its title contains any of these words
    "target_roles": [
        "data analyst", "data analytics", "business analyst", "business intelligence",
        "bi analyst", "bi developer", "data scientist", "data engineer",
        "ai engineer", "ml engineer", "machine learning", "genai", "gen ai",
        "llm", "analytics", "analyst",
    ],
    "work_modes": ["remote", "hybrid", "onsite"],
    # Leave empty if you are open to any location
    "preferred_locations": [],
}
