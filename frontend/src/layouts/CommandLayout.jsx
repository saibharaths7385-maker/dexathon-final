import { useEffect, useRef, useState } from 'react'
import {
  Activity,
  Award,
  Boxes,
  ChevronRight,
  CircleDot,
  FlaskConical,
  Gauge,
  Layers,
  LayoutDashboard,
  Menu,
  Plane,
  Satellite,
  ShieldCheck,
  X,
} from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

const operations = [
  ['/', 'Dashboard', LayoutDashboard],
  ['/judge-demo', 'Judge Demo', Award],
  ['/architecture', 'Architecture', Layers],
  ['/live-mission', 'Live Mission', Plane],
  ['/telemetry', 'Telemetry', Activity],
  ['/fleet', 'Fleet', Boxes],
  ['/digital-twin', 'Digital Twin', CircleDot],
  ['/replay', 'Replay', Activity],
  ['/diagnosis', 'Diagnosis', ShieldCheck],
  ['/analytics', 'Analytics', Gauge],
]

const engineering = [
  ['/health', 'Health Analysis', ShieldCheck],
  ['/validation', 'Validation', CircleDot],
  ['/experiments', 'Experiments', FlaskConical],
]

const titles = new Map([
  ...operations,
  ...engineering,
  ['/judge-demo', 'Judge Demo Mode'],
  ['/demo', 'Judge Demo Mode'],
  ['/architecture', 'Architecture & Digital Twin'],
].map(([path, label]) => [path, label]))

function NavigationLinks({ links, close }) {
  return links.map(([path, label, Icon]) => (
    <NavLink end={path === '/'} to={path} key={path} onClick={close}>
      <Icon aria-hidden="true" />
      <span>{label}</span>
      <ChevronRight aria-hidden="true" />
    </NavLink>
  ))
}

export default function CommandLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const menuRef = useRef(null)
  const closeRef = useRef(null)
  const { pathname } = useLocation()
  const closeNavigation = () => setMobileOpen(false)

  useEffect(() => {
    if (!mobileOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    const desktop = window.matchMedia('(min-width: 1025px)')
    const onResize = () => { if (desktop.matches) setMobileOpen(false) }
    document.addEventListener('keydown', onKeyDown)
    desktop.addEventListener('change', onResize)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      desktop.removeEventListener('change', onResize)
      menuRef.current?.focus()
    }
  }, [mobileOpen])

  return (
    <div className="command-shell">
      <a className="skip-link" href="#mission-content">Skip to content</a>
      {mobileOpen && (
        <button
          type="button"
          className="navigation-backdrop"
          aria-label="Close navigation"
          onClick={closeNavigation}
        />
      )}
      <aside id="mission-navigation" className={`sidebar ${mobileOpen ? 'open' : ''}`} aria-label="Mission control navigation">
        <div className="brand">
          <Satellite aria-hidden="true" />
          <div><b>SKYNEX <span className="brand-version">3.0</span></b><small>AEROSPACE ENGINE COMMAND</small></div>
          <button type="button" ref={closeRef} aria-label="Close navigation" onClick={closeNavigation}><X aria-hidden="true" /></button>
        </div>
        <div className="system-tag"><i /> PROTOTYPE · SYNTHETIC DATA</div>
        <nav aria-label="Mission operations">
          <span className="nav-label">MISSION OPERATIONS</span>
          <NavigationLinks links={operations} close={closeNavigation} />
        </nav>
        <nav className="engineering-nav" aria-label="Engineering tools">
          <span className="nav-label">ENGINEERING TOOLS</span>
          <NavigationLinks links={engineering} close={closeNavigation} />
        </nav>
        <footer><i /> RESEARCH DEMONSTRATOR<small>Not for flight clearance</small></footer>
      </aside>

      <main inert={mobileOpen ? '' : undefined}>
        <header className="topbar">
          <button type="button" ref={menuRef} className="menu" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="mission-navigation" onClick={() => setMobileOpen(true)}><Menu aria-hidden="true" /></button>
          <div><span>SKYNEX / UAV OPERATIONS /</span><h1 aria-live="polite">{titles.get(pathname) || 'Mission Control'}</h1></div>
          <div className="live"><Satellite size={14} aria-hidden="true" /><span>SIMULATION + API</span></div>
        </header>
        <div className="content" id="mission-content" tabIndex={-1}>{children}</div>
      </main>
    </div>
  )
}
