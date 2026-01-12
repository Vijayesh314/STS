import os
import json
import re
import logging
from functools import lru_cache
from typing import Dict, List, Tuple, Optional, TypedDict
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
import google.generativeai as genai

# Logging configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Directory containing letter/phrase videos (relative to this file)
VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "videos")

# (No authentication required by default)

# Basic security limits
# Reject very large requests early (text inputs are expected to be small)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64KB max request body

# Optional rate limiting (if flask-limiter is installed, it will be enabled)
try:
    from flask_limiter import Limiter  # type: ignore
    from flask_limiter.util import get_remote_address  # type: ignore

    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    limiter.init_app(app)
    logger.info("Flask-Limiter enabled with default limits")
except Exception:
    limiter = None
    logger.debug("Flask-Limiter not available; skipping rate limiting setup")

# Configure Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("Gemini API configured")
    except Exception as e:
        logger.warning("Failed to configure Gemini API: %s", e)


class SignData(TypedDict):
    word: str
    category: str
    synonyms: List[str]
    description: str
    animation_type: str  # 'css', 'gif', 'video'
    animation_data: Optional[Dict[str, str]]  # Additional animation metadata


# Classroom vocabulary with sign data
SIGN_VOCABULARY = {
    # Greetings
    "hello": {
        "word": "hello",
        "category": "greetings",
        "synonyms": ["hi", "hey", "greetings"],
        "description": "Wave hand near face",
        "animation_type": "css",
        "animation_data": {"class": "wave-animation"}
    },
    "goodbye": {
        "word": "goodbye",
        "category": "greetings",
        "synonyms": ["bye", "farewell", "see you", "later"],
        "description": "Wave hand away from body"
    },
    "thank you": {
        "word": "thank you",
        "category": "greetings",
        "synonyms": ["thanks", "appreciate", "grateful"],
        "description": "Hand moves from chin outward"
    },
    "please": {
        "word": "please",
        "category": "greetings",
        "synonyms": ["kindly"],
        "description": "Circular motion on chest"
    },
    "sorry": {
        "word": "sorry",
        "category": "greetings",
        "synonyms": ["apologize", "apologies", "my bad"],
        "description": "Fist circles on chest"
    },
    "good morning": {
        "word": "good morning",
        "category": "greetings",
        "synonyms": ["morning"],
        "description": "Point to sky then wave"
    },
    "good afternoon": {
        "word": "good afternoon",
        "category": "greetings",
        "synonyms": ["afternoon"],
        "description": "Point to sun then wave"
    },
    "good evening": {
        "word": "good evening",
        "category": "greetings",
        "synonyms": ["evening"],
        "description": "Point to horizon then wave"
    },
    "good night": {
        "word": "good night",
        "category": "greetings",
        "synonyms": ["night", "sleep well"],
        "description": "Rest head on hands"
    },
    "nice to meet you": {
        "word": "nice to meet you",
        "category": "greetings",
        "synonyms": ["pleased to meet you"],
        "description": "Shake hands gesture"
    },
    "how are you": {
        "word": "how are you",
        "category": "greetings",
        "synonyms": ["how do you do", "how's it going"],
        "description": "Point to self then others"
    },
    "i'm fine": {
        "word": "i'm fine",
        "category": "greetings",
        "synonyms": ["i'm good", "i'm well", "i'm okay"],
        "description": "Thumbs up with smile gesture"
    },
    "have a good day": {
        "word": "have a good day",
        "category": "greetings",
        "synonyms": ["have a nice day"],
        "description": "Wave with both hands"
    },

    # Responses
    "yes": {
        "word": "yes",
        "category": "responses",
        "synonyms": ["yeah", "yep", "correct", "right", "affirmative", "okay", "ok"],
        "description": "Fist nods up and down"
    },
    "no": {
        "word": "no",
        "category": "responses",
        "synonyms": ["nope", "negative", "wrong", "incorrect"],
        "description": "Two fingers close to thumb"
    },
    "maybe": {
        "word": "maybe",
        "category": "responses",
        "synonyms": ["perhaps", "possibly", "might"],
        "description": "Hands alternate up and down"
    },
    "understand": {
        "word": "understand",
        "category": "responses",
        "synonyms": ["get it", "comprehend", "got it", "clear", "makes sense"],
        "description": "Index finger flicks up near forehead"
    },
    "confused": {
        "word": "confused",
        "category": "responses",
        "synonyms": ["don't understand", "unclear", "lost", "puzzled"],
        "description": "Curved fingers alternate near forehead"
    },
    "i know": {
        "word": "i know",
        "category": "responses",
        "synonyms": ["i understand", "got it"],
        "description": "Tap forehead with index finger"
    },
    "i don't know": {
        "word": "i don't know",
        "category": "responses",
        "synonyms": ["not sure", "uncertain"],
        "description": "Shrug shoulders with palms up"
    },
    "wait": {
        "word": "wait",
        "category": "responses",
        "synonyms": ["hold on", "just a moment"],
        "description": "Palm facing out, fingers spread"
    },

    # Actions
    "question": {
        "word": "question",
        "category": "actions",
        "synonyms": ["ask", "query", "inquire"],
        "description": "Index finger draws question mark"
    },
    "answer": {
        "word": "answer",
        "category": "actions",
        "synonyms": ["reply", "respond", "response"],
        "description": "Index fingers point outward from mouth"
    },
    "help": {
        "word": "help",
        "category": "actions",
        "synonyms": ["assist", "aid", "support"],
        "description": "Thumbs up on flat palm, lift up"
    },
    "repeat": {
        "word": "repeat",
        "category": "actions",
        "synonyms": ["again", "say again", "one more time"],
        "description": "Curved hand flips over"
    },
    "stop": {
        "word": "stop",
        "category": "actions",
        "synonyms": ["wait", "hold", "pause", "halt"],
        "description": "Flat hand strikes palm"
    },
    "start": {
        "word": "start",
        "category": "actions",
        "synonyms": ["begin", "go", "commence"],
        "description": "Index finger twists between fingers"
    },
    "finish": {
        "word": "finish",
        "category": "actions",
        "synonyms": ["done", "complete", "end", "finished", "over"],
        "description": "Open hands flip outward"
    },
    "read": {
        "word": "read",
        "category": "actions",
        "synonyms": ["reading"],
        "description": "Two fingers scan across palm"
    },
    "write": {
        "word": "write",
        "category": "actions",
        "synonyms": ["writing", "note"],
        "description": "Pinched fingers write on palm"
    },
    "listen": {
        "word": "listen",
        "category": "actions",
        "synonyms": ["hear", "hearing", "listening"],
        "description": "Cupped hand to ear"
    },
    "speak": {
        "word": "speak",
        "category": "actions",
        "synonyms": ["talk", "say", "tell", "talking", "speaking"],
        "description": "Four fingers tap from chin"
    },
    "think": {
        "word": "think",
        "category": "actions",
        "synonyms": ["thinking", "consider", "thought"],
        "description": "Index finger circles at temple"
    },
    "learn": {
        "word": "learn",
        "category": "actions",
        "synonyms": ["study", "learning", "studying"],
        "description": "Fingers pull from palm to forehead"
    },
    "teach": {
        "word": "teach",
        "category": "actions",
        "synonyms": ["teaching", "instruct", "explain"],
        "description": "Both hands pull from forehead outward"
    },
    "work": {
        "word": "work",
        "category": "actions",
        "synonyms": ["working", "job"],
        "description": "Fists alternate pounding"
    },
    "play": {
        "word": "play",
        "category": "actions",
        "synonyms": ["playing", "fun"],
        "description": "Fingers wiggle like playing"
    },
    "eat": {
        "word": "eat",
        "category": "actions",
        "synonyms": ["eating", "food"],
        "description": "Hand to mouth"
    },
    "drink": {
        "word": "drink",
        "category": "actions",
        "synonyms": ["drinking"],
        "description": "Tilt hand to mouth"
    },
    "sleep": {
        "word": "sleep",
        "category": "actions",
        "synonyms": ["sleeping", "rest"],
        "description": "Rest head on hands"
    },
    "walk": {
        "word": "walk",
        "category": "actions",
        "synonyms": ["walking"],
        "description": "Two fingers walk on other hand"
    },
    "run": {
        "word": "run",
        "category": "actions",
        "synonyms": ["running"],
        "description": "Fingers run quickly"
    },

    # People
    "teacher": {
        "word": "teacher",
        "category": "nouns",
        "synonyms": ["instructor", "professor", "educator"],
        "description": "Teach sign plus person marker"
    },
    "student": {
        "word": "student",
        "category": "nouns",
        "synonyms": ["learner", "pupil"],
        "description": "Learn sign plus person marker"
    },
    "person": {
        "word": "person",
        "category": "nouns",
        "synonyms": ["people", "individual", "someone"],
        "description": "Point to person"
    },
    "man": {
        "word": "man",
        "category": "nouns",
        "synonyms": ["male", "guy", "boy"],
        "description": "Flat hand strikes forehead"
    },
    "woman": {
        "word": "woman",
        "category": "nouns",
        "synonyms": ["female", "lady", "girl"],
        "description": "Brush hair back"
    },
    "child": {
        "word": "child",
        "category": "nouns",
        "synonyms": ["kid", "children", "baby"],
        "description": "Small height gesture"
    },
    "friend": {
        "word": "friend",
        "category": "nouns",
        "synonyms": ["buddy", "pal"],
        "description": "Hook fingers together"
    },
    "family": {
        "word": "family",
        "category": "nouns",
        "synonyms": ["relatives"],
        "description": "F hands circle together"
    },
    "mother": {
        "word": "mother",
        "category": "nouns",
        "synonyms": ["mom", "mama"],
        "description": "Thumb brushes chin"
    },
    "father": {
        "word": "father",
        "category": "nouns",
        "synonyms": ["dad", "papa"],
        "description": "F hand strikes forehead"
    },
    "brother": {
        "word": "brother",
        "category": "nouns",
        "synonyms": ["bro"],
        "description": "B hand strikes forehead"
    },
    "sister": {
        "word": "sister",
        "category": "nouns",
        "synonyms": ["sis"],
        "description": "S hand brushes chin"
    },

    # Places
    "home": {
        "word": "home",
        "category": "nouns",
        "synonyms": ["house"],
        "description": "Fingers form roof over head"
    },
    "school": {
        "word": "school",
        "category": "nouns",
        "synonyms": ["classroom"],
        "description": "C hands circle outward"
    },
    "class": {
        "word": "class",
        "category": "nouns",
        "synonyms": ["classroom", "course", "lesson"],
        "description": "C hands circle outward"
    },
    "bathroom": {
        "word": "bathroom",
        "category": "nouns",
        "synonyms": ["restroom", "toilet"],
        "description": "T hand waves"
    },
    "kitchen": {
        "word": "kitchen",
        "category": "nouns",
        "synonyms": ["cook"],
        "description": "Stir motion"
    },
    "bedroom": {
        "word": "bedroom",
        "category": "nouns",
        "synonyms": ["bed"],
        "description": "Rest head on hands"
    },

    # Objects
    "book": {
        "word": "book",
        "category": "nouns",
        "synonyms": ["textbook"],
        "description": "Palms open like book"
    },
    "paper": {
        "word": "paper",
        "category": "nouns",
        "synonyms": ["document", "sheet"],
        "description": "Palms brush together twice"
    },
    "test": {
        "word": "test",
        "category": "nouns",
        "synonyms": ["exam", "quiz", "examination"],
        "description": "X hands pull down and open"
    },
    "homework": {
        "word": "homework",
        "category": "nouns",
        "synonyms": ["assignment", "work"],
        "description": "Home sign plus work sign"
    },
    "computer": {
        "word": "computer",
        "category": "nouns",
        "synonyms": ["laptop", "pc"],
        "description": "Type on keyboard"
    },
    "phone": {
        "word": "phone",
        "category": "nouns",
        "synonyms": ["telephone", "cell phone"],
        "description": "Hand to ear like phone"
    },
    "table": {
        "word": "table",
        "category": "nouns",
        "synonyms": ["desk"],
        "description": "Flat hand horizontal"
    },
    "chair": {
        "word": "chair",
        "category": "nouns",
        "synonyms": ["seat"],
        "description": "Sit down gesture"
    },
    "door": {
        "word": "door",
        "category": "nouns",
        "synonyms": ["entrance"],
        "description": "Open door motion"
    },
    "window": {
        "word": "window",
        "category": "nouns",
        "synonyms": ["glass"],
        "description": "Square window frame"
    },
    "water": {
        "word": "water",
        "category": "nouns",
        "synonyms": ["drink"],
        "description": "W hand waves"
    },
    "food": {
        "word": "food",
        "category": "nouns",
        "synonyms": ["eat"],
        "description": "Hand to mouth"
    },
    "money": {
        "word": "money",
        "category": "nouns",
        "synonyms": ["cash", "dollar"],
        "description": "Rub thumb and fingers"
    },
    "time": {
        "word": "time",
        "category": "nouns",
        "synonyms": ["clock", "hour"],
        "description": "Point to watch"
    },
    "day": {
        "word": "day",
        "category": "nouns",
        "synonyms": ["today"],
        "description": "Circle overhead"
    },
    "night": {
        "word": "night",
        "category": "nouns",
        "synonyms": ["dark"],
        "description": "Rest head on hands"
    },

    # Descriptors
    "good": {
        "word": "good",
        "category": "descriptors",
        "synonyms": ["great", "nice", "well", "excellent", "fine"],
        "description": "Flat hand from chin to palm"
    },
    "bad": {
        "word": "bad",
        "category": "descriptors",
        "synonyms": ["poor", "terrible", "awful", "wrong"],
        "description": "Flat hand from chin flips down"
    },
    "easy": {
        "word": "easy",
        "category": "descriptors",
        "synonyms": ["simple", "not hard"],
        "description": "Curved fingers brush upward"
    },
    "hard": {
        "word": "hard",
        "category": "descriptors",
        "synonyms": ["difficult", "tough", "challenging"],
        "description": "Bent V hands knock together"
    },
    "fast": {
        "word": "fast",
        "category": "descriptors",
        "synonyms": ["quick", "quickly", "rapid", "speed"],
        "description": "L hands pull back quickly"
    },
    "slow": {
        "word": "slow",
        "category": "descriptors",
        "synonyms": ["slowly", "slower"],
        "description": "Hand drags up back of hand"
    },
    "important": {
        "word": "important",
        "category": "descriptors",
        "synonyms": ["significant", "key", "critical", "essential"],
        "description": "F hands circle up to center"
    },
    "big": {
        "word": "big",
        "category": "descriptors",
        "synonyms": ["large", "huge"],
        "description": "Hands spread apart"
    },
    "small": {
        "word": "small",
        "category": "descriptors",
        "synonyms": ["little", "tiny"],
        "description": "Pinch fingers close"
    },
    "hot": {
        "word": "hot",
        "category": "descriptors",
        "synonyms": ["warm", "heat"],
        "description": "Wipe brow"
    },
    "cold": {
        "word": "cold",
        "category": "descriptors",
        "synonyms": ["cool", "freezing"],
        "description": "Shiver motion"
    },
    "happy": {
        "word": "happy",
        "category": "descriptors",
        "synonyms": ["glad", "joyful"],
        "description": "Smile with hands"
    },
    "sad": {
        "word": "sad",
        "category": "descriptors",
        "synonyms": ["unhappy", "sorry"],
        "description": "Frown with hands"
    },
    "tired": {
        "word": "tired",
        "category": "descriptors",
        "synonyms": ["sleepy", "exhausted"],
        "description": "Rest head on hands"
    },
    "hungry": {
        "word": "hungry",
        "category": "descriptors",
        "synonyms": ["starving"],
        "description": "Hand to stomach"
    },
    "thirsty": {
        "word": "thirsty",
        "category": "descriptors",
        "synonyms": ["dry"],
        "description": "Hand to mouth like drinking"
    },

    # Questions
    "what": {
        "word": "what",
        "category": "questions",
        "synonyms": [],
        "description": "Index finger brushes across palm"
    },
    "where": {
        "word": "where",
        "category": "questions",
        "synonyms": [],
        "description": "Index finger waves side to side"
    },
    "when": {
        "word": "when",
        "category": "questions",
        "synonyms": [],
        "description": "Index finger circles then touches"
    },
    "why": {
        "word": "why",
        "category": "questions",
        "synonyms": [],
        "description": "Fingers touch forehead, pull to Y"
    },
    "how": {
        "word": "how",
        "category": "questions",
        "synonyms": [],
        "description": "Knuckles roll outward and open"
    },
    "who": {
        "word": "who",
        "category": "questions",
        "synonyms": [],
        "description": "Index finger circles at lips"
    },
    "which": {
        "word": "which",
        "category": "questions",
        "synonyms": ["what one"],
        "description": "Point between options"
    },

    # Numbers (basic)
    "one": {
        "word": "one",
        "category": "numbers",
        "synonyms": ["1"],
        "description": "Index finger up"
    },
    "two": {
        "word": "two",
        "category": "numbers",
        "synonyms": ["2"],
        "description": "Index and middle fingers up"
    },
    "three": {
        "word": "three",
        "category": "numbers",
        "synonyms": ["3"],
        "description": "Three fingers up"
    },
    "four": {
        "word": "four",
        "category": "numbers",
        "synonyms": ["4"],
        "description": "Four fingers up"
    },
    "five": {
        "word": "five",
        "category": "numbers",
        "synonyms": ["5"],
        "description": "Five fingers up"
    },
    "ten": {
        "word": "ten",
        "category": "numbers",
        "synonyms": ["10"],
        "description": "Cross fists"
    },

    # Colors
    "red": {
        "word": "red",
        "category": "colors",
        "synonyms": [],
        "description": "R hand waves"
    },
    "blue": {
        "word": "blue",
        "category": "colors",
        "synonyms": [],
        "description": "B hand waves"
    },
    "green": {
        "word": "green",
        "category": "colors",
        "synonyms": [],
        "description": "G hand waves"
    },
    "yellow": {
        "word": "yellow",
        "category": "colors",
        "synonyms": [],
        "description": "Y hand waves"
    },
    "black": {
        "word": "black",
        "category": "colors",
        "synonyms": ["dark"],
        "description": "Brush hair back"
    },
    "white": {
        "word": "white",
        "category": "colors",
        "synonyms": ["light"],
        "description": "Brush palm"
    },

    # Common phrases
    "i love you": {
        "word": "i love you",
        "category": "phrases",
        "synonyms": ["love you"],
        "description": "I-L-Y fingers"
    },
    "what's up": {
        "word": "what's up",
        "category": "phrases",
        "synonyms": ["sup", "how's it going"],
        "description": "Wiggle fingers up"
    },
    "see you later": {
        "word": "see you later",
        "category": "phrases",
        "synonyms": ["bye", "later"],
        "description": "Wave with both hands"
    },
    "take care": {
        "word": "take care",
        "category": "phrases",
        "synonyms": ["be careful"],
        "description": "Pat heart"
    },
    "excuse me": {
        "word": "excuse me",
        "category": "phrases",
        "synonyms": ["pardon"],
        "description": "Wave hand"
    },
    "i'm sorry": {
        "word": "i'm sorry",
        "category": "phrases",
        "synonyms": ["sorry", "my apologies"],
        "description": "Fist circles on chest"
    },
    "no problem": {
        "word": "no problem",
        "category": "phrases",
        "synonyms": ["that's fine", "okay"],
        "description": "Brush off shoulder"
    },
    "you're welcome": {
        "word": "you're welcome",
        "category": "phrases",
        "synonyms": ["welcome"],
        "description": "Open hands outward"
    }
}

