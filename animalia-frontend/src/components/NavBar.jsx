import { NavLink } from 'react-router-dom'

export default function NavBar() {
  return (
    <header className="nav">
      <span className="nav-title">Animalia</span>
      <nav className="nav-links">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
          Tree of Life 3D
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
