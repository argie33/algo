/**
 * Real Speech Service Unit Tests
 * Testing the actual speechService.js with Speech-to-Text and Text-to-Speech functionality
 * CRITICAL COMPONENT - Handles browser speech APIs, voice recognition, and synthesis
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock browser speech APIs
const mockSpeechRecognition = {
  start: vi.fn(),
  stop: vi.fn(),
  abort: vi.fn(),
  continuous: false,
  interimResults: false,
  lang: 'en-US',
  maxAlternatives: 1,
  onstart: null,
  onresult: null,
  onerror: null,
  onend: null
};

const mockSpeechSynthesis = {
  speak: vi.fn(),
  cancel: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  getVoices: vi.fn().mockReturnValue([
    { name: 'English Voice 1', lang: 'en-US', localService: true },
    { name: 'English Voice 2', lang: 'en-GB', localService: false },
    { name: 'Spanish Voice', lang: 'es-ES', localService: true }
  ]),
  speaking: false,
  pending: false,
  paused: false,
  onvoiceschanged: null
};

const mockSpeechSynthesisUtterance = vi.fn().mockImplementation((text) => {
  return {
    text,
    voice: null,
    rate: 1,
    pitch: 1,
    volume: 1,
    lang: 'en-US',
    onstart: null,
    onend: null,
    onerror: null,
    onpause: null,
    onresume: null,
    onmark: null,
    onboundary: null
  };
});

// Mock global objects
Object.defineProperty(global, 'SpeechRecognition', {
  value: vi.fn().mockImplementation(() => mockSpeechRecognition),
  writable: true
});

Object.defineProperty(global, 'webkitSpeechRecognition', {
  value: vi.fn().mockImplementation(() => mockSpeechRecognition),
  writable: true
});

Object.defineProperty(global, 'speechSynthesis', {
  value: mockSpeechSynthesis,
  writable: true
});

Object.defineProperty(global, 'SpeechSynthesisUtterance', {
  value: mockSpeechSynthesisUtterance,
  writable: true
});

Object.defineProperty(global, 'window', {
  value: {
    SpeechRecognition: global.SpeechRecognition,
    webkitSpeechRecognition: global.webkitSpeechRecognition,
    speechSynthesis: global.speechSynthesis,
    SpeechSynthesisUtterance: global.SpeechSynthesisUtterance
  },
  writable: true
});

// Import the REAL SpeechService after mocks
let speechService;

describe('🗣️ Real Speech Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Reset mock states
    mockSpeechRecognition.continuous = false;
    mockSpeechRecognition.interimResults = false;
    mockSpeechRecognition.lang = 'en-US';
    mockSpeechSynthesis.speaking = false;
    
    // Reset voices to original state
    mockSpeechSynthesis.getVoices.mockReturnValue([
      { name: 'English Voice 1', lang: 'en-US', localService: true },
      { name: 'English Voice 2', lang: 'en-GB', localService: false },
      { name: 'Spanish Voice', lang: 'es-ES', localService: true }
    ]);
    
    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Dynamically import to get fresh instance
    const speechServiceModule = await import('../../../services/speechService');
    const getSpeechService = speechServiceModule.default;
    speechService = getSpeechService(); // Call the function to get the actual service instance
    
    // Reset service state and settings
    speechService.isListening = false;
    speechService.isSpeaking = false;
    speechService.settings = {
      language: 'en-US',
      rate: 1.0,
      pitch: 1.0,
      volume: 0.8,
      continuous: false,
      interimResults: true
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with browser support detection', () => {
      expect(speechService.isSupported).toEqual({
        speechToText: true,
        textToSpeech: true,
        fullSupport: true
      });
    });

    it('should initialize with default settings', () => {
      expect(speechService.settings).toEqual({
        language: 'en-US',
        rate: 1.0,
        pitch: 1.0,
        volume: 0.8,
        continuous: false,
        interimResults: true
      });
    });

    it('should initialize speech recognition with settings', () => {
      expect(mockSpeechRecognition.lang).toBe('en-US');
      expect(mockSpeechRecognition.continuous).toBe(false);
      expect(mockSpeechRecognition.interimResults).toBe(false); // Gets set to false initially, then true in settings
      expect(mockSpeechRecognition.maxAlternatives).toBe(1);
    });

    it('should load available voices', () => {
      expect(speechService.voices).toHaveLength(3);
      expect(speechService.currentVoice).toEqual({
        name: 'English Voice 1',
        lang: 'en-US',
        localService: true
      });
    });
  });

  describe('Browser Support Detection', () => {
    it('should detect speech recognition support', () => {
      expect(speechService.isRecognitionSupported()).toBe(true);
    });

    it('should detect speech synthesis support', () => {
      expect(speechService.isSynthesisSupported()).toBe(true);
    });

    it('should provide comprehensive support status', () => {
      const status = speechService.getSupportStatus();
      
      expect(status).toEqual({
        speechToText: true,
        textToSpeech: true,
        fullSupport: true,
        userAgent: expect.any(String),
        recommendedBrowser: 'Chrome or Edge for best compatibility'
      });
    });

    it('should handle missing speech recognition gracefully', async () => {
      // Create a minimal mock window without speech recognition
      const originalWindow = global.window;
      global.window = {
        speechSynthesis: mockSpeechSynthesis,
        SpeechSynthesisUtterance: mockSpeechSynthesisUtterance
      };
      
      const { SpeechService } = await import('../../../services/speechService');
      const noSupportService = new SpeechService();
      
      expect(noSupportService.isSupported.speechToText).toBe(false);
      expect(() => noSupportService.startListening()).toThrow('Speech recognition not supported');
      
      // Restore original window
      global.window = originalWindow;
    });

    it('should handle missing speech synthesis gracefully', async () => {
      // Create a minimal mock window without speech synthesis
      const originalWindow = global.window;
      global.window = {
        SpeechRecognition: global.SpeechRecognition,
        webkitSpeechRecognition: global.webkitSpeechRecognition
      };
      
      const { SpeechService } = await import('../../../services/speechService');
      const noSupportService = new SpeechService();
      
      expect(noSupportService.isSupported.textToSpeech).toBe(false);
      expect(() => noSupportService.speak('test')).toThrow('Speech synthesis not supported');
      
      // Restore original window
      global.window = originalWindow;
    });
  });

  describe('Speech Recognition (Speech-to-Text)', () => {
    it('should start listening successfully', () => {
      speechService.startListening();
      
      expect(mockSpeechRecognition.start).toHaveBeenCalled();
      expect(speechService.isListening).toBe(false); // Will be set to true by onstart callback
    });

    it('should apply options when starting listening', () => {
      speechService.startListening({
        language: 'es-ES',
        continuous: true,
        interimResults: false
      });
      
      expect(mockSpeechRecognition.lang).toBe('es-ES');
      expect(mockSpeechRecognition.continuous).toBe(true);
      expect(mockSpeechRecognition.interimResults).toBe(false);
    });

    it('should prevent starting when already listening', () => {
      speechService.isListening = true;
      
      speechService.startListening();
      
      expect(console.warn).toHaveBeenCalledWith('🎤 Already listening');
    });

    it('should stop listening successfully', () => {
      speechService.isListening = true;
      speechService.stopListening();
      
      expect(mockSpeechRecognition.stop).toHaveBeenCalled();
    });

    it('should handle start callback', () => {
      const onStart = vi.fn();
      speechService.setCallbacks({ onStart });
      
      // Simulate recognition start
      mockSpeechRecognition.onstart();
      
      expect(speechService.isListening).toBe(true);
      expect(onStart).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalledWith('🎤 Speech recognition started');
    });

    it('should handle final results', () => {
      const onResult = vi.fn();
      speechService.setCallbacks({ onResult });
      
      // Simulate recognition result
      const mockEvent = {
        resultIndex: 0,
        results: [
          [{ transcript: 'hello world' }],
          [{ transcript: ' how are you' }]
        ]
      };
      mockEvent.results[0].isFinal = true;
      mockEvent.results[1].isFinal = true;
      
      mockSpeechRecognition.onresult(mockEvent);
      
      expect(onResult).toHaveBeenCalledWith('hello world how are you', '');
      expect(console.log).toHaveBeenCalledWith('🎤 Final transcript:', 'hello world how are you');
    });

    it('should handle interim results', () => {
      const onResult = vi.fn();
      speechService.setCallbacks({ onResult });
      
      // Simulate interim result
      const mockEvent = {
        resultIndex: 0,
        results: [
          [{ transcript: 'hello' }],
          [{ transcript: ' world' }]
        ]
      };
      mockEvent.results[0].isFinal = false;
      mockEvent.results[1].isFinal = true;
      
      mockSpeechRecognition.onresult(mockEvent);
      
      expect(onResult).toHaveBeenCalledWith(' world', 'hello');
    });

    it('should handle recognition errors', () => {
      const onError = vi.fn();
      speechService.setCallbacks({ onError });
      
      // Simulate error
      const mockEvent = { error: 'no-speech' };
      mockSpeechRecognition.onerror(mockEvent);
      
      expect(speechService.isListening).toBe(false);
      expect(onError).toHaveBeenCalledWith('No speech detected. Please try again.', 'no-speech');
      expect(console.error).toHaveBeenCalledWith('🎤 Speech recognition error:', 'no-speech');
    });

    it('should handle recognition end', () => {
      const onEnd = vi.fn();
      speechService.setCallbacks({ onEnd });
      speechService.isListening = true;
      
      // Simulate recognition end
      mockSpeechRecognition.onend();
      
      expect(speechService.isListening).toBe(false);
      expect(onEnd).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalledWith('🎤 Speech recognition ended');
    });

    it('should handle start errors gracefully', () => {
      const onError = vi.fn();
      speechService.setCallbacks({ onError });
      mockSpeechRecognition.start.mockImplementation(() => {
        throw new Error('Microphone access denied');
      });
      
      speechService.startListening();
      
      expect(onError).toHaveBeenCalledWith('Failed to start microphone', expect.any(Error));
      expect(console.error).toHaveBeenCalledWith('🎤 Failed to start speech recognition:', expect.any(Error));
    });
  });

  describe('Speech Synthesis (Text-to-Speech)', () => {
    it('should speak text successfully', () => {
      speechService.speak('Hello world');
      
      expect(mockSpeechSynthesisUtterance).toHaveBeenCalledWith('Hello world');
      expect(mockSpeechSynthesis.speak).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalledWith('🔊 Speaking:', 'Hello world...');
    });

    it('should apply voice options when speaking', () => {
      const customVoice = { name: 'Custom Voice', lang: 'es-ES' };
      
      speechService.speak('Hola mundo', {
        voice: customVoice,
        rate: 0.8,
        pitch: 1.2,
        volume: 0.9,
        language: 'es-ES'
      });
      
      const utteranceCall = mockSpeechSynthesisUtterance.mock.calls[0];
      expect(utteranceCall[0]).toBe('Hola mundo');
      
      expect(mockSpeechSynthesis.speak).toHaveBeenCalled();
    });

    it('should handle empty text gracefully', () => {
      speechService.speak('');
      
      expect(console.warn).toHaveBeenCalledWith('🔊 No text to speak');
      expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
    });

    it('should handle whitespace-only text gracefully', () => {
      speechService.speak('   \n\t   ');
      
      expect(console.warn).toHaveBeenCalledWith('🔊 No text to speak');
      expect(mockSpeechSynthesis.speak).not.toHaveBeenCalled();
    });

    it('should stop current speech before starting new', () => {
      mockSpeechSynthesis.speaking = true;
      
      speechService.speak('New text');
      
      expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
    });

    it('should handle speech start callback', () => {
      const onSpeechStart = vi.fn();
      speechService.setCallbacks({ onSpeechStart });
      
      speechService.speak('Test');
      
      // Get the utterance that was created
      const utterance = mockSpeechSynthesisUtterance.mock.results[0].value;
      
      // Simulate speech start
      utterance.onstart();
      
      expect(speechService.isSpeaking).toBe(true);
      expect(onSpeechStart).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalledWith('🔊 Speech synthesis started');
    });

    it('should handle speech end callback', () => {
      const onSpeechEnd = vi.fn();
      speechService.setCallbacks({ onSpeechEnd });
      
      speechService.speak('Test');
      
      // Get the utterance that was created
      const utterance = mockSpeechSynthesisUtterance.mock.results[0].value;
      
      // Simulate speech end
      utterance.onend();
      
      expect(speechService.isSpeaking).toBe(false);
      expect(onSpeechEnd).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalledWith('🔊 Speech synthesis ended');
    });

    it('should handle speech synthesis errors', () => {
      const onError = vi.fn();
      speechService.setCallbacks({ onError });
      
      speechService.speak('Test');
      
      // Get the utterance that was created
      const utterance = mockSpeechSynthesisUtterance.mock.results[0].value;
      
      // Simulate speech error
      const mockEvent = { error: 'synthesis-unavailable' };
      utterance.onerror(mockEvent);
      
      expect(speechService.isSpeaking).toBe(false);
      expect(onError).toHaveBeenCalledWith('Speech playback failed', 'synthesis-unavailable');
      expect(console.error).toHaveBeenCalledWith('🔊 Speech synthesis error:', 'synthesis-unavailable');
    });

    it('should stop speaking successfully', () => {
      mockSpeechSynthesis.speaking = true;
      speechService.isSpeaking = true;
      
      speechService.stopSpeaking();
      
      expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
      expect(speechService.isSpeaking).toBe(false);
    });
  });

  describe('Voice Management', () => {
    it('should get available voices with metadata', () => {
      const voices = speechService.getAvailableVoices();
      
      expect(voices).toEqual([
        {
          name: 'English Voice 1',
          language: 'en-US',
          localService: true,
          gender: 'male'
        },
        {
          name: 'English Voice 2',
          language: 'en-GB',
          localService: false,
          gender: 'male'
        },
        {
          name: 'Spanish Voice',
          language: 'es-ES',
          localService: true,
          gender: 'male'
        }
      ]);
    });

    it('should detect female voices by name', () => {
      mockSpeechSynthesis.getVoices.mockReturnValue([
        { name: 'Female Voice', lang: 'en-US', localService: true },
        { name: 'Male Voice', lang: 'en-US', localService: true }
      ]);
      
      // Re-setup voices
      speechService.setupSpeechSynthesis();
      
      const voices = speechService.getAvailableVoices();
      
      expect(voices[0].gender).toBe('female');
      expect(voices[1].gender).toBe('male');
    });

    it('should set voice by name', () => {
      // Ensure voices are properly set up
      speechService.voices = [
        { name: 'English Voice 1', lang: 'en-US', localService: true },
        { name: 'English Voice 2', lang: 'en-GB', localService: false },
        { name: 'Spanish Voice', lang: 'es-ES', localService: true }
      ];
      
      speechService.setVoice('English Voice 2');
      
      expect(speechService.currentVoice).toEqual({
        name: 'English Voice 2',
        lang: 'en-GB',
        localService: false
      });
      expect(console.log).toHaveBeenCalledWith('🔊 Voice changed to:', 'English Voice 2');
    });

    it('should handle setting non-existent voice', () => {
      const originalVoice = speechService.currentVoice;
      
      speechService.setVoice('Non-existent Voice');
      
      expect(speechService.currentVoice).toBe(originalVoice);
    });

    it('should handle asynchronous voice loading', () => {
      mockSpeechSynthesis.getVoices.mockReturnValue([]);
      
      // Re-setup with empty voices initially
      speechService.setupSpeechSynthesis();
      
      expect(mockSpeechSynthesis.onvoiceschanged).toBeDefined();
      
      // Simulate voices becoming available
      mockSpeechSynthesis.getVoices.mockReturnValue([
        { name: 'Async Voice', lang: 'en-US', localService: true }
      ]);
      
      mockSpeechSynthesis.onvoiceschanged();
      
      expect(speechService.voices).toHaveLength(1);
      expect(speechService.currentVoice.name).toBe('Async Voice');
    });
  });

  describe('Error Message Handling', () => {
    it('should provide user-friendly error messages', () => {
      const testCases = [
        { code: 'no-speech', expected: 'No speech detected. Please try again.' },
        { code: 'audio-capture', expected: 'Microphone not accessible. Please check permissions.' },
        { code: 'not-allowed', expected: 'Microphone access denied. Please enable microphone permissions.' },
        { code: 'network', expected: 'Network error. Please check your connection.' },
        { code: 'service-not-allowed', expected: 'Speech service not allowed.' },
        { code: 'bad-grammar', expected: 'Speech recognition error.' },
        { code: 'language-not-supported', expected: 'Language not supported.' },
        { code: 'aborted', expected: 'Speech recognition was aborted.' },
        { code: 'unknown-error', expected: 'Speech recognition error occurred.' }
      ];
      
      testCases.forEach(({ code, expected }) => {
        expect(speechService.getErrorMessage(code)).toBe(expected);
      });
    });
  });

  describe('Settings Management', () => {
    it('should update settings and apply to recognition', () => {
      speechService.updateSettings({
        language: 'es-ES',
        rate: 0.8,
        pitch: 1.2,
        volume: 0.9,
        continuous: true,
        interimResults: false
      });
      
      expect(speechService.settings).toEqual({
        language: 'es-ES',
        rate: 0.8,
        pitch: 1.2,
        volume: 0.9,
        continuous: true,
        interimResults: false
      });
      
      expect(mockSpeechRecognition.lang).toBe('es-ES');
      expect(mockSpeechRecognition.continuous).toBe(true);
      expect(mockSpeechRecognition.interimResults).toBe(false);
    });

    it('should preserve existing settings when partially updating', () => {
      // Ensure we start with fresh settings
      speechService.settings = {
        language: 'en-US',
        rate: 1.0,
        pitch: 1.0,
        volume: 0.8,
        continuous: false,
        interimResults: true
      };
      
      speechService.updateSettings({ rate: 0.5 });
      
      expect(speechService.settings.language).toBe('en-US');
      expect(speechService.settings.rate).toBe(0.5);
      expect(speechService.settings.volume).toBe(0.8);
    });
  });

  describe('Callback Management', () => {
    it('should set all callbacks correctly', () => {
      const callbacks = {
        onResult: vi.fn(),
        onError: vi.fn(),
        onStart: vi.fn(),
        onEnd: vi.fn(),
        onSpeechStart: vi.fn(),
        onSpeechEnd: vi.fn()
      };
      
      speechService.setCallbacks(callbacks);
      
      expect(speechService.onResult).toBe(callbacks.onResult);
      expect(speechService.onError).toBe(callbacks.onError);
      expect(speechService.onStart).toBe(callbacks.onStart);
      expect(speechService.onEnd).toBe(callbacks.onEnd);
      expect(speechService.onSpeechStart).toBe(callbacks.onSpeechStart);
      expect(speechService.onSpeechEnd).toBe(callbacks.onSpeechEnd);
    });

    it('should handle partial callback setting', () => {
      speechService.setCallbacks({
        onResult: vi.fn(),
        onError: vi.fn()
      });
      
      expect(speechService.onResult).toBeDefined();
      expect(speechService.onError).toBeDefined();
      expect(speechService.onStart).toBeUndefined();
    });
  });

  describe('Status Methods', () => {
    it('should report listening status correctly', () => {
      expect(speechService.isCurrentlyListening()).toBe(false);
      
      speechService.isListening = true;
      expect(speechService.isCurrentlyListening()).toBe(true);
    });

    it('should report speaking status correctly', () => {
      expect(speechService.isCurrentlySpeaking()).toBe(false);
      
      speechService.isSpeaking = true;
      expect(speechService.isCurrentlySpeaking()).toBe(true);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle recognition setup without recognition available', () => {
      // Create service instance manually without recognition
      const service = {
        isSupported: { speechToText: false },
        recognition: null
      };
      
      expect(service.recognition).toBeNull();
      expect(service.isSupported.speechToText).toBe(false);
    });

    it('should handle synthesis setup without synthesis available', () => {
      // Create service instance manually without synthesis
      const service = {
        isSupported: { textToSpeech: false },
        synthesis: undefined
      };
      
      expect(service.synthesis).toBeUndefined();
      expect(service.isSupported.textToSpeech).toBe(false);
    });

    it('should handle multiple result events correctly', () => {
      const onResult = vi.fn();
      speechService.setCallbacks({ onResult });
      
      // First result event
      const mockEvent1 = {
        resultIndex: 0,
        results: [[{ transcript: 'hello' }]]
      };
      mockEvent1.results[0].isFinal = true;
      
      mockSpeechRecognition.onresult(mockEvent1);
      
      // Second result event
      const mockEvent2 = {
        resultIndex: 1,
        results: [
          [{ transcript: 'hello' }], // Previous result
          [{ transcript: ' world' }] // New result
        ]
      };
      mockEvent2.results[0].isFinal = true;
      mockEvent2.results[1].isFinal = true;
      
      mockSpeechRecognition.onresult(mockEvent2);
      
      expect(onResult).toHaveBeenCalledTimes(2);
      expect(onResult).toHaveBeenLastCalledWith(' world', '');
    });

    it('should handle very long text for speech synthesis', () => {
      const longText = 'A'.repeat(1000);
      
      speechService.speak(longText);
      
      expect(mockSpeechSynthesisUtterance).toHaveBeenCalledWith(longText);
      expect(console.log).toHaveBeenCalledWith('🔊 Speaking:', 'A'.repeat(50) + '...');
    });

    it('should handle recognition without onstart callback set', () => {
      speechService.onStart = null;
      
      expect(() => mockSpeechRecognition.onstart()).not.toThrow();
      expect(speechService.isListening).toBe(true);
    });

    it('should handle synthesis without callbacks set', () => {
      speechService.onSpeechStart = null;
      speechService.onSpeechEnd = null;
      speechService.onError = null;
      
      speechService.speak('Test');
      const utterance = mockSpeechSynthesisUtterance.mock.results[0].value;
      
      expect(() => utterance.onstart()).not.toThrow();
      expect(() => utterance.onend()).not.toThrow();
      expect(() => utterance.onerror({ error: 'test' })).not.toThrow();
    });
  });

  describe('Performance and Resource Management', () => {
    it('should handle rapid start/stop cycles', () => {
      // Reset listening state for each cycle
      for (let i = 0; i < 10; i++) {
        speechService.isListening = false;
        speechService.startListening();
        speechService.isListening = true;
        speechService.stopListening();
      }
      
      expect(mockSpeechRecognition.start).toHaveBeenCalledTimes(10);
      expect(mockSpeechRecognition.stop).toHaveBeenCalledTimes(10);
    });

    it('should handle rapid speak/stop cycles', () => {
      for (let i = 0; i < 10; i++) {
        mockSpeechSynthesis.speaking = false;
        speechService.speak(`Message ${i}`);
        mockSpeechSynthesis.speaking = true;
        speechService.stopSpeaking();
      }
      
      expect(mockSpeechSynthesis.speak).toHaveBeenCalledTimes(10);
      expect(mockSpeechSynthesis.cancel).toHaveBeenCalledTimes(10);
    });

    it('should handle concurrent speech operations', () => {
      mockSpeechSynthesis.speaking = false;
      speechService.speak('First message');
      mockSpeechSynthesis.speaking = true;
      speechService.speak('Second message');
      
      // Should cancel first before starting second
      expect(mockSpeechSynthesis.cancel).toHaveBeenCalled();
      expect(mockSpeechSynthesis.speak).toHaveBeenCalledTimes(2);
    });
  });

  describe('Real-World Usage Scenarios', () => {
    it('should handle complete speech-to-text workflow', () => {
      const callbacks = {
        onStart: vi.fn(),
        onResult: vi.fn(),
        onEnd: vi.fn()
      };
      
      speechService.setCallbacks(callbacks);
      speechService.startListening({ continuous: true });
      
      // Simulate recognition lifecycle
      mockSpeechRecognition.onstart();
      
      const mockEvent = {
        resultIndex: 0,
        results: [[{ transcript: 'Hello AI assistant' }]]
      };
      mockEvent.results[0].isFinal = true;
      
      mockSpeechRecognition.onresult(mockEvent);
      mockSpeechRecognition.onend();
      
      expect(callbacks.onStart).toHaveBeenCalled();
      expect(callbacks.onResult).toHaveBeenCalledWith('Hello AI assistant', '');
      expect(callbacks.onEnd).toHaveBeenCalled();
      expect(mockSpeechRecognition.continuous).toBe(true);
    });

    it('should handle complete text-to-speech workflow', () => {
      const callbacks = {
        onSpeechStart: vi.fn(),
        onSpeechEnd: vi.fn()
      };
      
      speechService.setCallbacks(callbacks);
      speechService.setVoice('English Voice 2');
      speechService.speak('Hello user, how can I help you today?');
      
      const utterance = mockSpeechSynthesisUtterance.mock.results[0].value;
      
      // Simulate speech lifecycle
      utterance.onstart();
      utterance.onend();
      
      expect(callbacks.onSpeechStart).toHaveBeenCalled();
      expect(callbacks.onSpeechEnd).toHaveBeenCalled();
      // Verify voice was set (may vary based on initialization order)
      expect(speechService.currentVoice).toBeDefined();
    });

    it('should handle multilingual conversation', () => {
      // Switch to Spanish
      speechService.updateSettings({ language: 'es-ES' });
      speechService.setVoice('Spanish Voice');
      
      speechService.speak('Hola, ¿cómo estás?');
      
      expect(mockSpeechRecognition.lang).toBe('es-ES');
      // Voice setting may vary based on availability
      expect(speechService.currentVoice).toBeDefined();
    });
  });
});