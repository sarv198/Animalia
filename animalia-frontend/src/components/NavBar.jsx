import { NavLink } from 'react-router-dom'

export default function NavBar() {
  return (
    <header className="nav">
      <span className="nav-title">Reptilia</span>
      <nav className="nav-links">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
          3D Tree
        </NavLink>
        <NavLink
          to="/phylogeny"
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          Phylogeny
        </NavLink>
      </nav>
    </header>
  )
}
