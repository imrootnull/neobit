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
