import React from 'react'
import ReactDOM from 'react-dom/client'

const root = document.getElementById('root')
if (root) {
  ReactDOM.createRoot(root).render(
    React.createElement('div', null,
      React.createElement('h1', null, 'Hello from React!'),
      React.createElement('p', null, 'Test without JSX syntax')
    )
  )
}
