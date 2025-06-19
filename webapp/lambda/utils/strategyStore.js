const fs = require('fs');
const path = require('path');

const STRATEGY_FILE = path.join(__dirname, '../user_strategies.json');

function loadStrategies() {
  if (!fs.existsSync(STRATEGY_FILE)) return [];
  return JSON.parse(fs.readFileSync(STRATEGY_FILE, 'utf8'));
}

function saveStrategies(strategies) {
  fs.writeFileSync(STRATEGY_FILE, JSON.stringify(strategies, null, 2));
}

function addStrategy(strategy) {
  const strategies = loadStrategies();
  strategy.id = Date.now().toString();
  strategies.push(strategy);
  saveStrategies(strategies);
  return strategy;
}

function getStrategy(id) {
  return loadStrategies().find(s => s.id === id);
}

function deleteStrategy(id) {
  let strategies = loadStrategies();
  strategies = strategies.filter(s => s.id !== id);
  saveStrategies(strategies);
}

module.exports = {
  loadStrategies,
  saveStrategies,
  addStrategy,
  getStrategy,
  deleteStrategy
};
