import React, { useEffect, useState } from 'react';
import {
  StatusBar,
  StyleSheet,
  Text,
  View,
  Alert,
  AppState,
  AppStateStatus,
} from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import Icon from 'react-native-vector-icons/MaterialIcons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AuthProvider } from './src/contexts/AuthContext';
import { DataProvider } from './src/contexts/DataContext';
import { NotificationProvider } from './src/contexts/NotificationContext';
import { BiometricAuthService } from './src/services/BiometricAuthService';
import { VoiceTradingService } from './src/services/VoiceTradingService';
import { OfflineDataService } from './src/services/OfflineDataService';
import LoginScreen from './src/screens/LoginScreen';
import PortfolioScreen from './src/screens/PortfolioScreen';
import TradingScreen from './src/screens/TradingScreen';
import MarketScreen from './src/screens/MarketScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import VoiceTradingScreen from './src/screens/VoiceTradingScreen';
import ARVisualizationScreen from './src/screens/ARVisualizationScreen';

const Tab = createBottomTabNavigator();
const Stack = createStackNavigator();

// Main App Navigation
function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: string;

          switch (route.name) {
            case 'Portfolio':
              iconName = 'account-balance-wallet';
              break;
            case 'Trading':
              iconName = 'trending-up';
              break;
            case 'Market':
              iconName = 'assessment';
              break;
            case 'Voice':
              iconName = 'mic';
              break;
            case 'Settings':
              iconName = 'settings';
              break;
            default:
              iconName = 'help';
          }

          return <Icon name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: '#2196F3',
        tabBarInactiveTintColor: 'gray',
        headerStyle: {
          backgroundColor: '#1a1a1a',
        },
        headerTintColor: '#fff',
        tabBarStyle: {
          backgroundColor: '#1a1a1a',
          borderTopColor: '#333',
        },
      })}
    >
      <Tab.Screen 
        name="Portfolio" 
        component={PortfolioScreen}
        options={{ title: 'Portfolio' }}
      />
      <Tab.Screen 
        name="Trading" 
        component={TradingScreen}
        options={{ title: 'Trading' }}
      />
      <Tab.Screen 
        name="Market" 
        component={MarketScreen}
        options={{ title: 'Market Data' }}
      />
      <Tab.Screen 
        name="Voice" 
        component={VoiceTradingScreen}
        options={{ title: 'Voice Trading' }}
      />
      <Tab.Screen 
        name="Settings" 
        component={SettingsScreen}
        options={{ title: 'Settings' }}
      />
    </Tab.Navigator>
  );
}

// Main App Component
const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [appState, setAppState] = useState(AppState.currentState);

  useEffect(() => {
    initializeApp();
    
    const appStateSubscription = AppState.addEventListener(
      'change',
      handleAppStateChange
    );

    return () => {
      appStateSubscription?.remove();
    };
  }, []);

  const initializeApp = async () => {
    try {
      // Initialize offline data service
      await OfflineDataService.initialize();
      
      // Check for existing authentication
      const authToken = await AsyncStorage.getItem('authToken');
      const biometricEnabled = await AsyncStorage.getItem('biometricEnabled');
      
      if (authToken) {
        if (biometricEnabled === 'true') {
          // Require biometric authentication
          const biometricResult = await BiometricAuthService.authenticate(
            'Please authenticate to access your portfolio'
          );
          
          if (biometricResult.success) {
            setIsAuthenticated(true);
          } else {
            // Fallback to traditional login
            await AsyncStorage.removeItem('authToken');
          }
        } else {
          setIsAuthenticated(true);
        }
      }
    } catch (error) {
      console.error('App initialization error:', error);
      Alert.alert('Error', 'Failed to initialize app. Please restart.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAppStateChange = (nextAppState: AppStateStatus) => {
    if (appState.match(/inactive|background/) && nextAppState === 'active') {
      // App came to foreground - refresh data
      if (isAuthenticated) {
        OfflineDataService.syncWithServer();
      }
    }
    setAppState(nextAppState);
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>Financial Platform</Text>
        <Text style={styles.loadingSubtext}>Loading...</Text>
      </View>
    );
  }

  return (
    <AuthProvider>
      <DataProvider>
        <NotificationProvider>
          <NavigationContainer>
            <StatusBar barStyle="light-content" backgroundColor="#1a1a1a" />
            <Stack.Navigator screenOptions={{ headerShown: false }}>
              {isAuthenticated ? (
                <>
                  <Stack.Screen name="Main" component={MainTabs} />
                  <Stack.Screen 
                    name="ARVisualization" 
                    component={ARVisualizationScreen}
                    options={{
                      headerShown: true,
                      title: 'AR Chart Visualization',
                      headerStyle: { backgroundColor: '#1a1a1a' },
                      headerTintColor: '#fff',
                    }}
                  />
                </>
              ) : (
                <Stack.Screen 
                  name="Login" 
                  component={LoginScreen}
                  initialParams={{ setIsAuthenticated }}
                />
              )}
            </Stack.Navigator>
          </NavigationContainer>
        </NotificationProvider>
      </DataProvider>
    </AuthProvider>
  );
};

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1a1a1a',
  },
  loadingText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 10,
  },
  loadingSubtext: {
    fontSize: 16,
    color: '#999',
  },
});

export default App;