/**
 * Speech-to-Sign Aid MVP
 * Client-side JavaScript with Web Speech API and Gemini backend
 */

// State
let isListening = false
let recognition = null
let preferences = loadPreferences()
let useAI = true
let currentProcessingText = ""
let hasSeenWelcome = localStorage.getItem("signaid-welcome-seen") === "true"

// DOM Elements
const elements = {
  // Header
  aiToggle: document.getElementById("ai-toggle"),
  settingsBtn: document.getElementById("settings-btn"),

  // Stats
  statusDot: document.querySelector(".status-dot"),
  statusText: document.getElementById("status-text"),
  methodIndicator: document.getElementById("method-indicator"),
  latencyIndicator: document.getElementById("latency-indicator"),
  matchCount: document.getElementById("match-count"),

  // Input
  tabBtns: document.querySelectorAll(".tab-btn"),
  speechPanel: document.getElementById("speech-panel"),
  textPanel: document.getElementById("text-panel"),
  micBtn: document.getElementById("mic-btn"),
  micHint: document.getElementById("mic-hint"),
  transcript: document.getElementById("transcript"),
  textInput: document.getElementById("text-input"),
  processBtn: document.getElementById("process-btn"),

  // Sign Display
  emptyState: document.getElementById("empty-state"),
  signsGrid: document.getElementById("signs-grid"),

  // Settings Modal
  settingsModal: document.getElementById("settings-modal"),
  closeSettings: document.getElementById("close-settings"),
  signSize: document.getElementById("sign-size"),
  sizeValue: document.getElementById("size-value"),
  animationSpeed: document.getElementById("animation-speed"),
  speedValue: document.getElementById("speed-value"),
  highContrast: document.getElementById("high-contrast"),
  showDescriptions: document.getElementById("show-descriptions"),
  resetSettings: document.getElementById("reset-settings"),
  saveSettings: document.getElementById("save-settings"),

  // Vocabulary
  vocabToggle: document.getElementById("vocab-toggle"),
  vocabContent: document.getElementById("vocab-content"),
  vocabGrid: document.getElementById("vocab-grid"),

  // Welcome Modal
  welcomeModal: document.getElementById("welcome-modal"),
  closeWelcome: document.getElementById("close-welcome"),
  getStartedBtn: document.getElementById("get-started-btn"),

  // Loading & Error States
  loadingState: document.getElementById("loading-state"),
  skeletonGrid: document.getElementById("skeleton-grid"),
  errorState: document.getElementById("error-state"),
  errorTitle: document.getElementById("error-title"),
  errorMessage: document.getElementById("error-message"),
  retryBtn: document.getElementById("retry-btn"),

  // Examples
  tryExampleBtn: document.getElementById("try-example-btn"),
  quickExamples: document.getElementById("quick-examples"),
}

// Initialize
document.addEventListener("DOMContentLoaded", init)

function init() {
  setupSpeechRecognition()
  setupEventListeners()
  applyPreferences()
  loadVocabulary()
  checkAPIStatus()
  
  // Show welcome modal if first visit
  setTimeout(() => {
    if (!hasSeenWelcome) {
      elements.welcomeModal.classList.remove("hidden")
    }
  }, 300)
}

// Preferences
function loadPreferences() {
  const defaults = {
    signSize: 160,
    animationSpeed: 1,
    highContrast: false,
    showDescriptions: true,
  }

  try {
    const saved = localStorage.getItem("signaid-preferences")
    return saved ? { ...defaults, ...JSON.parse(saved) } : defaults
  } catch {
    return defaults
  }
}

function savePreferences() {
  localStorage.setItem("signaid-preferences", JSON.stringify(preferences))
}

function applyPreferences() {
  document.documentElement.style.setProperty("--sign-size", `${preferences.signSize}px`)
  document.documentElement.style.setProperty("--animation-speed", preferences.animationSpeed)

  if (preferences.highContrast) {
    document.body.classList.add("high-contrast")
  } else {
    document.body.classList.remove("high-contrast")
  }

  // Update form controls
  elements.signSize.value = preferences.signSize
  elements.sizeValue.textContent = `${preferences.signSize}px`
  elements.animationSpeed.value = preferences.animationSpeed
  elements.speedValue.textContent = `${preferences.animationSpeed}x`
  elements.highContrast.checked = preferences.highContrast
  elements.showDescriptions.checked = preferences.showDescriptions
}

