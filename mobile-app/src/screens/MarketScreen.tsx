import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const MarketScreen: React.FC = () => {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Market Data</Text>
      <Text style={styles.subtitle}>Real-time market information</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 16,
    color: '#999',
  },
});

export default MarketScreen;