def get_vocabulary_list():
    """Get list of all vocabulary words for Gemini prompt"""
    return list(SIGN_VOCABULARY.keys())

def local_match_signs(text):
    """Fallback local matching when Gemini is unavailable"""
    text_lower = text.lower()
    words = text_lower.replace(',', ' ').replace('.', ' ').replace('?', ' ').replace('!', ' ').split()
    matched_signs = []
    matched_words = set()
    
    # Check for multi-word phrases first
    for sign_word, sign_data in SIGN_VOCABULARY.items():
        if ' ' in sign_word and sign_word in text_lower and sign_word not in matched_words:
            matched_signs.append({
                **sign_data,
                "confidence": 1.0,
                "matched_from": sign_word
            })
            matched_words.add(sign_word)
    
    # Then check individual words and synonyms
    for word in words:
        if word in matched_words:
            continue
            
        # Direct match
        if word in SIGN_VOCABULARY:
            matched_signs.append({
                **SIGN_VOCABULARY[word],
                "confidence": 1.0,
                "matched_from": word
            })
            matched_words.add(word)
            continue
        
        # Synonym match
        for sign_word, sign_data in SIGN_VOCABULARY.items():
            if word in sign_data.get("synonyms", []):
                matched_signs.append({
                    **sign_data,
                    "confidence": 0.85,
                    "matched_from": word
                })
                matched_words.add(word)
                break
    
    # Finger-spell fallback for unmatched words: produce a single fingerspelled entry
    # containing the letters so the frontend can animate finger-spelling when needed.
    for word in words:
        # skip if already matched or empty
        if not word or word in matched_words:
            continue

        # keep only alphabetic characters for finger-spelling
        letters = [c for c in word if c.isalpha()]
        if not letters:
            continue

        matched_signs.append({
            "word": word,
            "category": "fingerspelled",
            "synonyms": [],
            "description": f"Finger-spell the word '{word}'",
            "letters": letters,
            "confidence": 0.5,
            "matched_from": word,
        })
        matched_words.add(word)

    return matched_signs

