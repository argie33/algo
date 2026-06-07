/**
 * Request Batching Utility
 * Limits concurrent API requests to prevent connection pool exhaustion
 */

/**
 * Execute promises with concurrency limit
 * @param {Array} items - Array of items to process
 * @param {Function} fn - Async function to execute per item: (item) => Promise
 * @param {number} concurrency - Max concurrent requests (default: 5)
 * @returns {Promise<Array>} Array of results in original order
 */
export async function batchRequests(items, fn, concurrency = 5) {
  if (items.length === 0) return [];

  const results = Array(items.length).fill(null);
  const inProgress = new Set();
  let nextIndex = 0;

  const executeNext = async () => {
    if (nextIndex >= items.length) return;

    const currentIndex = nextIndex++;
    const item = items[currentIndex];

    try {
      results[currentIndex] = await fn(item);
    } catch (error) {
      results[currentIndex] = { error, item };
    } finally {
      inProgress.delete(currentIndex);
    }
  };

  // Start initial batch of requests
  for (let i = 0; i < Math.min(concurrency, items.length); i++) {
    inProgress.add(i);
    executeNext().catch(err => console.error('[Batcher] Error:', err));
  }

  // Continue executing as slots free up
  while (inProgress.size > 0) {
    await Promise.race(
      Array.from(inProgress).map(i => new Promise(resolve => setTimeout(resolve, 10)))
    );

    // Execute next batch
    while (inProgress.size < concurrency && nextIndex < items.length) {
      inProgress.add(nextIndex);
      executeNext().catch(err => console.error('[Batcher] Error:', err));
    }
  }

  return results;
}

/**
 * Batch multiple promises with concurrency control
 * @param {Array<Function>} promiseFunctions - Array of functions that return promises
 * @param {number} concurrency - Max concurrent requests
 * @returns {Promise<Array>} Array of results in original order
 */
export async function batchPromises(promiseFunctions, concurrency = 5) {
  return batchRequests(promiseFunctions, fn => fn(), concurrency);
}