// Speech Recognition
function setupSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition

  if (!SpeechRecognition) {
    elements.micBtn.disabled = true
    elements.micHint.textContent = "Speech recognition not supported in this browser"
    return
  }

  recognition = new SpeechRecognition()
  recognition.continuous = true
  recognition.interimResults = true
  recognition.lang = "en-US"

  recognition.onstart = () => {
    isListening = true
    updateListeningState()
  }

  recognition.onend = () => {
    isListening = false
    updateListeningState()

    // Auto-restart if still supposed to be listening
    if (elements.micBtn.classList.contains("listening")) {
      try {
        recognition.start()
      } catch (e) {
        console.log("Could not restart recognition")
      }
    }
  }

  recognition.onresult = (event) => {
    let interimTranscript = ""
    let finalTranscript = ""

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript
      if (event.results[i].isFinal) {
        finalTranscript += transcript
      } else {
        interimTranscript += transcript
      }
    }

    // Display transcript
    elements.transcript.textContent = finalTranscript || interimTranscript

    // Process final transcript
    if (finalTranscript) {
      processText(finalTranscript)
    }
  }

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error)
    if (event.error !== "no-speech") {
      setStatus("error", `Error: ${event.error}`)
    }
  }
}

function updateListeningState() {
  if (isListening) {
    elements.micBtn.classList.add("listening")
    elements.micHint.textContent = "Listening... Click to stop"
    elements.statusDot.classList.add("listening")
    setStatus("listening", "Listening")
  } else {
    elements.micBtn.classList.remove("listening")
    elements.micHint.textContent = "Click to start listening"
    elements.statusDot.classList.remove("listening")
    setStatus("ready", "Ready")
  }
}

function toggleListening() {
  if (!recognition) return

  if (isListening) {
    recognition.stop()
    elements.micBtn.classList.remove("listening")
  } else {
    try {
      recognition.start()
      elements.micBtn.classList.add("listening")
    } catch (e) {
      console.error("Could not start recognition:", e)
    }
  }
}