def gemini_match_signs(text):
    """Use Gemini API for intelligent sign matching"""
    if not GEMINI_API_KEY:
        return None, "No API key configured"
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        vocab_list = get_vocabulary_list()
        
        prompt = f"""You are an assistant that maps spoken text to sign language vocabulary.

Given the input text, identify which words from the available vocabulary should be used to represent the meaning.

Available vocabulary: {json.dumps(vocab_list)}

Input text: "{text}"

Rules:
1. Only return words that are in the available vocabulary list
2. Consider synonyms and semantic meaning (e.g., "I don't get it" should match "confused")
3. Return words in the order they should be signed
4. Include a confidence score (0.0-1.0) for each match
5. For words with no good match, skip them

Return a JSON array of objects with format:
[{{"word": "vocabulary_word", "confidence": 0.95, "matched_from": "original_word_or_phrase"}}]

Only return the JSON array, no other text."""

        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response - remove markdown code blocks if present
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            response_text = '\n'.join(lines[1:-1])
        
        matches = json.loads(response_text)
        
        # Enrich with full sign data
        enriched_matches = []
        for match in matches:
            word = match.get('word', '').lower()
            if word in SIGN_VOCABULARY:
                enriched_matches.append({
                    **SIGN_VOCABULARY[word],
                    "confidence": match.get('confidence', 0.8),
                    "matched_from": match.get('matched_from', word)
                })
        
        return enriched_matches, None
        
    except json.JSONDecodeError as e:
        return None, f"Failed to parse Gemini response: {str(e)}"
    except Exception as e:
        return None, f"Gemini API error: {str(e)}"

