const fs = require("fs");
const path = require("path");

const STORE_FILE = path.join(__dirname, "../user_backtest_store.json");

function loadStrategies() {
  if (!fs.existsSync(STORE_FILE)) return [];
  return JSON.parse(fs.readFileSync(STORE_FILE, "utf8"));
}

function saveStrategies(strategies) {
  fs.writeFileSync(STORE_FILE, JSON.stringify(strategies, null, 2));
}

function addStrategy(strategy) {
  const strategies = loadStrategies();
  strategy.id = Date.now().toString();
  strategies.push(strategy);
  saveStrategies(strategies);
  return strategy;
}

function getStrategy(id) {
  return loadStrategies().find((s) => s.id === id);
}

function deleteStrategy(id) {
  let strategies = loadStrategies();
  strategies = strategies.filter((s) => s.id !== id);
  saveStrategies(strategies);
}

// Backtest-specific methods (alias for strategies)
function getBacktest(id) {
  return getStrategy(id);
}

function addBacktest(backtest) {
  return addStrategy(backtest);
}

function listBacktests() {
  return loadStrategies();
}

function getUserStrategies(userId) {
  return loadStrategies().filter((s) => s.userId === userId);
}

module.exports = {
  loadStrategies,
  saveStrategies,
  addStrategy,
  getStrategy,
  deleteStrategy,
  getUserStrategies,
  getBacktest,
  addBacktest,
  listBacktests,
};
