# AI Portfolio

An AI-powered portfolio that allows recruiters to interact with an AI representative of my professional profile.

## Overview

This project uses an AI model, structured candidate data, and a web interface to create an interactive portfolio for recruiters.

## Key Features

- AI-powered recruiter chatbot
- Answers questions about my professional profile
- Uses structured candidate data from my resume
- Conversation memory
- Job Description analysis
- JD vs profile matching
- Identifies missing skills
- Designed to avoid AI hallucinations

## How It Works

1. Recruiter enters a question or Job Description.
2. FastAPI receives the request.
3. The system identifies whether it is a normal question or JD.
4. Candidate information is loaded from structured JSON data.
5. Groq AI generates the response.
6. The response is displayed in the web interface.

## Technology Stack

- Python
- FastAPI
- Groq API
- Pydantic
- HTML
- CSS
- JavaScript
- JSON
- Git & GitHub
- Render
- Vercel

## Project Architecture

Recruiter
    ↓
Vercel Frontend
    ↓
FastAPI Backend
    ↓
Question / JD Classification
    ↓
Groq AI
    ↓
Candidate Profile JSON
    ↓
AI Response

## AI Behavior

The AI representative is designed to:

- Use only the provided candidate information
- Avoid making up information
- Clearly state when information is unavailable
- Answer professional profile-related questions
- Analyze Job Descriptions against the candidate profile
- Provide concise and relevant responses.

## Project Structure

    AI-Portfolio/
    ├── main.py
    ├── chatbot.py
    ├── candidate.json
    ├── index.html
    ├── resume.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── uv.lock
    ├── README.md
    └── .gitignore

## Deployment
Frontend: Vercel
Backend: Render
AI Model: Groq


## Purpose

This project demonstrates the integration of Generative AI, structured candidate data, FastAPI, and a web interface to build an interactive AI-powered professional portfolio.

## Author:

Sunculp Shukla
Data Analytics | AI Engineering | Business Analysis

## Live Demo

[Visit AI Portfolio](https://ai-portfolio-eosin-sigma.vercel.app/)