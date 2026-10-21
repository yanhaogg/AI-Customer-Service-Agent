// import { StrictMode } from 'react'
// import { createRoot } from 'react-dom/client'
// import './index.css'
// import App from './App.jsx'

// createRoot(document.getElementById('root')).render(
//   <StrictMode>
//     <App />
//   </StrictMode>,
// )

import ReactDOM from 'react-dom/client'

import Router from './router'
import AuthProvider from './auth/AuthProvider'
import './index.css'


ReactDOM.createRoot(
    document.getElementById('root')
)
.render(
    <AuthProvider><Router /></AuthProvider>
)
import './storefront.css'
import './navbar.css'
