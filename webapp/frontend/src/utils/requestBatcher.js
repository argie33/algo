/**
 * Request Batching Utility
 * Limits concurrent API requests to prevent connection pool exhaustion
 */

/**
 * Execute async functions with concurrency limit, preserving result order
 * @param {Array} items - Array of items to process
 * @param {Function} fn - Async function to execute per item: (item) => Promise
 * @param {number} concurrency - Max concurrent requests (default: 5)
 * @returns {Promise<Array>} Array of results in original order
 */
export async function batchRequests(items, fn, concurrency = 5) {
  if (items.length === 0) return [];

  const results = new Array(items.length);
  const queue = items.map((item, idx) => ({ item, idx }));
  let activeCount = 0;
  let queueIdx = 0;

  return new Promise((resolve, _reject) => {
    const processNext = async () => {
      if (queueIdx >= queue.length && activeCount === 0) {
        resolve(results);
        return;
      }

      if (queueIdx < queue.length && activeCount < concurrency) {
        const { item, idx } = queue[queueIdx++];
        activeCount++;

        try {
          results[idx] = await fn(item);
        } catch (error) {
          results[idx] = { error, item };
        } finally {
          activeCount--;
          // Continue processing when a slot frees up
          setImmediate(processNext);
        }
      }
    };

    // Start initial batch
    for (let i = 0; i < Math.min(concurrency, items.length); i++) {
      setImmediate(processNext);
    }
  });
}

/**
 * Batch multiple promises with concurrency control
 * @param {Array<Function>} promiseFunctions - Array of functions that return promises
 * @param {number} concurrency - Max concurrent requests
 * @returns {Promise<Array>} Array of results in original order
 */
export async function batchPromises(promiseFunctions, concurrency = 5) {
  return batchRequests(promiseFunctions, (fn) => fn(), concurrency);
}