@app.route('/')
@app.route('/index')
@app.route('/index.html')
def index():
    return render_template('index.html')

@app.route('/api/match', methods=['POST'])
def match_signs():
    """Match input text to signs. Validates input and returns JSON with method used."""
    if not request.is_json:
        return jsonify(error="Expected JSON payload"), 400

    data = request.get_json()
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        return jsonify(signs=[], method="none", error="No text provided"), 400

    # Trim overly long input for safety
    text = text.strip()[:2000]
    use_ai = bool(data.get('use_ai', True))
    force_fingerspell = bool(data.get('force_fingerspell', False))

    # If the client requests forced fingerspelling, construct fingerspelled signs for each word
    if force_fingerspell:
        words = [w for w in re.sub(r"[^A-Za-z0-9\s]", " ", text).split() if w]
        signs = []
        for w in words:
            letters = [c for c in w if c.isalpha()]
            if not letters:
                continue
            signs.append({
                "word": w,
                "category": "fingerspelled",
                "synonyms": [],
                "description": f"Finger-spell the word '{w}'",
                "letters": letters,
                "confidence": 1.0,
                "matched_from": w,
            })

        try:
            add_video_urls_to_signs(signs)
        except Exception:
            logger.debug("Failed to enrich forced-fingerspell signs with videos")

        return jsonify(signs=signs, method="fingerspell", text=text)

    # Try Gemini if requested and configured
    if use_ai and GEMINI_API_KEY:
        signs, error = gemini_match_signs(text)
        if signs is None:
            logger.info("Gemini error, falling back to local: %s", error)
        else:
            # Enrich signs with available video URLs
            try:
                add_video_urls_to_signs(signs)
            except Exception:
                logger.debug("Failed to enrich signs with videos")
            return jsonify(signs=signs, method="gemini", text=text)

    # Local fallback
    signs = local_match_signs(text)
    try:
        add_video_urls_to_signs(signs)
    except Exception:
        logger.debug("Failed to enrich signs with videos")
    return jsonify(signs=signs, method="local", text=text)


