import Voice from 'react-native-voice';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { BiometricAuthService } from './BiometricAuthService';
import { TradingService } from './TradingService';

export interface VoiceCommand {
  action: 'buy' | 'sell' | 'check' | 'status' | 'cancel';
  symbol?: string;
  quantity?: number;
  price?: number;
  orderType?: 'market' | 'limit' | 'stop';
  confidence: number;
  originalText: string;
}

export interface VoiceCommandResult {
  success: boolean;
  command?: VoiceCommand;
  error?: string;
  requiresConfirmation?: boolean;
  orderPreview?: any;
}

export class VoiceTradingService {
  private static isListening = false;
  private static commandHistory: VoiceCommand[] = [];

  /**
   * Initialize voice trading service
   */
  static async initialize(): Promise<void> {
    try {
      Voice.onSpeechStart = this.onSpeechStart;
      Voice.onSpeechEnd = this.onSpeechEnd;
      Voice.onSpeechResults = this.onSpeechResults;
      Voice.onSpeechError = this.onSpeechError;
      Voice.onSpeechPartialResults = this.onSpeechPartialResults;

      // Check if voice trading is enabled
      const voiceEnabled = await AsyncStorage.getItem('voiceTradingEnabled');
      if (voiceEnabled !== 'true') {
        console.log('Voice trading is disabled');
      }
    } catch (error) {
      console.error('Failed to initialize voice trading:', error);
    }
  }

  /**
   * Start listening for voice commands
   */
  static async startListening(): Promise<void> {
    try {
      if (this.isListening) {
        await this.stopListening();
      }

      await Voice.start('en-US');
      this.isListening = true;
    } catch (error) {
      console.error('Failed to start voice recognition:', error);
      throw new Error('Could not start voice recognition');
    }
  }

  /**
   * Stop listening for voice commands
   */
  static async stopListening(): Promise<void> {
    try {
      await Voice.stop();
      this.isListening = false;
    } catch (error) {
      console.error('Failed to stop voice recognition:', error);
    }
  }

  /**
   * Parse voice command text into structured command
   */
  static parseVoiceCommand(text: string): VoiceCommand {
    const lowercaseText = text.toLowerCase();
    
    // Extract action
    let action: VoiceCommand['action'] = 'check';
    if (lowercaseText.includes('buy') || lowercaseText.includes('purchase')) {
      action = 'buy';
    } else if (lowercaseText.includes('sell')) {
      action = 'sell';
    } else if (lowercaseText.includes('cancel')) {
      action = 'cancel';
    } else if (lowercaseText.includes('status') || lowercaseText.includes('portfolio')) {
      action = 'status';
    }

    // Extract symbol
    const symbolRegex = /(?:shares of|stock of|symbol)?\s*([A-Z]{1,5})\b/i;
    const symbolMatch = text.match(symbolRegex);
    const symbol = symbolMatch ? symbolMatch[1].toUpperCase() : undefined;

    // Extract quantity
    const quantityRegex = /(\d+)\s*(?:shares?|stocks?)?/i;
    const quantityMatch = text.match(quantityRegex);
    const quantity = quantityMatch ? parseInt(quantityMatch[1], 10) : undefined;

    // Extract price
    const priceRegex = /(?:at|for|price)\s*\$?(\d+(?:\.\d{2})?)/i;
    const priceMatch = text.match(priceRegex);
    const price = priceMatch ? parseFloat(priceMatch[1]) : undefined;

    // Determine order type
    let orderType: VoiceCommand['orderType'] = 'market';
    if (price && (lowercaseText.includes('limit') || lowercaseText.includes('at'))) {
      orderType = 'limit';
    } else if (lowercaseText.includes('stop')) {
      orderType = 'stop';
    }

    // Calculate confidence based on parsed elements
    let confidence = 0.5;
    if (action && action !== 'check') confidence += 0.2;
    if (symbol) confidence += 0.2;
    if (quantity) confidence += 0.1;

    return {
      action,
      symbol,
      quantity,
      price,
      orderType,
      confidence,
      originalText: text,
    };
  }

  /**
   * Execute voice command with security validation
   */
  static async executeVoiceCommand(command: VoiceCommand): Promise<VoiceCommandResult> {
    try {
      // Validate command confidence
      if (command.confidence < 0.7) {
        return {
          success: false,
          error: 'Command not clear enough. Please try again.',
        };
      }

      // Check if voice trading is enabled
      const voiceEnabled = await AsyncStorage.getItem('voiceTradingEnabled');
      if (voiceEnabled !== 'true') {
        return {
          success: false,
          error: 'Voice trading is disabled. Enable it in settings.',
        };
      }

      // Handle different command types
      switch (command.action) {
        case 'buy':
        case 'sell':
          return await this.handleTradeCommand(command);
        
        case 'status':
          return await this.handleStatusCommand();
        
        case 'cancel':
          return await this.handleCancelCommand();
        
        case 'check':
          return await this.handleCheckCommand(command);
        
        default:
          return {
            success: false,
            error: 'Unknown command type',
          };
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Command execution failed',
      };
    }
  }

