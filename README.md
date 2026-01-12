# Speech-to-Sign Aid (STS)

Speech-to-Sign Aid is a real-time accessibility prototype that converts live speech or captions into visual sign-based representations for Deaf and hard-of-hearing users. Instead of attempting full sign language translation, STS focuses on low latency and clear visual output using a limited set of predefined signs and symbols.

This MVP shows that real-time speech-to-visual communication can work in classrooms, meetings, and presentations.

---

## What It Does

Speech-to-Sign Aid:
- Listens to live speech or accepts auto-generated captions  
- Converts speech into normalized text  
- Matches keywords and phrases to a set of sign animations and visual symbols  
- Displays visual output in real time  
- Uses fingerspelling or text when a word is not supported  

The goal is not perfect translation, but fast and understandable communication.

---

## Why It Matters

Captions can be slow and tiring to follow. Many Deaf users rely more on visual language.  
STS provides a visual way to follow spoken content that is easier to process in live settings.

---

## How It Works

1. Speech is captured using the Web Speech API or from caption input  
2. The text is cleaned and standardized  
3. A rule-based and AI-assisted matching system maps words and phrases to signs  
4. Unknown words fall back to fingerspelling or text  
5. The frontend shows the matching signs in sync with the speech  

---

## Built With

- Python and Flask for the backend  
- Google Gemini API for phrase and intent matching  
- Web Speech API for speech recognition  
- HTML, CSS, and JavaScript for the frontend  
- Gesture and sign video assets  
- A rule-based sign mapping engine  

---

## Key Features

- Real-time speech to sign conversion  
- Phrase and keyword matching  
- Fingerspelling for unknown words  
- Fast and low-latency display  
- Simple and accessible user interface  
- Optional live camera gesture demo  

---

## MVP Limitations

This is a prototype, not a full sign language translator.

- Uses a limited sign vocabulary  
- Does not model grammar or facial expression  
- Focuses on speed and clarity rather than full language coverage  

---

## What’s Next

Future versions will:
- Add more signs and phrases  
- Improve how context is handled  
- Support sentence flow and tense  
- Improve avatar and sign animation  
- Include user testing with Deaf and hard-of-hearing users  

---

## Project Goal

This project shows that live speech can be turned into useful visual signs in real time.  
It is a foundation for building more advanced accessibility tools in the future.

---

## Team

Built as a hackathon prototype to explore real-time communication access.
