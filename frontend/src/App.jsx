/**
 * App.jsx — CoWorkX routing.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Marketplace from './pages/Marketplace'
import TaskView from './pages/TaskView'
import Wallet from './pages/Wallet'
import Network from './pages/Network'
import Tasks from './pages/Tasks'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Marketplace />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:id" element={<TaskView />} />
        <Route path="/wallet" element={<Wallet />} />
        <Route path="/network" element={<Network />} />
      </Routes>
    </BrowserRouter>
  )
}
