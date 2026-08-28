import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Cliente } from './pages/Cliente'
import { Cocina } from './pages/Cocina'
import { Admin } from './pages/Admin'
import { Ticketera } from './pages/Ticketera'
import { Caja } from './pages/Caja'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Cliente />} />
        <Route path="/cocina" element={<Cocina />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/ticketera" element={<Ticketera />} />
        <Route path="/caja" element={<Caja />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
