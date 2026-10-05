import os
import json
from time import sleep
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field
from typing import Optional
import re

load_dotenv()
my_api_key=os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError("API key is missing.")

client = Groq(api_key=my_api_key)
model = "openai/gpt-oss-120b"


class PersonalInfo(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    personal_email: Optional[str] = None
    college_email: Optional[str] = None


class Education(BaseModel):
    college: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    current_cgpa: Optional[float] = None
    percentage_12th: Optional[float] = None
    percentage_10th: Optional[float] = None


class Experience(BaseModel):
    company: Optional[str] = None
    tenure: Optional[str] = None
    role: Optional[str] = None
    responsibilities: list[str] = []
    learnings: list[str] = []


class Project(BaseModel):
    name: Optional[str] = None
    aim: Optional[str] = None
    technologies_used: list[str] = []
    skills_required: list[str] = []
    tenure: Optional[str] = None
    mode: Optional[str] = None
    learnings: list[str] = []
    outcome: Optional[str] = None
    real_world_problem_solved: Optional[str] = None


class Skills(BaseModel):
    data_analytics: list[str] = []
    gen_ai_agentic_ai: list[str] = []
    core_engineering: list[str] = []
    tools: list[str] = []
    software: list[str] = []


class Certification(BaseModel):
    certification_for: Optional[str] = None
    provider: Optional[str] = None
    completion_date: Optional[str] = None


class PortfolioLinks(BaseModel):
    github: Optional[str] = None
    linkedin: Optional[str] = None
    tableau: Optional[str] = None


class Candidate(BaseModel):
    personal_info: Optional[PersonalInfo] = None
    education: Optional[Education] = None
    experience: list[Experience] = []
    projects: list[Project] = []
    skills: Optional[Skills] = None
    certifications: list[Certification] = []
    portfolio_links: Optional[PortfolioLinks] = None
    soft_skills: list[str] = []
    achievements: list[str] = []

candidate_schema = Candidate.model_json_schema()

response_format = {
    "type":"json_object"
}

with open(r"C:\Users\suncu\OneDrive\Documents\resume_all.md", "r", encoding="utf-8") as file:
    resume_text = file.read()


def call_llm(system_prompt, user_prompt, response_format) :

    message_system = {
            "role":"system",
            "content":system_prompt
        }

    message = {
            "role":"user",
            "content":user_prompt
        }

    messages = [message_system, message]

    response = client.chat.completions.create(model = model, messages = messages, temperature = 0, response_format = response_format)
    answer = response.choices[0].message.content

    data = json.loads(answer)
    info = Candidate(**data)
    return info

# Preparing Resume for Recruiter...
 
sys_pmt = f"""

You are an expert resume parser and information extraction assistant for HR.
Your task is to extract all important and relevant information from the given resume.
You must return the answer strictly in the given JSON object format only.

The JSON schema is:
{candidate_schema}
Fill the schema with the actual information extracted from the resume.
Do not return the schema itself.

Your constraints and rules are:
1. Use only the information explicitly provided in the resume.
2. Never invent, assume, or infer information that is not supported by the resume.
3. If information for a field is not available in the resume, return null for optional fields and an empty list [] for list fields.
4. Preserve the original meaning of the resume while structuring the information.
5. Do not add ATS keywords that are not explicitly supported by the resume.
6. Return only a valid JSON object. Do not include explanations, comments, markdown, or any text outside the JSON object.

"""

user_pmt = f"""

Extract the information from given resume text. 
{resume_text}

"""

Resume = call_llm(sys_pmt,user_pmt, response_format)

with open("candidate.json", "w", encoding="utf-8") as file:
    file.write(Resume.model_dump_json(indent=4))

print("Resume parsed and candidate data saved.")

