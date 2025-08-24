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
    
    // Cleanup function to restore previous title
    return () => {
      if (previousTitle) {
        document.title = previousTitle;
      }
    };
  }, [title, suffix]);
};

export default useDocumentTitle;