def add_video_urls_to_signs(signs: List[Dict]):
    """Augment sign entries with `video_url` for gesture videos and
    `letter_videos` for fingerspelled entries when matching files exist
    in the local `videos/` folder.
    """
    if not os.path.isdir(VIDEOS_DIR):
        return

    # Map lowercase filename -> actual filename for lookup
    files = {fn.lower(): fn for fn in os.listdir(VIDEOS_DIR)}

    for sign in signs:
        word = str(sign.get("word", "")).strip()
        key = f"{word.lower()}.mp4"

        # Attach gesture/phrase video if available
        if key in files:
            sign["video_url"] = url_for("serve_video", filename=files[key])

        # For fingerspelled entries, attach per-letter videos when available
        if sign.get("category") == "fingerspelled":
            letters = sign.get("letters") or []
            letter_video_urls = []
            for ch in letters:
                if not ch or not str(ch).isalpha():
                    letter_video_urls.append(None)
                    continue
                candidate = f"{str(ch).lower()}.mp4"
                if candidate in files:
                    letter_video_urls.append(url_for("serve_video", filename=files[candidate]))
                else:
                    letter_video_urls.append(None)

            if any(letter_video_urls):
                sign["letter_videos"] = letter_video_urls


@app.route('/videos/<path:filename>')
def serve_video(filename: str):
    """Serve video files from the workspace `videos` folder."""
    # send_from_directory handles safe path joining
    return send_from_directory(VIDEOS_DIR, filename)

