"""
Analytics Registry — defines all available analytics modules.
Each analytic is a plugin that can be enabled per camera.
Adding a new analytic = add an entry here + implement the class.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnalyticCategory(str, Enum):
    DETECTION   = "detection"
    COUNTING    = "counting"
    SAFETY      = "safety"
    SECURITY    = "security"
    FIRE        = "fire"
    BEHAVIOR    = "behavior"
    CUSTOM      = "custom"
    # New sectors
    TRAFFIC     = "traffic"       # Smart city / logistics
    RETAIL      = "retail"        # Retail analytics
    HEALTH      = "health"        # Healthcare / hospitals
    INDUSTRIAL  = "industrial"    # Heavy industry / oil & gas
    PRIVACY     = "privacy"       # GDPR / data protection
    AI_ADVANCED = "ai_advanced"   # Differentiating AI features
    FACIAL_AI   = "facial_ai"     # Full facial AI suite


@dataclass
class AnalyticDefinition:
    key: str
    label: str
    description: str
    category: AnalyticCategory
    icon: str
    default_config: dict = field(default_factory=dict)
    model_required: str | None = None   # model file key
    phase: int = 1                       # development phase


ANALYTICS_CATALOG: list[AnalyticDefinition] = [

    # ── Detection ──────────────────────────────────────────────────────────
    AnalyticDefinition(
        key="person_detection",
        label="Detección de personas",
        description="Detecta y localiza personas en la escena en tiempo real.",
        category=AnalyticCategory.DETECTION,
        icon="user",
        default_config={"confidence": 0.5, "min_size": 30},
        model_required="mobilenet_ssd",
        phase=2,
    ),
    AnalyticDefinition(
        key="vehicle_detection",
        label="Detección de vehículos",
        description="Detecta autos, camiones, motocicletas y bicicletas.",
        category=AnalyticCategory.DETECTION,
        icon="car",
        default_config={"confidence": 0.5, "classes": ["car","truck","motorcycle","bicycle"]},
        model_required="yolov8n",
        phase=2,
    ),

    # ── Counting ───────────────────────────────────────────────────────────
    AnalyticDefinition(
        key="person_counting",
        label="Conteo de personas",
        description="Cuenta personas en zonas definidas o cruzando una línea.",
        category=AnalyticCategory.COUNTING,
        icon="hash",
        default_config={"zone": None, "line": None, "alert_threshold": 10},
        model_required="yolov8n",
        phase=2,
    ),
    AnalyticDefinition(
        key="vehicle_counting",
        label="Conteo de vehículos",
        description="Cuenta vehículos que cruzan una línea virtual o circulan en una zona.",
        category=AnalyticCategory.COUNTING,
        icon="truck",
        default_config={"line": None, "classes": ["car","truck"]},
        model_required="yolov8n",
        phase=2,
    ),

    # ── Perimeter & Security ───────────────────────────────────────────────
    AnalyticDefinition(
        key="intrusion_detection",
        label="Detección de intrusión",
        description="Alerta cuando una persona o vehículo entra a una zona restringida.",
        category=AnalyticCategory.SECURITY,
        icon="shield-alert",
        default_config={"zone_polygon": [], "dwell_time": 0, "classes": ["person"]},
        model_required="yolov8n",
        phase=2,
    ),
    AnalyticDefinition(
        key="line_crossing",
        label="Cruce de línea virtual",
        description="Detecta cuando un objeto cruza una línea definida en cualquier dirección.",
        category=AnalyticCategory.SECURITY,
        icon="arrow-right-left",
        default_config={"line": [], "direction": "both", "classes": ["person","car"]},
        model_required="yolov8n",
        phase=2,
    ),
    AnalyticDefinition(
        key="perimeter_guard",
        label="Guardia perimetral",
        description="Monitoreo continuo de perímetro con alertas por horario.",
        category=AnalyticCategory.SECURITY,
        icon="shield",
        default_config={"zones": [], "schedule": {"start": "22:00", "end": "06:00"}},
        model_required="yolov8n",
        phase=2,
    ),
    AnalyticDefinition(
        key="loitering_detection",
        label="Merodeo / permanencia prolongada",
        description="Alerta cuando una persona permanece en una zona más del tiempo permitido.",
        category=AnalyticCategory.SECURITY,
        icon="clock",
        default_config={"zone_polygon": [], "max_dwell_seconds": 30},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="theft_detection",
        label="Detección de robo",
        description="Detecta comportamientos asociados al robo y sustracción de objetos.",
        category=AnalyticCategory.SECURITY,
        icon="lock",
        default_config={"confidence": 0.6},
        model_required="yolov8n",
        phase=5,
    ),

    # ── Safety / EPP ───────────────────────────────────────────────────────
    AnalyticDefinition(
        key="epp_detection",
        label="EPP Industrial",
        description="Detecta uso correcto de casco, chaleco, botas y guantes en zonas industriales.",
        category=AnalyticCategory.SAFETY,
        icon="hard-hat",
        default_config={
            "required_ppe": ["helmet","vest","boots"],
            "confidence": 0.55,
            "zone_polygon": [],
        },
        model_required="ppe_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="fall_detection",
        label="Detección de caídas",
        description="Detecta caídas de personas en cualquier área usando estimación de pose.",
        category=AnalyticCategory.SAFETY,
        icon="alert-triangle",
        default_config={"confidence": 0.6, "confirmation_frames": 5},
        model_required="yolov8n_pose",
        phase=3,
    ),
    AnalyticDefinition(
        key="uniform_compliance",
        label="Cumplimiento de uniforme (custom)",
        description="Verifica que el personal use el uniforme correcto de la empresa cliente.",
        category=AnalyticCategory.SAFETY,
        icon="shirt",
        default_config={"client_model": None, "confidence": 0.6},
        model_required=None,   # Uses custom client model
        phase=4,
    ),

    # ── Fire & Hazard ──────────────────────────────────────────────────────
    AnalyticDefinition(
        key="fire_detection",
        label="Detección de fuego",
        description="Detecta llamas y fuego activo en tiempo real con alta sensibilidad.",
        category=AnalyticCategory.FIRE,
        icon="flame",
        default_config={"confidence": 0.5, "alert_immediately": True},
        model_required="fire_smoke_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="smoke_detection",
        label="Detección de humo",
        description="Detecta presencia de humo antes de que el fuego sea visible.",
        category=AnalyticCategory.FIRE,
        icon="wind",
        default_config={"confidence": 0.45, "alert_immediately": True},
        model_required="fire_smoke_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="hazmat_detection",
        label="Materiales peligrosos / derrames",
        description="Detecta derrames o presencia de materiales peligrosos.",
        category=AnalyticCategory.FIRE,
        icon="biohazard",
        default_config={"confidence": 0.55},
        model_required=None,   # Custom per-client
        phase=5,
    ),

    # ── Behavior ───────────────────────────────────────────────────────────
    AnalyticDefinition(
        key="behavior_detection",
        label="Comportamiento hostil / pelea",
        description="Detecta altercados físicos, peleas y comportamiento agresivo.",
        category=AnalyticCategory.BEHAVIOR,
        icon="alert-octagon",
        default_config={"confidence": 0.6, "confirmation_frames": 8},
        model_required="yolov8n_pose",
        phase=5,
    ),
    AnalyticDefinition(
        key="crowd_detection",
        label="Detección de multitudes / aglomeraciones",
        description="Alerta cuando la densidad de personas supera un umbral en una zona.",
        category=AnalyticCategory.BEHAVIOR,
        icon="users",
        default_config={"max_density": 5, "zone_polygon": []},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="abandoned_object",
        label="Objeto abandonado",
        description="Detecta objetos dejados sin atención en zonas de interés.",
        category=AnalyticCategory.BEHAVIOR,
        icon="package",
        default_config={"dwell_seconds": 60, "zone_polygon": []},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="wrong_direction",
        label="Dirección incorrecta / contraflujo",
        description="Detecta personas o vehículos que se mueven en dirección incorrecta.",
        category=AnalyticCategory.BEHAVIOR,
        icon="arrow-left",
        default_config={"allowed_direction": "right", "zone_polygon": []},
        model_required="yolov8n",
        phase=4,
    ),

    # ── License Plate Recognition ──────────────────────────────────────────
    AnalyticDefinition(
        key="lpr_recognition",
        label="Reconocimiento de placas (LPR/ANPR)",
        description="Lee placas vehiculares en tiempo real. Control de acceso, listas negras/blancas, registro de entradas y salidas.",
        category=AnalyticCategory.TRAFFIC,
        icon="scan-text",
        default_config={"whitelist": [], "blacklist": [], "confidence": 0.75, "record_all": True},
        model_required="lpr_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="vehicle_speed",
        label="Estimación de velocidad vehicular",
        description="Estima velocidad de vehículos en km/h. Alertas por exceso de velocidad en estacionamientos, plantas o vías internas.",
        category=AnalyticCategory.TRAFFIC,
        icon="gauge",
        default_config={"max_speed_kmh": 20, "calibration_meters": 10},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="parking_occupancy",
        label="Ocupación de estacionamiento",
        description="Monitorea espacios de estacionamiento libres y ocupados en tiempo real. Genera mapa de calor de disponibilidad.",
        category=AnalyticCategory.TRAFFIC,
        icon="parking-square",
        default_config={"spaces": [], "alert_full": True},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="traffic_flow",
        label="Análisis de flujo vehicular",
        description="Mide densidad de tráfico, tiempos de paso y congestión. Útil para logística, plantas y ciudades inteligentes.",
        category=AnalyticCategory.TRAFFIC,
        icon="navigation",
        default_config={"zones": [], "interval_seconds": 60},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="illegal_parking",
        label="Estacionamiento indebido",
        description="Detecta vehículos estacionados en zonas prohibidas, rampas de emergencia o accesos bloqueados.",
        category=AnalyticCategory.TRAFFIC,
        icon="parking-square-off",
        default_config={"forbidden_zones": [], "tolerance_seconds": 30},
        model_required="yolov8n",
        phase=4,
    ),

    # ── Retail Analytics ───────────────────────────────────────────────────
    AnalyticDefinition(
        key="queue_management",
        label="Gestión de filas / colas",
        description="Mide longitud de colas, tiempo de espera promedio y alerta cuando supera umbral. Retail, bancos, gobierno.",
        category=AnalyticCategory.RETAIL,
        icon="align-justify",
        default_config={"zone": [], "max_wait_minutes": 5, "max_queue_length": 8},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="heat_map",
        label="Mapa de calor / zonas de tráfico",
        description="Genera mapas de calor de movimiento de personas. Optimización de layouts en tiendas, museos, eventos.",
        category=AnalyticCategory.RETAIL,
        icon="thermometer",
        default_config={"interval_seconds": 300, "decay": 0.95},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="dwell_analysis",
        label="Análisis de permanencia",
        description="Mide cuánto tiempo pasan las personas en zonas de interés (exhibidores, departamentos, cajas).",
        category=AnalyticCategory.RETAIL,
        icon="timer",
        default_config={"zones": [], "min_dwell_seconds": 5},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="customer_counting",
        label="Aforo y conteo de clientes",
        description="Conteo de entradas y salidas para control de aforo. Cumplimiento regulatorio y analítica de tráfico.",
        category=AnalyticCategory.RETAIL,
        icon="door-open",
        default_config={"entry_line": [], "exit_line": [], "max_capacity": 100},
        model_required="yolov8n",
        phase=2,
    ),
    AnalyticDefinition(
        key="shelf_monitoring",
        label="Monitoreo de estantes (desabasto)",
        description="Detecta estantes vacíos o con bajo inventario en supermercados y tiendas. Alertas automáticas al personal.",
        category=AnalyticCategory.RETAIL,
        icon="layout-grid",
        default_config={"confidence": 0.6, "empty_threshold": 0.2},
        model_required=None,  # Custom per-client
        phase=5,
    ),

    # ── Healthcare ─────────────────────────────────────────────────────────
    AnalyticDefinition(
        key="hand_hygiene",
        label="Higiene de manos (dispensador)",
        description="Verifica que el personal use dispensadores de gel antes de entrar a áreas críticas. Hospitales, cocinas, laboratorios.",
        category=AnalyticCategory.HEALTH,
        icon="droplets",
        default_config={"dispenser_zone": [], "entry_zone": [], "confidence": 0.65},
        model_required="yolov8n_pose",
        phase=4,
    ),
    AnalyticDefinition(
        key="patient_fall",
        label="Caída de paciente (hospital)",
        description="Detecta caídas de pacientes en habitaciones, pasillos y baños hospitalarios con alta sensibilidad.",
        category=AnalyticCategory.HEALTH,
        icon="heart-pulse",
        default_config={"sensitivity": "high", "alert_immediately": True},
        model_required="yolov8n_pose",
        phase=3,
    ),
    AnalyticDefinition(
        key="mask_detection",
        label="Detección de cubrebocas / mascarilla",
        description="Verifica uso de mascarillas en áreas donde es obligatorio: salas limpias, hospitales, industria alimentaria.",
        category=AnalyticCategory.HEALTH,
        icon="sticker",
        default_config={"confidence": 0.65, "zone": []},
        model_required="ppe_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="social_distancing",
        label="Distanciamiento social / proximidad",
        description="Alerta cuando personas están más cerca de la distancia mínima configurada. Salas limpias, quirófanos, producción.",
        category=AnalyticCategory.HEALTH,
        icon="arrow-right-left",
        default_config={"min_distance_cm": 150, "zone": []},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="medical_emergency",
        label="Detección de emergencia médica",
        description="Persona inconsciente en el suelo por tiempo prolongado sin respuesta. Diferencia de descanso/caída intencional.",
        category=AnalyticCategory.HEALTH,
        icon="siren",
        default_config={"no_movement_seconds": 10, "alert_immediately": True},
        model_required="yolov8n_pose",
        phase=4,
    ),

    # ── Industrial / Oil & Gas ─────────────────────────────────────────────
    AnalyticDefinition(
        key="forklift_safety",
        label="Seguridad con montacargas",
        description="Alerta cuando personas están en zona de operación de montacargas o grúas. Previene accidentes críticos.",
        category=AnalyticCategory.INDUSTRIAL,
        icon="construction",
        default_config={"safety_zone": [], "min_distance_px": 100},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="working_at_heights",
        label="Trabajo en alturas",
        description="Verifica arnés y equipo de protección en trabajos en altura. Detecta personas sin equipo en zonas elevadas.",
        category=AnalyticCategory.INDUSTRIAL,
        icon="move-up",
        default_config={"height_zones": [], "required_ppe": ["harness"]},
        model_required="ppe_yolov8",
        phase=4,
    ),
    AnalyticDefinition(
        key="confined_space",
        label="Espacios confinados",
        description="Monitorea entradas y salidas de espacios confinados. Alerta si persona queda atrapada o no sale en tiempo esperado.",
        category=AnalyticCategory.INDUSTRIAL,
        icon="circle",
        default_config={"entry_zone": [], "max_time_minutes": 30, "require_buddy": True},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="spill_detection",
        label="Detección de derrames",
        description="Detecta derrames de líquidos en pisos. Previene resbalones y accidentes. Útil en plantas y almacenes.",
        category=AnalyticCategory.INDUSTRIAL,
        icon="droplets",
        default_config={"confidence": 0.55, "zone": []},
        model_required=None,
        phase=5,
    ),
    AnalyticDefinition(
        key="equipment_tamper",
        label="Manipulación de equipos críticos",
        description="Detecta acceso no autorizado o manipulación de maquinaria, tableros eléctricos o equipos críticos.",
        category=AnalyticCategory.INDUSTRIAL,
        icon="settings-2",
        default_config={"equipment_zones": [], "authorized_ids": []},
        model_required="yolov8n",
        phase=4,
    ),

    # ── Security & Banking ─────────────────────────────────────────────────
    AnalyticDefinition(
        key="weapon_detection",
        label="Detección de armas",
        description="Detecta armas de fuego, cuchillos y objetos peligrosos. Escuelas, bancos, aeropuertos, eventos masivos.",
        category=AnalyticCategory.SECURITY,
        icon="crosshair",
        default_config={"confidence": 0.7, "alert_immediately": True, "classes": ["gun","knife"]},
        model_required="weapon_yolov8",
        phase=4,
    ),
    AnalyticDefinition(
        key="atm_security",
        label="Seguridad en ATM",
        description="Detecta comportamiento sospechoso en cajeros: merodeo prolongado, cobertura de cámara, skimming físico.",
        category=AnalyticCategory.SECURITY,
        icon="credit-card",
        default_config={"dwell_seconds": 45, "zone": [], "camera_cover_detect": True},
        model_required="yolov8n",
        phase=4,
    ),
    AnalyticDefinition(
        key="tailgating",
        label="Acceso no autorizado (tailgating)",
        description="Detecta cuando más personas de las autorizadas cruzan una puerta de acceso controlado.",
        category=AnalyticCategory.SECURITY,
        icon="user-x",
        default_config={"entry_line": [], "max_simultaneous": 1},
        model_required="yolov8n",
        phase=3,
    ),
    AnalyticDefinition(
        key="vandalism_detection",
        label="Detección de vandalismo / grafiti",
        description="Detecta actos de vandalismo, grafiti y daño a propiedad. Espacios públicos, transporte, infraestructura.",
        category=AnalyticCategory.SECURITY,
        icon="pen-line",
        default_config={"confidence": 0.6, "zone": []},
        model_required=None,
        phase=5,
    ),
    AnalyticDefinition(
        key="drone_detection",
        label="Detección de drones",
        description="Detecta drones no autorizados sobre infraestructura crítica, plantas, aeropuertos o instalaciones privadas.",
        category=AnalyticCategory.SECURITY,
        icon="plane",
        default_config={"confidence": 0.65, "alert_immediately": True},
        model_required="drone_yolov8",
        phase=5,
    ),
    AnalyticDefinition(
        key="unattended_child",
        label="Menor de edad sin acompañante",
        description="Detecta niños solos en zonas de riesgo: estacionamientos, accesos, áreas industriales. Centros comerciales, colegios.",
        category=AnalyticCategory.SECURITY,
        icon="baby",
        default_config={"zone": [], "age_threshold": "child", "alone_seconds": 30},
        model_required="yolov8n",
        phase=5,
    ),

    # ── Privacy & Compliance (diferenciador clave) ─────────────────────────
    AnalyticDefinition(
        key="face_blur",
        label="Anonimización automática (GDPR/LFPDPPP)",
        description="Difumina rostros automáticamente en grabaciones para cumplimiento GDPR. Esencial para clientes europeos y corporativos.",
        category=AnalyticCategory.PRIVACY,
        icon="eye-off",
        default_config={"enabled": False, "blur_strength": 25, "exempt_zones": []},
        model_required="yolov8n_face",
        phase=3,
    ),
    AnalyticDefinition(
        key="data_retention",
        label="Gestión automática de retención de datos",
        description="Elimina grabaciones automáticamente según política de retención configurable. Cumplimiento legal garantizado.",
        category=AnalyticCategory.PRIVACY,
        icon="trash-2",
        default_config={"retention_days": 30, "auto_delete": True},
        model_required=None,
        phase=2,
    ),

    # ── Advanced AI Differentiators ────────────────────────────────────────
    AnalyticDefinition(
        key="anomaly_detection",
        label="Detección de anomalías (sin entrenamiento)",
        description="Detecta situaciones anómalas sin necesidad de etiquetas de entrenamiento. Aprende el comportamiento 'normal' y alerta sobre lo inusual.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="brain",
        default_config={"learning_period_hours": 48, "sensitivity": 0.8},
        model_required=None,
        phase=5,
    ),
    AnalyticDefinition(
        key="zero_shot_detection",
        label="Detección zero-shot (CLIP)",
        description="Detecta cualquier objeto o situación describiendo con texto — sin necesidad de entrenar un modelo. Powered by CLIP.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="zap",
        default_config={"queries": [], "confidence": 0.6, "sample_interval": 1.0},
        model_required=None,
        phase=4,
    ),
    AnalyticDefinition(
        key="predictive_alert",
        label="Alertas predictivas (IA temporal)",
        description="Analiza patrones de comportamiento para predecir incidentes ANTES de que ocurran. IA temporal sobre historial de eventos.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="trending-up",
        default_config={"lookback_minutes": 10, "threshold": 0.75},
        model_required=None,
        phase=5,
    ),
    AnalyticDefinition(
        key="phone_distraction",
        label="Uso de teléfono / distracción",
        description="Detecta operadores, guardias o conductores usando el celular mientras trabajan. Reducción de accidentes por distracción.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="smartphone",
        default_config={"confidence": 0.65, "zone": [], "roles": ["operator","guard","driver"]},
        model_required="yolov8n_pose",
        phase=4,
    ),
    AnalyticDefinition(
        key="driver_fatigue",
        label="Detección de fatiga en conductores",
        description="Detecta signos de somnolencia en conductores: cabeza caída, ojos cerrados. Logística, transporte de carga.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="bed-double",
        default_config={"confidence": 0.7, "alert_immediately": True},
        model_required="yolov8n_face",
        phase=5,
    ),
    AnalyticDefinition(
        key="facial_recognition",
        label="Reconocimiento facial",
        description="Identifica personas registradas en la base de datos local de NeoBit. Control de acceso, listas blancas/negras y registro de presencia.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="scan-face",
        default_config={"mode": "whitelist", "confidence": 0.85, "database": "local"},
        model_required="face_recognition_model",
        phase=4,
    ),
    AnalyticDefinition(
        key="animal_detection",
        label="Detección de animales / fauna",
        description="Detecta animales en perímetros agrícolas, zoológicos, granjas o áreas industriales. Alerta por especie.",
        category=AnalyticCategory.AI_ADVANCED,
        icon="cat",
        default_config={"classes": ["dog","cat","cow","horse","bird"], "zone": []},
        model_required="yolov8n",
        phase=4,
    ),

    # ── Facial AI Suite ──────────────────────────────────────────────────────
    AnalyticDefinition(
        key="face_detection",
        label="Detección facial",
        description="Detecta y localiza rostros humanos en escena. Base para todas las analíticas faciales. Alta velocidad, baja latencia.",
        category=AnalyticCategory.FACIAL_AI,
        icon="scan-face",
        default_config={"confidence": 0.6, "min_face_size": 30, "max_faces": 50},
        model_required="face_yolov8",
        phase=3,
    ),
    AnalyticDefinition(
        key="face_recognition",
        label="Reconocimiento facial",
        description="Identifica personas registradas (lista blanca). Acceso automático, asistencia y alerta por persona no autorizada.",
        category=AnalyticCategory.FACIAL_AI,
        icon="fingerprint",
        default_config={
            "mode": "whitelist",           # whitelist | blacklist | all
            "confidence": 0.80,
            "database": "local",           # NeoBit internal face database
            "alert_unknown": True,
            "save_snapshots": True,
        },
        model_required="face_recognition_model",
        phase=3,
    ),
    AnalyticDefinition(
        key="face_blacklist",
        label="Lista negra facial (persona no grata)",
        description="Alerta inmediata cuando una persona de la lista negra es detectada en cámara. Seguridad bancaria, casinos, eventos.",
        category=AnalyticCategory.FACIAL_AI,
        icon="user-x",
        default_config={
            "confidence": 0.82,
            "alert_immediately": True,
            "save_snapshots": True,
            "notify_security": True,
        },
        model_required="face_recognition_model",
        phase=3,
    ),
    AnalyticDefinition(
        key="liveness_detection",
        label="Detección de vivacidad (anti-spoofing)",
        description="Distingue rostros reales de fotos, videos o máscaras. Evita fraudes de identidad en acceso facial.",
        category=AnalyticCategory.FACIAL_AI,
        icon="shield-check",
        default_config={"confidence": 0.85, "check_blink": True, "check_depth": False},
        model_required="liveness_model",
        phase=4,
    ),
    AnalyticDefinition(
        key="age_gender_estimation",
        label="Estimación de edad y género",
        description="Estima rango de edad y género de personas detectadas. Análisis demográfico para retail, publicidad y eventos.",
        category=AnalyticCategory.FACIAL_AI,
        icon="users",
        default_config={
            "age_groups": ["child","teen","adult","senior"],
            "confidence": 0.65,
            "anonymous_mode": True,       # No store identity, only stats
        },
        model_required="age_gender_model",
        phase=4,
    ),
    AnalyticDefinition(
        key="facial_search",
        label="Búsqueda facial por foto",
        description="Busca en el historial de video a una persona específica usando una foto de referencia. Investigación forense, seguridad.",
        category=AnalyticCategory.FACIAL_AI,
        icon="search",
        default_config={"confidence": 0.78, "search_days_back": 30},
        model_required="face_recognition_model",
        phase=4,
    ),
    AnalyticDefinition(
        key="emotion_detection",
        label="Detección de emociones",
        description="Detecta emociones básicas (enojo, miedo, alegría, sorpresa, tristeza). Atención al cliente, seguridad, UX.",
        category=AnalyticCategory.FACIAL_AI,
        icon="smile",
        default_config={"emotions": ["anger","fear","neutral","happy","sad"], "alert_on": ["anger","fear"]},
        model_required="emotion_model",
        phase=5,
    ),
    AnalyticDefinition(
        key="face_mask_access",
        label="Control de acceso facial con cubrebocas",
        description="Reconoce identidad incluso con cubrebocas usando modelos adaptados. Hospitales, fábricas, áreas clínicas.",
        category=AnalyticCategory.FACIAL_AI,
        icon="shield",
        default_config={"confidence": 0.75, "require_mask": True},
        model_required="masked_face_model",
        phase=5,
    ),
]

# Fast lookup by key
ANALYTICS_BY_KEY: dict[str, AnalyticDefinition] = {a.key: a for a in ANALYTICS_CATALOG}


def get_catalog_by_category() -> dict[str, list[dict]]:
    """Return catalog grouped by category for the UI."""
    result: dict[str, list] = {}
    for a in ANALYTICS_CATALOG:
        cat = a.category.value
        if cat not in result:
            result[cat] = []
        result[cat].append({
            "key": a.key,
            "label": a.label,
            "description": a.description,
            "icon": a.icon,
            "category": cat,
            "default_config": a.default_config,
            "phase": a.phase,
        })
    return result
