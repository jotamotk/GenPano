import React, { createContext, useContext } from 'react';

const ThemeContext = createContext({ theme: 'stripe' });

export function ThemeProvider({ children }) {
  return (
    <ThemeContext.Provider value={{ theme: 'stripe' }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
