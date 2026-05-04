"""
Fall Detector — YOLOv8 Pose-based fall detection.

How it works:
1. YOLOv8 Pose detects 17 COCO keypoints per person (skeleton)
2. Body orientation is computed from shoulder-to-hip angle
3. A person is classified as "fallen" if:
   - Body angle is near horizontal (< 45° from floor)
   - OR shoulder/hip midpoints are at similar Y height
   - OR bounding box is wider than tall (w/h ratio > 1.2)
4. Skeleton is drawn on the frame with color-coded joints:
   - Green skeleton = standing
   - Red skeleton   = FALLEN (triggers event)

COCO keypoint indices:
  0=nose, 1=left_eye, 2=right_eye, 3=left_ear, 4=right_ear,
  5=left_shoulder, 6=right_shoulder, 7=left_elbow, 8=right_elbow,
  9=left_wrist, 10=right_wrist, 11=left_hip, 12=right_hip,
  13=left_knee, 14=right_knee, 15=left_ankle, 16=right_ankle
"""
import cv2
import math
import numpy as np
import threading
from typing import Optional
from loguru import logger

# ─── Skeleton definition ─────────────────────────────────────────────────────

SKELETON_CONNECTIONS = [
    # Head
    (0, 1), (0, 2), (1, 3), (2, 4),
    # Torso
    (5, 6), (5, 11), (6, 12), (11, 12),
    # Left arm
    (5, 7), (7, 9),
    # Right arm
    (6, 8), (8, 10),
    # Left leg
    (11, 13), (13, 15),
    # Right leg
    (12, 14), (14, 16),
]

COLOR_STANDING = (50,  220, 100)   # green
COLOR_FALLEN   = (30,   50, 240)   # red
COLOR_JOINT    = (255, 255, 255)   # white dot

