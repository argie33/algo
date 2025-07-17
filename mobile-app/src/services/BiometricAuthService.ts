import ReactNativeBiometrics from 'react-native-biometrics';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface BiometricAuthResult {
  success: boolean;
  error?: string;
  biometryType?: string;
}

export class BiometricAuthService {
  private static rnBiometrics = new ReactNativeBiometrics();

  /**
   * Check if biometric authentication is available on the device
   */
  static async isAvailable(): Promise<{
    available: boolean;
    biometryType?: string;
    error?: string;
  }> {
    try {
      const { available, biometryType } = await this.rnBiometrics.isSensorAvailable();
      
      return {
        available,
        biometryType,
      };
    } catch (error) {
      return {
        available: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * Authenticate user with biometric data
   */
  static async authenticate(promptMessage: string): Promise<BiometricAuthResult> {
    try {
      const { available, biometryType } = await this.isAvailable();
      
      if (!available) {
        return {
          success: false,
          error: 'Biometric authentication not available',
        };
      }

      const { success, error } = await this.rnBiometrics.simplePrompt({
        promptMessage,
        cancelButtonText: 'Use Password',
      });

      if (success) {
        // Log successful authentication
        await AsyncStorage.setItem(
          'lastBiometricAuth',
          new Date().toISOString()
        );
      }

      return {
        success,
        error,
        biometryType,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Authentication failed',
      };
    }
  }

  /**
   * Enable biometric authentication for the user
   */
  static async enableBiometricAuth(): Promise<BiometricAuthResult> {
    try {
      const { available } = await this.isAvailable();
      
      if (!available) {
        return {
          success: false,
          error: 'Biometric authentication not available on this device',
        };
      }

      // Test biometric authentication
      const authResult = await this.authenticate(
        'Please authenticate to enable biometric login'
      );

      if (authResult.success) {
        await AsyncStorage.setItem('biometricEnabled', 'true');
      }

      return authResult;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to enable biometric auth',
      };
    }
  }

  /**
   * Disable biometric authentication
   */
  static async disableBiometricAuth(): Promise<void> {
    await AsyncStorage.removeItem('biometricEnabled');
    await AsyncStorage.removeItem('lastBiometricAuth');
  }

  /**
   * Check if biometric authentication is enabled for the user
   */
  static async isBiometricEnabled(): Promise<boolean> {
    const enabled = await AsyncStorage.getItem('biometricEnabled');
    return enabled === 'true';
  }

  /**
   * Create biometric key for secure storage
   */
  static async createBiometricKey(keyAlias: string): Promise<BiometricAuthResult> {
    try {
      const { available } = await this.isAvailable();
      
      if (!available) {
        return {
          success: false,
          error: 'Biometric authentication not available',
        };
      }

      const { success, error } = await this.rnBiometrics.createKeys();

      return {
        success,
        error,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to create biometric key',
      };
    }
  }

  /**
   * Sign data with biometric key (for secure trading confirmations)
   */
  static async signWithBiometric(
    payload: string,
    promptMessage: string
  ): Promise<{
    success: boolean;
    signature?: string;
    error?: string;
  }> {
    try {
      const { success, signature, error } = await this.rnBiometrics.createSignature({
        promptMessage,
        payload,
      });

      return {
        success,
        signature,
        error,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Signing failed',
      };
    }
  }

  /**
   * Get device biometric capabilities
   */
  static async getDeviceCapabilities(): Promise<{
    biometryType?: string;
    available: boolean;
    hasHardware: boolean;
    hasEnrolledBiometrics: boolean;
  }> {
    try {
      const { available, biometryType } = await this.rnBiometrics.isSensorAvailable();
      
      return {
        biometryType,
        available,
        hasHardware: available,
        hasEnrolledBiometrics: available,
      };
    } catch (error) {
      return {
        available: false,
        hasHardware: false,
        hasEnrolledBiometrics: false,
      };
    }
  }
}