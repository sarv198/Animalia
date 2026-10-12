import { NavLink } from 'react-router-dom'
import logo from '../assets/reptilia-logo.png'

export default function NavBar() {
  return (
    <header className="nav">
      <img className="nav-logo" src={logo} alt="Reptilia" />
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
