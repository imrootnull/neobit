/**
 * Central icon registry — maps analytic keys and categories to Lucide icons.
 * All icons in NeoBit use Lucide React. Zero emojis.
 */
import {
  Eye, User, Users, Car, Truck, Hash, ShieldAlert, Shield,
  ArrowRightLeft, Clock, Lock, HardHat, AlertTriangle, Shirt,
  Flame, Wind, Biohazard, AlertOctagon, Package, ArrowLeft,
  ScanText, Gauge, ParkingSquare, Navigation, ParkingSquareOff,
  AlignJustify, Activity, Timer, DoorOpen, LayoutGrid,
  Droplets, HeartPulse, Sticker, Siren, Construction,
  MoveUp, Circle, Settings2, Crosshair, CreditCard,
  UserX, PenLine, Plane, Baby, EyeOff, Trash2,
  Brain, Zap, TrendingUp, Smartphone, BedDouble,
  ScanFace, Cat, Bot, Camera, Bell, Search, Monitor,
  BarChart2, Cpu, Wifi, WifiOff, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Plus, Upload, Pencil, X,
  Check, Info, Cloud, Webhook, Link, Filter, CheckCheck,
  Maximize2, LayoutTemplate, Map, Thermometer,
  Fingerprint, Smile, ShieldCheck
} from 'lucide-react';

// ─── Custom PPE SVG Icons ─────────────────────────────────────────────────────
// Inline SVG components — no emojis, fully styled via color prop

const SvgWrap = ({ size = 18, children }: { size?: number; children: React.ReactNode }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size} height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

export const IcoHelmet = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Hard hat: dome + brim */}
    <path d="M4 14c0-4.418 3.582-8 8-8s8 3.582 8 8" />
    <line x1="2" y1="14" x2="22" y2="14" />
    <line x1="12" y1="6" x2="12" y2="4" />
    <rect x="8" y="14" width="8" height="3" rx="1" />
  </SvgWrap>
);

export const IcoVest = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Safety vest: V-collar + side panels */}
    <path d="M8 3 L4 8 L4 20 L20 20 L20 8 L16 3" />
    <path d="M8 3 L12 10 L16 3" />
    <line x1="4" y1="12" x2="8" y2="12" />
    <line x1="16" y1="12" x2="20" y2="12" />
  </SvgWrap>
);

export const IcoGloves = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Work glove: palm + 3 fingers */}
    <path d="M6 10 L6 5 Q6 3 8 3 Q10 3 10 5 L10 8" />
    <path d="M10 8 L10 4 Q10 2.5 11.5 2.5 Q13 2.5 13 4 L13 8" />
    <path d="M13 8 L13 5 Q13 3.5 14.5 3.5 Q16 3.5 16 5 L16 9" />
    <path d="M6 10 Q4 10 4 13 L4 17 Q4 21 9 21 L15 21 Q18 21 18 17 L18 9 L16 9" />
  </SvgWrap>
);

export const IcoGoggles = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Safety goggles: two lenses + strap */}
    <line x1="2" y1="12" x2="6" y2="12" />
    <rect x="6" y="9" width="5" height="6" rx="2" />
    <rect x="13" y="9" width="5" height="6" rx="2" />
    <line x1="11" y1="12" x2="13" y2="12" />
    <line x1="18" y1="12" x2="22" y2="12" />
  </SvgWrap>
);

export const IcoMask = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Face mask: curved rectangle + ear loops */}
    <path d="M5 10 Q5 7 12 7 Q19 7 19 10 L19 15 Q19 18 12 18 Q5 18 5 15 Z" />
    <line x1="5" y1="12" x2="2" y2="11" />
    <line x1="5" y1="14" x2="2" y2="14" />
    <line x1="19" y1="12" x2="22" y2="11" />
    <line x1="19" y1="14" x2="22" y2="14" />
    <line x1="8" y1="13" x2="16" y2="13" />
  </SvgWrap>
);

export const IcoBoots = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Safety boot: shaft + sole */}
    <path d="M8 3 L8 14 Q8 16 10 17 L18 17 L18 19 L6 19 Q4 19 4 17 Q4 15 6 15 L6 14 L6 3 Z" />
    <line x1="6" y1="8" x2="8" y2="8" />
  </SvgWrap>
);

export const IcoOveralls = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Coverall: bib + legs */}
    <rect x="8" y="3" width="8" height="5" rx="1" />
    <path d="M6 8 L4 21 L10 21 L12 14 L14 21 L20 21 L18 8 Z" />
    <line x1="8" y1="3" x2="6" y2="8" />
    <line x1="16" y1="3" x2="18" y2="8" />
  </SvgWrap>
);

export const IcoHarness = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Safety harness: shoulder + waist straps + D-ring */}
    <circle cx="12" cy="5" r="2" />
    <path d="M12 7 L12 13" />
    <path d="M12 10 L7 7" />
    <path d="M12 10 L17 7" />
    <path d="M7 7 L6 14 L9 14" />
    <path d="M17 7 L18 14 L15 14" />
    <path d="M9 14 L9 20" />
    <path d="M15 14 L15 20" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </SvgWrap>
);

export const IcoEarProtector = ({ size = 18 }: { size?: number }) => (
  <SvgWrap size={size}>
    {/* Hearing protection: headband + two ear cups */}
    <path d="M6 12 Q6 5 12 5 Q18 5 18 12" />
    <rect x="3" y="11" width="5" height="6" rx="2.5" />
    <rect x="16" y="11" width="5" height="6" rx="2.5" />
  </SvgWrap>
);

