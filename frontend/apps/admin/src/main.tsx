import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './styles/globals.css'
import { initializeLanguage } from '@glean/i18n'
import { useLanguageStore } from './stores/languageStore'

// Initialize i18n
initializeLanguage()

// Initialize language store
useLanguageStore.getState().initializeLanguage()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