# Apply rate limit to the match endpoint if limiter is configured
if 'limiter' in globals() and limiter:
    match_signs = limiter.limit("120/minute")(match_signs)

@app.route('/api/vocabulary')
def get_vocabulary():
    """Return vocabulary; optional '?category=' filters results."""
    category = request.args.get('category')
    categories = sorted({s["category"] for s in SIGN_VOCABULARY.values()})
    if category:
        filtered = {k: v for k, v in SIGN_VOCABULARY.items() if v.get('category') == category}
        return jsonify(vocabulary=filtered, categories=categories, count=len(filtered))
    return jsonify(vocabulary=SIGN_VOCABULARY, categories=categories, count=len(SIGN_VOCABULARY))


@app.route('/api/vocabulary/<word>')
def get_vocabulary_item(word: str):
    """Return a single vocabulary entry by word (case-insensitive)."""
    key = word.lower()
    item = SIGN_VOCABULARY.get(key)
    if not item:
        return jsonify(error="Not found"), 404
    return jsonify(word=key, data=item)

@app.route('/api/status')
def get_status():
    """Health/status endpoint."""
    return jsonify({
        "gemini_configured": bool(GEMINI_API_KEY),
        "vocabulary_count": len(SIGN_VOCABULARY)
    })


# Error handlers for consistent JSON responses
@app.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled exception: %s", e)
    return jsonify(error="Internal Server Error"), 500


# Basic security headers
@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    # Minimal CSP - allow same origin scripts/styles only
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
    return response

if __name__ == '__main__':
    logger.info("Starting Speech-to-Sign Aid")
    if GEMINI_API_KEY:
        logger.info("✓ Gemini API configured")
    else:
        logger.warning("⚠ No GEMINI_API_KEY found - using local matching only")
        logger.info("Set environment variable: set GEMINI_API_KEY=your_key (Windows) or export GEMINI_API_KEY=your_key")

    logger.info("✓ Loaded %d signs", len(SIGN_VOCABULARY))

    try:
        app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
    except KeyboardInterrupt:
        logger.info("Shutdown requested, exiting")