  /**
   * Handle trading commands (buy/sell)
   */
  private static async handleTradeCommand(command: VoiceCommand): Promise<VoiceCommandResult> {
    if (!command.symbol || !command.quantity) {
      return {
        success: false,
        error: 'Please specify both symbol and quantity for trading',
      };
    }

    // Get order preview
    const orderPreview = await TradingService.getOrderPreview({
      symbol: command.symbol,
      side: command.action,
      qty: command.quantity,
      type: command.orderType || 'market',
      ...(command.price && { limit_price: command.price }),
    });

    // Require biometric confirmation for trades
    const biometricResult = await BiometricAuthService.authenticate(
      `Confirm ${command.action} ${command.quantity} shares of ${command.symbol}`
    );

    if (!biometricResult.success) {
      return {
        success: false,
        error: 'Biometric authentication required for trading',
      };
    }

    // Execute the trade
    const tradeResult = await TradingService.submitOrder({
      symbol: command.symbol,
      side: command.action,
      qty: command.quantity,
      type: command.orderType || 'market',
      ...(command.price && { limit_price: command.price }),
    });

    // Store command in history
    this.commandHistory.push({
      ...command,
      confidence: 1.0, // Confirmed execution
    });

    return {
      success: tradeResult.success,
      command,
      orderPreview,
      error: tradeResult.error,
    };
  }

  /**
   * Handle status commands
   */
  private static async handleStatusCommand(): Promise<VoiceCommandResult> {
    // This would integrate with portfolio service
    return {
      success: true,
      command: {
        action: 'status',
        confidence: 1.0,
        originalText: 'Portfolio status',
      },
    };
  }

  /**
   * Handle cancel commands
   */
  private static async handleCancelCommand(): Promise<VoiceCommandResult> {
    // Get pending orders and cancel the most recent
    const pendingOrders = await TradingService.getPendingOrders();
    
    if (pendingOrders.length === 0) {
      return {
        success: false,
        error: 'No pending orders to cancel',
      };
    }

    // Require biometric confirmation
    const biometricResult = await BiometricAuthService.authenticate(
      'Confirm cancellation of pending order'
    );

    if (!biometricResult.success) {
      return {
        success: false,
        error: 'Biometric authentication required for order cancellation',
      };
    }

    const cancelResult = await TradingService.cancelOrder(pendingOrders[0].id);

    return {
      success: cancelResult.success,
      error: cancelResult.error,
    };
  }

  /**
   * Handle check/quote commands
   */
  private static async handleCheckCommand(command: VoiceCommand): Promise<VoiceCommandResult> {
    if (!command.symbol) {
      return {
        success: false,
        error: 'Please specify a symbol to check',
      };
    }

    // This would integrate with market data service
    return {
      success: true,
      command,
    };
  }

  /**
   * Get voice command history
   */
  static getCommandHistory(): VoiceCommand[] {
    return [...this.commandHistory];
  }

  /**
   * Clear command history
   */
  static clearCommandHistory(): void {
    this.commandHistory = [];
  }

  /**
   * Enable/disable voice trading
   */
  static async setVoiceTradingEnabled(enabled: boolean): Promise<void> {
    await AsyncStorage.setItem('voiceTradingEnabled', enabled.toString());
  }

  /**
   * Check if voice trading is enabled
   */
  static async isVoiceTradingEnabled(): Promise<boolean> {
    const enabled = await AsyncStorage.getItem('voiceTradingEnabled');
    return enabled === 'true';
  }

  // Voice recognition event handlers
  private static onSpeechStart = (e: any) => {
    console.log('Voice recognition started');
  };

  private static onSpeechEnd = (e: any) => {
    console.log('Voice recognition ended');
  };

  private static onSpeechResults = (e: any) => {
    if (e.value && e.value.length > 0) {
      const spokenText = e.value[0];
      console.log('Voice command received:', spokenText);
      // This would trigger command processing
    }
  };

  private static onSpeechError = (e: any) => {
    console.error('Voice recognition error:', e.error);
  };

  private static onSpeechPartialResults = (e: any) => {
    // Handle partial results for real-time feedback
    if (e.value && e.value.length > 0) {
      console.log('Partial result:', e.value[0]);
    }
  };
}