export const PPE_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  helmet:        IcoHelmet,
  vest:          IcoVest,
  gloves:        IcoGloves,
  goggles:       IcoGoggles,
  mask:          IcoMask,
  shoes:         IcoBoots,
  overalls:      IcoOveralls,
  harness:       IcoHarness,
  ear_protector: IcoEarProtector,
};

// ─── Analytic icons by key ────────────────────────────────────────────────────
export const ANALYTIC_ICONS = {
  // Detection
  person_detection:   User,
  vehicle_detection:  Car,

  // Counting
  person_counting:    Users,
  vehicle_counting:   Truck,

  // Security / Perimeter
  intrusion_detection: ShieldAlert,
  line_crossing:       ArrowRightLeft,
  perimeter_guard:     Shield,
  loitering_detection: Clock,
  theft_detection:     Lock,
  tailgating:          UserX,
  vandalism_detection: PenLine,
  drone_detection:     Plane,
  unattended_child:    Baby,
  weapon_detection:    Crosshair,
  atm_security:        CreditCard,

  // Safety / EPP
  epp_detection:       HardHat,
  fall_detection:      AlertTriangle,
  uniform_compliance:  Shirt,
  working_at_heights:  MoveUp,
  mask_detection:      Sticker,
  social_distancing:   ArrowRightLeft,
  hand_hygiene:        Droplets,
  forklift_safety:     Construction,
  confined_space:      Circle,
  spill_detection:     Droplets,
  equipment_tamper:    Settings2,

  // Fire & Hazard
  fire_detection:      Flame,
  smoke_detection:     Wind,
  hazmat_detection:    Biohazard,

  // Behavior
  behavior_detection:  AlertOctagon,
  crowd_detection:     Users,
  abandoned_object:    Package,
  wrong_direction:     ArrowLeft,

  // Traffic / Smart City
  lpr_recognition:     ScanText,
  vehicle_speed:       Gauge,
  parking_occupancy:   ParkingSquare,
  traffic_flow:        Navigation,
  illegal_parking:     ParkingSquareOff,

  // Retail
  queue_management:    AlignJustify,
  heat_map:            Thermometer,
  dwell_analysis:      Timer,
  customer_counting:   DoorOpen,
  shelf_monitoring:    LayoutGrid,

  // Health
  patient_fall:        HeartPulse,
  medical_emergency:   Siren,

  // Privacy
  face_blur:           EyeOff,
  data_retention:      Trash2,

  // AI Advanced
  anomaly_detection:   Brain,
  zero_shot_detection: Zap,
  predictive_alert:    TrendingUp,
  phone_distraction:   Smartphone,
  driver_fatigue:      BedDouble,
  facial_recognition:  ScanFace,
  animal_detection:    Cat,

  // Custom
  custom_detection:    Bot,

  // Facial AI
  face_detection:        ScanFace,
  face_recognition:      Fingerprint,
  face_blacklist:        UserX,
  liveness_detection:    ShieldCheck,
  age_gender_estimation: Users,
  facial_search:         Search,
  emotion_detection:     Smile,
  face_mask_access:      Shield,
};

// ─── Category icons ───────────────────────────────────────────────────────────
export const CATEGORY_ICONS = {
  detection:   Eye,
  counting:    Hash,
  safety:      HardHat,
  security:    Shield,
  fire:        Flame,
  behavior:    AlertOctagon,
  traffic:     Navigation,
  retail:      LayoutGrid,
  health:      HeartPulse,
  industrial:  Construction,
  privacy:     EyeOff,
  ai_advanced: Brain,
  custom:      Bot,
  facial_ai:   ScanFace,
};

// ─── Severity icons ───────────────────────────────────────────────────────────
export const SEVERITY_ICONS = {
  critical: XCircle,
  high:     AlertTriangle,
  medium:   AlertOctagon,
  low:      Info,
};

// ─── Severity colors ──────────────────────────────────────────────────────────
export const SEVERITY_COLORS = {
  critical: 'var(--accent-red)',
  high:     'var(--accent-amber)',
  medium:   'var(--accent-blue)',
  low:      'var(--text-muted)',
};

// ─── Helper: get analytic icon component ─────────────────────────────────────
export function getAnalyticIcon(key, size = 16) {
  const Icon = ANALYTIC_ICONS[key] || Eye;
  return <Icon size={size} />;
}

export function getCategoryIcon(key, size = 16) {
  const Icon = CATEGORY_ICONS[key] || Eye;
  return <Icon size={size} />;
}

export function getSeverityIcon(severity, size = 14) {
  const Icon = SEVERITY_ICONS[severity] || Info;
  const color = SEVERITY_COLORS[severity] || 'var(--text-muted)';
  return <Icon size={size} style={{ color }} />;
}

// Re-export all icons for convenience
export {
  Eye, User, Users, Car, Truck, Hash, ShieldAlert, Shield,
  ArrowRightLeft, Clock, Lock, HardHat, AlertTriangle, Shirt,
  Flame, Wind, Biohazard, AlertOctagon, Package, ArrowLeft,
  ScanText, Gauge, ParkingSquare, Navigation, ParkingSquareOff,
  AlignJustify, Activity, Timer, DoorOpen, LayoutGrid,
  Droplets, HeartPulse, Sticker, Siren, Construction,
  MoveUp, Circle, Settings2, Crosshair, CreditCard,
  UserX, PenLine, Plane, Baby, EyeOff, Trash2,
  Brain, Zap, TrendingUp, Smartphone, BedDouble,
  ScanFace, Cat, Bot, Camera, Bell, Search, Monitor,
  BarChart2, Cpu, Wifi, WifiOff, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Plus, Upload, Pencil, X,
  Check, Info, Cloud, Webhook, Link, Filter, CheckCheck,
  Maximize2, LayoutTemplate, Map, Thermometer,
  Fingerprint, Smile, ShieldCheck
};
