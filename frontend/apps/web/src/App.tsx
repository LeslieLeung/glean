import React from 'react'
import { Routes, Route } from 'react-router-dom'

/**
 * Root application component.
 *
 * Defines the main routing structure for the web application.
 */
function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Routes>
        <Route path="/" element={
          <div className="flex items-center justify-center h-screen">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-gray-900 mb-4">
                Glean 拾灵
              </h1>
              <p className="text-lg text-gray-600">
                Personal Knowledge Management Tool
              </p>
              <p className="text-sm text-gray-500 mt-2">
                M0 Phase - Coming Soon
              </p>
            </div>
          </div>
        } />
      </Routes>
    </div>
  )
}

export default App