JOINT_RADIUS   = 4
BONE_THICKNESS = 2
FONT           = cv2.FONT_HERSHEY_DUPLEX


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def _midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def _angle_from_vertical(p1, p2) -> float:
    """
    Returns the angle (degrees) between the line p1→p2 and the vertical axis.
    0° = perfectly vertical (standing), 90° = perfectly horizontal (lying).
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if dy == 0 and dx == 0:
        return 0.0
    angle = math.degrees(math.atan2(abs(dx), abs(dy)))
    return angle   # 0–90°


def _kp_visible(kp, frame_h, frame_w, conf_threshold=0.3) -> bool:
    x, y, conf = kp
    return (conf >= conf_threshold and
            0 <= x <= frame_w and
            0 <= y <= frame_h)


def _is_fallen(keypoints, bbox, conf_threshold: float = 0.30) -> tuple[bool, float, str]:
    """
    Analyze keypoints to determine if a person has fallen.
    Returns (fallen: bool, confidence: float, reason: str)
    """
    h  = bbox[3] - bbox[1]
    w  = bbox[2] - bbox[0]
    aspect_ratio = w / max(h, 1)

    reasons  = []
    evidence = 0
    total    = 0

    kps = keypoints   # shape: (17, 3) — [x, y, conf]

    # ── 1. Bounding box aspect ratio ──────────────────────────────────────────
    # Standing person: ~0.3–0.6 (tall bbox)
    # Fallen person:   > 1.0   (wide bbox)
    total += 1
    if aspect_ratio > 1.2:
        evidence += 1
        reasons.append(f"bbox_ratio={aspect_ratio:.1f}")
    elif aspect_ratio > 0.9:
        evidence += 0.5
        reasons.append(f"bbox_ratio_partial={aspect_ratio:.1f}")

    # ── 2. Shoulder-to-hip vertical angle ────────────────────────────────────
    L_sh, R_sh = kps[5], kps[6]
    L_hip, R_hip = kps[11], kps[12]

    sh_visible  = _kp_visible(L_sh, 9999, 9999, conf_threshold) or \
                  _kp_visible(R_sh, 9999, 9999, conf_threshold)
    hip_visible = _kp_visible(L_hip, 9999, 9999, conf_threshold) or \
                  _kp_visible(R_hip, 9999, 9999, conf_threshold)

    if sh_visible and hip_visible:
        sh_mid  = _midpoint((L_sh[0], L_sh[1]), (R_sh[0], R_sh[1]))
        hip_mid = _midpoint((L_hip[0], L_hip[1]), (R_hip[0], R_hip[1]))
        torso_angle = _angle_from_vertical(sh_mid, hip_mid)
        total += 1
        if torso_angle > 55:
            evidence += 1
            reasons.append(f"torso_angle={torso_angle:.0f}°")
        elif torso_angle > 40:
            evidence += 0.6
            reasons.append(f"torso_angle_partial={torso_angle:.0f}°")

    # ── 3. Head-to-hip height comparison ─────────────────────────────────────
    # Standing: head Y << hip Y (head is above hips)
    # Fallen:   head Y ≈ hip Y  (same level)
    nose = kps[0]
    if _kp_visible(nose, 9999, 9999, conf_threshold) and hip_visible:
        hip_y  = (L_hip[1] + R_hip[1]) / 2 if (L_hip[2] > conf_threshold and R_hip[2] > conf_threshold) \
                  else (L_hip[1] if L_hip[2] > conf_threshold else R_hip[1])
        nose_y = nose[1]
        # Relative position: how close nose is to hip in Y
        rel_diff = abs(nose_y - hip_y) / max(h, 1)
        total += 1
        if rel_diff < 0.25:   # head very close to hip level → fallen
            evidence += 1
            reasons.append(f"head_near_hip={rel_diff:.2f}")
        elif rel_diff < 0.40:
            evidence += 0.5

    # ── 4. Feet above torso ───────────────────────────────────────────────────
    # (can happen if person is upside down / on floor with legs raised)
    L_ank, R_ank = kps[15], kps[16]
    if (sh_visible and
        (_kp_visible(L_ank, 9999, 9999, conf_threshold) or
         _kp_visible(R_ank, 9999, 9999, conf_threshold))):
        sh_y  = (L_sh[1] + R_sh[1]) / 2 if (L_sh[2] > conf_threshold and R_sh[2] > conf_threshold) \
                 else (L_sh[1] if L_sh[2] > conf_threshold else R_sh[1])
        ank_y = 0
        if L_ank[2] > conf_threshold and R_ank[2] > conf_threshold:
            ank_y = (L_ank[1] + R_ank[1]) / 2
        elif L_ank[2] > conf_threshold:
            ank_y = L_ank[1]
        elif R_ank[2] > conf_threshold:
            ank_y = R_ank[1]
        if ank_y and sh_y > ank_y + 10:   # shoulders below ankles
            evidence += 1
            total    += 1
            reasons.append("shoulders_below_ankles")

    # ── Decision ─────────────────────────────────────────────────────────────
    if total == 0:
        return False, 0.0, "no_keypoints"

    score = evidence / total
    fallen_confidence = min(0.50 + score * 0.50, 0.99)  # map to [0.5, 0.99]

    # Need at least 60% evidence score to call it a fall
    fallen = score >= 0.6
    reason = " + ".join(reasons) if reasons else "no_evidence"
    return fallen, fallen_confidence if fallen else score, reason


# ─── Drawing helpers ──────────────────────────────────────────────────────────

def _draw_skeleton(frame, keypoints, fallen: bool, conf_threshold: float = 0.3):
    h, w = frame.shape[:2]
    color = COLOR_FALLEN if fallen else COLOR_STANDING

    # Draw bones
    for i, j in SKELETON_CONNECTIONS:
        kp_i = keypoints[i]
        kp_j = keypoints[j]
        if (_kp_visible(kp_i, h, w, conf_threshold) and
                _kp_visible(kp_j, h, w, conf_threshold)):
            pt1 = (int(kp_i[0]), int(kp_i[1]))
            pt2 = (int(kp_j[0]), int(kp_j[1]))
            cv2.line(frame, pt1, pt2, color, BONE_THICKNESS, cv2.LINE_AA)

    # Draw joints
    for kp in keypoints:
        if _kp_visible(kp, h, w, conf_threshold):
            cv2.circle(frame, (int(kp[0]), int(kp[1])),
                       JOINT_RADIUS, COLOR_JOINT, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(kp[0]), int(kp[1])),
                       JOINT_RADIUS + 1, color, 1, cv2.LINE_AA)


def _draw_fall_alert(frame, x1, y1, x2, y2, confidence: float):
    """Draw a prominent red bounding box + CAIDA alert label."""
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_FALLEN, 3)

    # Flashing-style filled top bar
    bar_h = 28
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1 - bar_h), (x2, y1), COLOR_FALLEN, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    text = f"CAIDA DETECTADA  {confidence:.0%}"
    cv2.putText(frame, text, (x1 + 6, y1 - 8),
                FONT, 0.52, (255, 255, 255), 1, cv2.LINE_AA)


# ─── Model cache ─────────────────────────────────────────────────────────────

_pose_cache: dict[str, object] = {}
_pose_lock  = threading.Lock()


def _load_pose_model(path: str = "yolov8n-pose.pt"):
    with _pose_lock:
        if path not in _pose_cache:
            try:
                from ultralytics import YOLO
                logger.info(f"Loading pose model: {path}")
                _pose_cache[path] = YOLO(path)
                logger.success(f"Pose model loaded: {path}")
            except Exception as e:
                logger.error(f"Failed to load pose model: {e}")
                _pose_cache[path] = None
        return _pose_cache[path]


# ─── FallDetector class ───────────────────────────────────────────────────────

class FallDetector:
    """
    Detects person falls using YOLOv8 Pose + skeleton analysis.
    Draws full skeleton on frames — green (standing), red (fallen).
    """

    def __init__(self, model_path: str = "yolov8n-pose.pt",
                 device: str = "cpu",
                 conf_threshold: float = 0.40):
        self.model_path     = model_path
        self.device         = device
        self.conf_threshold = conf_threshold
        self._model         = None

    def ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        self._model = _load_pose_model(self.model_path)
        return self._model is not None

    def detect(self,
               frame: np.ndarray,
               config: dict,
               draw: bool = True) -> tuple[np.ndarray, list[dict]]:
        """
        Run pose estimation + fall analysis.

        Returns:
            (annotated_frame, falls)
            falls: [{"fallen": bool, "confidence": float, "reason": str, "bbox": [x1,y1,x2,y2]}]
        """
        if not self.ensure_loaded():
            return frame, []

        conf = config.get("confidence", self.conf_threshold)

        try:
            results = self._model(
                frame, conf=conf, device=self.device,
                verbose=False, stream=False,
            )
        except Exception as e:
            logger.warning(f"Pose inference error: {e}")
            return frame, []

        annotated = frame.copy() if draw else frame
        detections: list[dict] = []

        for result in results:
            if result.keypoints is None or result.boxes is None:
                continue

            kps_data   = result.keypoints.data.cpu().numpy()   # (N, 17, 3)
            boxes_data = result.boxes.xyxy.cpu().numpy()       # (N, 4)
            confs_data = result.boxes.conf.cpu().numpy()       # (N,)

            for i in range(len(boxes_data)):
                kps  = kps_data[i]           # (17, 3)
                bbox = boxes_data[i].astype(int)
                x1, y1, x2, y2 = bbox

                fallen, fall_conf, reason = _is_fallen(
                    kps, bbox, conf_threshold=conf
                )

                detections.append({
                    "fallen":     fallen,
                    "confidence": fall_conf,
                    "reason":     reason,
                    "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                })

                if draw:
                    _draw_skeleton(annotated, kps, fallen, conf_threshold=conf)
                    if fallen:
                        _draw_fall_alert(annotated, x1, y1, x2, y2, fall_conf)
                    else:
                        # Draw subtle person box
                        cv2.rectangle(annotated, (x1, y1), (x2, y2),
                                      COLOR_STANDING, 1)
                        label = f"Persona  {confs_data[i]:.0%}"
                        cv2.putText(annotated, label, (x1 + 4, y1 - 6),
                                    FONT, 0.42, COLOR_STANDING, 1, cv2.LINE_AA)

        return annotated, detections
