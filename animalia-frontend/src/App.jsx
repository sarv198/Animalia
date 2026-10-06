import { BrowserRouter, Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import Phylogeny from './pages/Phylogeny.jsx'
import TreeOfLife3D from './pages/TreeOfLife3D.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<TreeOfLife3D />} />
          <Route path="/phylogeny" element={<Phylogeny />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
