import { useMemo } from 'react';

/**
 * Hook to validate and handle data from API responses.
 * Works with DataError discriminator pattern (isDataError flag).
 * @param {any} data - The data to validate
 * @param {string} fieldPath - Dot-notation path to field (e.g., 'portfolio.value')
 * @returns {{isValid: boolean, hasError: boolean, value: any, error: any}}
 */
export const useDataValidation = (data, fieldPath = null) => {
  return useMemo(() => {
    const result = {
      isValid: false,
      hasError: false,
      value: null,
      error: null,
    };

    if (data === null || data === undefined) {
      result.hasError = true;
      result.error = 'Data is null or undefined';
      return result;
    }

    // Check for DataError discriminator pattern
    if (typeof data === 'object' && data.isDataError === true) {
      result.hasError = true;
      result.error = data.message || 'Data validation error';
      return result;
    }

    // If fieldPath specified, navigate to nested field
    if (fieldPath) {
      const parts = fieldPath.split('.');
      let current = data;

      for (const part of parts) {
        if (current === null || current === undefined) {
          result.hasError = true;
          result.error = `Field '${part}' is missing`;
          return result;
        }
        current = current[part];
      }

      // Check if nested value is a DataError
      if (typeof current === 'object' && current?.isDataError === true) {
        result.hasError = true;
        result.error = current.message || 'Data validation error in nested field';
        return result;
      }

      result.value = current;
    } else {
      result.value = data;
    }

    result.isValid = true;
    return result;
  }, [data, fieldPath]);
};

/**
 * Hook to validate multiple fields and return consolidated validation status.
 * @param {object} fields - Object with field names as keys and values to validate
 * @returns {{isValid: boolean, errors: object, values: object}}
 */
export const useDataValidationMultiple = (fields) => {
  return useMemo(() => {
    const result = {
      isValid: true,
      errors: {},
      values: {},
    };

    if (!fields || typeof fields !== 'object') {
      result.isValid = false;
      result.errors.root = 'Invalid fields object';
      return result;
    }

    for (const [key, value] of Object.entries(fields)) {
      // Check for null/undefined
      if (value === null || value === undefined) {
        result.isValid = false;
        result.errors[key] = 'Value is null or undefined';
        continue;
      }

      // Check for DataError
      if (typeof value === 'object' && value.isDataError === true) {
        result.isValid = false;
        result.errors[key] = value.message || 'Data validation error';
        continue;
      }

      result.values[key] = value;
    }

    return result;
  }, [fields]);
};

/**
 * Hook to check if response contains any error entries.
 * @param {object} response - API response object
 * @returns {boolean}
 */
export const useHasDataErrors = (response) => {
  return useMemo(() => {
    if (!response || typeof response !== 'object') return false;
    if (response.isDataError === true) return true;
    if (Array.isArray(response.errors) && response.errors.length > 0) return true;
    return false;
  }, [response]);
};

/**
 * Get error messages from a response.
 * @param {object} response - API response
 * @returns {string[]}
 */
export const getResponseErrors = (response) => {
  const errors = [];

  if (!response || typeof response !== 'object') {
    return errors;
  }

  if (response.isDataError === true) {
    if (response.message) errors.push(response.message);
  }

  if (Array.isArray(response.errors)) {
    errors.push(...response.errors.filter(e => typeof e === 'string'));
  }

  return errors;
};
