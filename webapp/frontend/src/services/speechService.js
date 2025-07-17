/**
 * Speech Service - Handles Speech-to-Text and Text-to-Speech
 * Provides cheap, browser-native voice capabilities for AI chat
 */

class SpeechService {
  constructor() {
    this.isSupported = this.checkSupport();
    this.recognition = null;
    this.synthesis = window.speechSynthesis;
    this.voices = [];
    this.currentVoice = null;
    this.isListening = false;
    this.isSpeaking = false;
    
    // Settings
    this.settings = {
      language: 'en-US',
      rate: 1.0,
      pitch: 1.0,
      volume: 0.8,
      continuous: false,
      interimResults: true
    };

    // Callbacks
    this.onResult = null;
    this.onError = null;
    this.onStart = null;
    this.onEnd = null;
    this.onSpeechStart = null;
    this.onSpeechEnd = null;

    this.init();
  }

  checkSupport() {
    const hasSpeechRecognition = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
    const hasSpeechSynthesis = 'speechSynthesis' in window;
    
    return {
      speechToText: hasSpeechRecognition,
      textToSpeech: hasSpeechSynthesis,
      fullSupport: hasSpeechRecognition && hasSpeechSynthesis
    };
  }

  init() {
    if (this.isSupported.speechToText) {
      this.setupSpeechRecognition();
    }
    
    if (this.isSupported.textToSpeech) {
      this.setupSpeechSynthesis();
    }
  }

  setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.recognition = new SpeechRecognition();
    
    this.recognition.continuous = this.settings.continuous;
    this.recognition.interimResults = this.settings.interimResults;
    this.recognition.lang = this.settings.language;
    this.recognition.maxAlternatives = 1;

    this.recognition.onstart = () => {
      this.isListening = true;
      console.log('🎤 Speech recognition started');
      if (this.onStart) this.onStart();
    };

