/**
 * Hook to validate data before rendering
 * Returns validated items with filtering for null/undefined
 * Usage: const validatedItems = useValidatedData(items, ['symbol', 'price'])
 */
import { validateItems } from "../utils/responseNormalizer";

export const useValidatedData = (
  items,
  requiredFields = [],
  defaultValue = []
) => {
  // Handle null/undefined/non-array
  if (!Array.isArray(items)) {
    console.warn("[useValidatedData] Expected array but got", typeof items);
    return defaultValue;
  }

  // Filter out null/undefined items
  const filtered = items.filter((item) => item !== null && item !== undefined);

  // If no required fields specified, just return filtered array
  if (requiredFields.length === 0) {
    return filtered;
  }

  // Validate that items have required fields
  const { valid, invalidItems, missingFields } = validateItems(
    filtered,
    requiredFields
  );

  if (!valid) {
    console.warn(
      `[useValidatedData] ${invalidItems.length} of ${filtered.length} items invalid. Missing: ${[...missingFields].join(", ")}`
    );
  }

  // Return filtered items (validation already warned about invalid ones)
  return filtered.filter((_, idx) => !invalidItems.includes(idx));
};

export default useValidatedData;
