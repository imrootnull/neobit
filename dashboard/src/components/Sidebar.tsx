import { NavLink } from 'react-router-dom';
import { useWS } from '../context/WSContext';
import {
  LayoutGrid, Search, Bell, Settings, Camera,
  Activity, Shield, Cpu, Radio, HardDrive
} from 'lucide-react';

const navItems = [
  { to: '/',           icon: LayoutGrid, label: 'Monitor'      },
  { to: '/events',     icon: Bell,       label: 'Eventos'      },
  { to: '/search',     icon: Search,     label: 'Busqueda IA'  },
  { to: '/analytics',  icon: Activity,   label: 'Analiticas'   },
  { to: '/cameras',    icon: Camera,     label: 'Camaras'      },
  { to: '/recording',  icon: HardDrive,  label: 'Grabacion'    },
  { to: '/settings',   icon: Settings,   label: 'Ajustes'      },
];

// NeoBit logotype — pure SVG, no emoji
function NeoBitLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="9" fill="url(#nb-grad)" />
      <circle cx="16" cy="13" r="5" stroke="white" strokeWidth="2" fill="none" />
      <circle cx="16" cy="13" r="2" fill="white" />
      <path d="M8 24 Q16 17 24 24" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
      <defs>
        <linearGradient id="nb-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export default function Sidebar() {
  const { status, streams } = useWS();
  const activeCams = streams.filter(s => s.connected).length;

  const statusLabel = {
    connected:    'Gateway conectado',
    connecting:   'Conectando...',
    disconnected: 'Sin conexión',
  }[status];

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-mark">
          <NeoBitLogo />
          <div>
            <div className="logo-text">NeoBit</div>
            <div className="logo-sub">AI Gateway</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="nav-section">Principal</div>
        {navItems.slice(0, 3).map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={16} className="nav-icon" />
            {label}
          </NavLink>
        ))}

        <div className="nav-section">Configuración</div>
        {navItems.slice(3).map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={16} className="nav-icon" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 12px', marginBottom: 6,
          fontSize: 12, color: 'var(--text-muted)',
        }}>
          <Camera size={13} />
          <span>{activeCams} / {streams.length} cámaras activas</span>
        </div>

        <div className="connection-status">
          <div className={`status-dot ${status}`} />
          <span style={{ flex: 1 }}>{statusLabel}</span>
          <Cpu size={12} style={{ opacity: 0.5 }} />
        </div>
      </div>
    </aside>
  );
}