    this.recognition.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript && this.onResult) {
        console.log('🎤 Final transcript:', finalTranscript);
        this.onResult(finalTranscript, interimTranscript);
      }
    };

    this.recognition.onerror = (event) => {
      console.error('🎤 Speech recognition error:', event.error);
      this.isListening = false;
      
      const errorMessage = this.getErrorMessage(event.error);
      if (this.onError) this.onError(errorMessage, event.error);
    };

    this.recognition.onend = () => {
      this.isListening = false;
      console.log('🎤 Speech recognition ended');
      if (this.onEnd) this.onEnd();
    };
  }

  setupSpeechSynthesis() {
    // Load voices when they become available
    const loadVoices = () => {
      this.voices = this.synthesis.getVoices();
      
      // Find a good default English voice
      this.currentVoice = this.voices.find(voice => 
        voice.lang.startsWith('en') && voice.localService
      ) || this.voices.find(voice => 
        voice.lang.startsWith('en')
      ) || this.voices[0];

      console.log('🔊 Available voices:', this.voices.length);
      console.log('🔊 Selected voice:', this.currentVoice?.name);
    };

    // Voices might load asynchronously
    if (this.synthesis.getVoices().length === 0) {
      this.synthesis.onvoiceschanged = loadVoices;
    } else {
      loadVoices();
    }
  }

  // Speech-to-Text Methods
  startListening(options = {}) {
    if (!this.isSupported.speechToText) {
      throw new Error('Speech recognition not supported in this browser');
    }

    if (this.isListening) {
      console.warn('🎤 Already listening');
      return;
    }

    // Apply any option overrides
    if (options.language) this.recognition.lang = options.language;
    if (options.continuous !== undefined) this.recognition.continuous = options.continuous;
    if (options.interimResults !== undefined) this.recognition.interimResults = options.interimResults;

    try {
      this.recognition.start();
    } catch (error) {
      console.error('🎤 Failed to start speech recognition:', error);
      if (this.onError) this.onError('Failed to start microphone', error);
    }
  }

  stopListening() {
    if (this.recognition && this.isListening) {
      this.recognition.stop();
    }
  }

  // Text-to-Speech Methods
  speak(text, options = {}) {
    if (!this.isSupported.textToSpeech) {
      throw new Error('Speech synthesis not supported in this browser');
    }

    if (!text || !text.trim()) {
      console.warn('🔊 No text to speak');
      return;
    }

    // Stop any current speech
    this.stopSpeaking();

    const utterance = new SpeechSynthesisUtterance(text.trim());
    
    // Apply voice settings
    utterance.voice = options.voice || this.currentVoice;
    utterance.rate = options.rate || this.settings.rate;
    utterance.pitch = options.pitch || this.settings.pitch;
    utterance.volume = options.volume || this.settings.volume;
    utterance.lang = options.language || this.settings.language;

    utterance.onstart = () => {
      this.isSpeaking = true;
      console.log('🔊 Speech synthesis started');
      if (this.onSpeechStart) this.onSpeechStart();
    };

    utterance.onend = () => {
      this.isSpeaking = false;
      console.log('🔊 Speech synthesis ended');
      if (this.onSpeechEnd) this.onSpeechEnd();
    };

    utterance.onerror = (event) => {
      this.isSpeaking = false;
      console.error('🔊 Speech synthesis error:', event.error);
      if (this.onError) this.onError('Speech playback failed', event.error);
    };

    console.log('🔊 Speaking:', text.substring(0, 50) + '...');
    this.synthesis.speak(utterance);
  }

  stopSpeaking() {
    if (this.synthesis.speaking) {
      this.synthesis.cancel();
      this.isSpeaking = false;
    }
  }

  // Utility Methods
  getErrorMessage(errorCode) {
    const errorMessages = {
      'no-speech': 'No speech detected. Please try again.',
      'audio-capture': 'Microphone not accessible. Please check permissions.',
      'not-allowed': 'Microphone access denied. Please enable microphone permissions.',
      'network': 'Network error. Please check your connection.',
      'service-not-allowed': 'Speech service not allowed.',
      'bad-grammar': 'Speech recognition error.',
      'language-not-supported': 'Language not supported.',
      'aborted': 'Speech recognition was aborted.'
    };

    return errorMessages[errorCode] || 'Speech recognition error occurred.';
  }

  getAvailableVoices() {
    return this.voices.map(voice => ({
      name: voice.name,
      language: voice.lang,
      localService: voice.localService,
      gender: voice.name.toLowerCase().includes('female') ? 'female' : 'male'
    }));
  }

  setVoice(voiceName) {
    const voice = this.voices.find(v => v.name === voiceName);
    if (voice) {
      this.currentVoice = voice;
      console.log('🔊 Voice changed to:', voice.name);
    }
  }

  updateSettings(newSettings) {
    this.settings = { ...this.settings, ...newSettings };
    
    if (this.recognition) {
      this.recognition.lang = this.settings.language;
      this.recognition.continuous = this.settings.continuous;
      this.recognition.interimResults = this.settings.interimResults;
    }
  }

  // Event Handlers
  setCallbacks(callbacks) {
    this.onResult = callbacks.onResult;
    this.onError = callbacks.onError;
    this.onStart = callbacks.onStart;
    this.onEnd = callbacks.onEnd;
    this.onSpeechStart = callbacks.onSpeechStart;
    this.onSpeechEnd = callbacks.onSpeechEnd;
  }

  // Status Methods
  isRecognitionSupported() {
    return this.isSupported.speechToText;
  }

  isSynthesisSupported() {
    return this.isSupported.textToSpeech;
  }

  isCurrentlyListening() {
    return this.isListening;
  }

  isCurrentlySpeaking() {
    return this.isSpeaking;
  }

  getSupportStatus() {
    return {
      ...this.isSupported,
      userAgent: navigator.userAgent,
      recommendedBrowser: 'Chrome or Edge for best compatibility'
    };
  }
}

// Create singleton instance
const speechService = new SpeechService();

export default speechService;
export { SpeechService };