// Text Processing
async function processText(text) {
  if (!text.trim()) return

  currentProcessingText = text.trim()
  const startTime = performance.now()
  setStatus("processing", "Processing...")
  
  // Hide error state and show loading
  hideErrorState()
  showLoadingState()

  try {
    const response = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: currentProcessingText,
        use_ai: useAI,
      }),
    })

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`)
    }

    const data = await response.json()
    const latency = Math.round(performance.now() - startTime)

    hideLoadingState()
    displaySigns(data.signs)
    updateStats(data.method, latency, data.signs.length)
    setStatus("ready", "Ready")
  } catch (error) {
    console.error("Error processing text:", error)
    hideLoadingState()
    
    let errorMsg = "Unable to process your request."
    let errorTitle = "Processing Failed"
    
    if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError")) {
      errorTitle = "Connection Error"
      errorMsg = "Could not connect to the server. Please check your internet connection and try again."
    } else if (error.message.includes("Server error")) {
      errorTitle = "Server Error"
      errorMsg = "The server encountered an error. Please try again in a moment."
    } else if (error.message) {
      errorMsg = error.message
    }
    
    showErrorState(errorTitle, errorMsg)
    setStatus("error", "Error")
  }
}

// Display Signs
function displaySigns(signs) {
  if (!signs || signs.length === 0) {
    elements.signsGrid.innerHTML = ""
    elements.emptyState.classList.remove("hidden")
    elements.signsGrid.classList.add("hidden")
    hideLoadingState()
    return
  }

  showSignsGrid()
  hideLoadingState()

  elements.signsGrid.innerHTML = signs
    .map(
      (sign, index) => `
        <div class="sign-card" style="--index: ${index};">
            <div class="sign-animation">
                ${getSignVisualization(sign)}
            </div>
            <div class="sign-word">${sign.word}</div>
            <div class="sign-category">${sign.category}</div>
            ${preferences.showDescriptions ? `<div class="sign-description">${sign.description}</div>` : ""}
            <div class="sign-confidence">${Math.round(sign.confidence * 100)}% match</div>
        </div>
    `,
    )
    .join("")
}

// Loading States
function showLoadingState() {
  elements.emptyState.classList.add("hidden")
  elements.errorState.classList.add("hidden")
  elements.signsGrid.classList.add("hidden")
  elements.loadingState.classList.remove("hidden")
  
  // Generate skeleton loaders
  const skeletonCount = 6
  elements.skeletonGrid.innerHTML = Array.from({ length: skeletonCount }, (_, i) => `
    <div class="skeleton-card" style="--index: ${i};">
      <div class="skeleton-animation"></div>
      <div class="skeleton-line skeleton-title"></div>
      <div class="skeleton-line skeleton-category"></div>
      <div class="skeleton-line skeleton-description"></div>
    </div>
  `).join("")
}

function hideLoadingState() {
  elements.loadingState.classList.add("hidden")
}

// Error States
function showErrorState(title, message) {
  elements.emptyState.classList.add("hidden")
  elements.loadingState.classList.add("hidden")
  elements.signsGrid.classList.add("hidden")
  elements.errorState.classList.remove("hidden")
  elements.errorTitle.textContent = title
  elements.errorMessage.textContent = message
}

function hideErrorState() {
  elements.errorState.classList.add("hidden")
}

function showSignsGrid() {
  elements.emptyState.classList.add("hidden")
  elements.signsGrid.classList.remove("hidden")
}

function getSignVisualization(sign) {
  // Enhanced sign visualization - structure ready for videos/GIFs
  // For now, using improved animated SVG placeholders
  const word = sign.word.toLowerCase()
  const category = sign.category?.toLowerCase() || ""
  
  // Fingerspelling: if the backend returned a letters array, render that animation
  if (sign.letters && Array.isArray(sign.letters) && sign.letters.length > 0) {
    return getFingerspellVisualization(sign.letters, preferences.animationSpeed)
  }

  // Check if we have a video/GIF path (would come from backend)
  if (sign.video_url) {
    return `<video class="sign-video" autoplay loop muted playsinline>
      <source src="${sign.video_url}" type="video/mp4">
    </video>`
  }
  
  if (sign.gif_url) {
    return `<img class="sign-gif" src="${sign.gif_url}" alt="${sign.word} sign" />`
  }
  
  // Fallback to animated SVG based on category/word
  return getAnimatedSignSVG(word, category)
} 

function getAnimatedSignSVG(word, category) {
  // More detailed hand/gesture SVGs with animation potential
  const signIcons = {
    hello: `<svg class="sign-svg" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="2">
      <g class="hand-animation">
        <path d="M30 40 L50 20 L70 40" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M40 50 L50 40 L60 50" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="50" cy="50" r="8" fill="currentColor" opacity="0.3"/>
        <path d="M30 60 Q50 70 70 60" stroke-linecap="round"/>
      </g>
    </svg>`,
    thank: `<svg class="sign-svg" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="2">
      <g class="hand-animation">
        <path d="M50 20 L50 60" stroke-linecap="round"/>
        <path d="M30 50 Q50 40 70 50" stroke-linecap="round"/>
        <circle cx="50" cy="30" r="6" fill="currentColor" opacity="0.3"/>
      </g>
    </svg>`,
    default: `<svg class="sign-svg" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="2">
      <g class="hand-animation">
        <circle cx="50" cy="50" r="30" opacity="0.2"/>
        <path d="M35 50 L50 35 L65 50" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M50 50 L50 70" stroke-linecap="round"/>
        <circle cx="50" cy="50" r="8" fill="currentColor" opacity="0.4"/>
      </g>
    </svg>`
  }
  
  // Match by word or category
  if (word.includes("hello") || word.includes("hi")) return signIcons.hello
  if (word.includes("thank")) return signIcons.thank
  
  return signIcons.default
}

function getFingerspellVisualization(letters, speed) {
  // speed >1 is faster, <1 is slower. We'll use it to compute delays/duration.
  const baseDelay = 0.25 // seconds per letter at 1x
  const delayPer = baseDelay / Math.max(0.1, speed)
  const totalDuration = letters.length * delayPer

  const letterHtml = letters
    .map((ch, i) => `
      <div class="fs-letter" aria-hidden="true" style="animation-delay: ${(
        i * delayPer
      ).toFixed(2)}s">${String(ch).toUpperCase()}</div>
    `)
    .join("")

  return `<div class="fingerspell" role="img" aria-label="Finger-spelled word">
      <div class="fs-letters" style="--fs-duration: ${totalDuration}s">${letterHtml}</div>
    </div>`
}

// Stats & Status
function setStatus(type, text) {
  elements.statusText.textContent = text
  elements.statusDot.className = "status-dot"

  if (type === "listening") {
    elements.statusDot.classList.add("listening")
  } else if (type === "processing") {
    elements.statusDot.classList.add("processing")
  } else if (type === "error") {
    elements.statusDot.classList.add("error")
  }
}

function updateStats(method, latency, count) {
  elements.methodIndicator.textContent = method === "gemini" ? "Gemini AI" : "Local"
  elements.latencyIndicator.textContent = `${latency}ms`
  elements.matchCount.textContent = count
}

// Vocabulary
async function loadVocabulary() {
  try {
    const response = await fetch("/api/vocabulary")
    const data = await response.json()

    elements.vocabGrid.innerHTML = Object.keys(data.vocabulary)
      .sort()
      .map((word) => `<div class="vocab-item">${word}</div>`)
      .join("")
  } catch (error) {
    console.error("Could not load vocabulary:", error)
    elements.vocabGrid.innerHTML = '<div class="vocab-item">Could not load vocabulary</div>'
  }
}

// API Status
async function checkAPIStatus() {
  try {
    const response = await fetch("/api/status")
    const data = await response.json()

    if (!data.gemini_configured) {
      elements.aiToggle.checked = false
      elements.aiToggle.disabled = true
      elements.methodIndicator.textContent = "Local only"
      useAI = false
    }
  } catch (error) {
    console.error("Could not check API status:", error)
  }
}

// Event Listeners
function setupEventListeners() {
  // AI Toggle
  elements.aiToggle.addEventListener("change", (e) => {
    useAI = e.target.checked
  })

  // Tab switching
  elements.tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode

      elements.tabBtns.forEach((b) => b.classList.remove("active"))
      btn.classList.add("active")

      if (mode === "speech") {
        elements.speechPanel.classList.remove("hidden")
        elements.textPanel.classList.add("hidden")
      } else {
        elements.speechPanel.classList.add("hidden")
        elements.textPanel.classList.remove("hidden")

        // Stop listening when switching to text mode
        if (isListening && recognition) {
          recognition.stop()
          elements.micBtn.classList.remove("listening")
        }
      }
    })
  })

  // Microphone
  elements.micBtn.addEventListener("click", toggleListening)

  // Text input
  elements.processBtn.addEventListener("click", () => {
    const text = elements.textInput.value.trim()
    if (text) {
      elements.transcript.textContent = text
      processText(text)
    }
  })

  elements.textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      elements.processBtn.click()
    }
  })

  // Settings
  elements.settingsBtn.addEventListener("click", () => {
    elements.settingsModal.classList.remove("hidden")
  })

  elements.closeSettings.addEventListener("click", () => {
    elements.settingsModal.classList.add("hidden")
  })

  elements.settingsModal.addEventListener("click", (e) => {
    if (e.target === elements.settingsModal) {
      elements.settingsModal.classList.add("hidden")
    }
  })

  elements.signSize.addEventListener("input", (e) => {
    elements.sizeValue.textContent = `${e.target.value}px`
  })

  elements.animationSpeed.addEventListener("input", (e) => {
    elements.speedValue.textContent = `${e.target.value}x`
  })

  elements.resetSettings.addEventListener("click", () => {
    preferences = loadPreferences()
    applyPreferences()
  })

  elements.saveSettings.addEventListener("click", () => {
    preferences.signSize = Number.parseInt(elements.signSize.value)
    preferences.animationSpeed = Number.parseFloat(elements.animationSpeed.value)
    preferences.highContrast = elements.highContrast.checked
    preferences.showDescriptions = elements.showDescriptions.checked

    savePreferences()
    applyPreferences()
    elements.settingsModal.classList.add("hidden")
  })

  // Vocabulary panel
  elements.vocabToggle.addEventListener("click", () => {
    const isExpanded = elements.vocabToggle.getAttribute("aria-expanded") === "true"
    elements.vocabToggle.setAttribute("aria-expanded", !isExpanded)
    elements.vocabContent.classList.toggle("hidden")
  })

  // Welcome Modal
  elements.closeWelcome.addEventListener("click", closeWelcomeModal)
  elements.getStartedBtn.addEventListener("click", closeWelcomeModal)
  elements.welcomeModal.addEventListener("click", (e) => {
    if (e.target === elements.welcomeModal) {
      closeWelcomeModal()
    }
  })

  // Example buttons in welcome modal
  document.querySelectorAll(".example-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const text = btn.dataset.text
      closeWelcomeModal()
      setTimeout(() => {
        elements.textInput.value = text
        elements.transcript.textContent = text
        processText(text)
      }, 300)
    })
  })

  // Quick examples in empty state
  document.querySelectorAll(".example-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.dataset.text
      elements.textInput.value = text
      elements.transcript.textContent = text
      processText(text)
    })
  })

  // Try example button
  elements.tryExampleBtn.addEventListener("click", () => {
    const examples = [
      "Hello, how are you today?",
      "Thank you very much",
      "Nice to meet you",
      "I need help",
      "Where is the bathroom?",
      "Have a great day"
    ]
    const randomExample = examples[Math.floor(Math.random() * examples.length)]
    elements.textInput.value = randomExample
    elements.transcript.textContent = randomExample
    processText(randomExample)
  })

  // Retry button
  elements.retryBtn.addEventListener("click", () => {
    if (currentProcessingText) {
      processText(currentProcessingText)
    }
  })
}

function closeWelcomeModal() {
  elements.welcomeModal.classList.add("hidden")
  localStorage.setItem("signaid-welcome-seen", "true")
  hasSeenWelcome = true
}
