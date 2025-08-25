import { useEffect } from 'react';

/**
 * Custom hook to set document title for accessibility and SEO
 * @param {string} title - The page title
 * @param {string} suffix - Optional suffix (defaults to "Financial Dashboard")
 */
export const useDocumentTitle = (title, suffix = 'Financial Dashboard') => {
  useEffect(() => {
    const previousTitle = document.title;
    
    if (title) {
      document.title = `${title} | ${suffix}`;
    }
    
    // Cleanup function to restore previous title or default
    return () => {
      // Ensure we always have a valid title, fallback to the suffix if previous title is empty
      document.title = previousTitle && previousTitle.trim() ? previousTitle : suffix;
    };
  }, [title, suffix]);
};

export default useDocumentTitle;