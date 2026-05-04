"""
ONVIF Camera Discovery & Probe API
- WS-Discovery finds ONVIF cameras on LAN (no credentials needed)
- Probe uses WS-Security with nonce (required by Hikvision, Dahua, Axis, etc.)
- Falls back to brand-specific RTSP patterns if ONVIF media service fails
"""
import asyncio
import socket
import uuid
import re
import hashlib
import base64
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/api/onvif", tags=["ONVIF Discovery"])

# ─── WS-Discovery ─────────────────────────────────────────────────────────────

WS_DISCOVERY_ADDR = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

WS_PROBE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
    ' xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
    ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
    ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
    '<s:Header>'
    '<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>'
    '<a:MessageID>uuid:{msg_id}</a:MessageID>'
    '<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>'
    '</s:Header>'
    '<s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body>'
    '</s:Envelope>'
)


def _ws_discover(timeout: float = 4.0) -> list[dict]:
    msg = WS_PROBE.format(msg_id=str(uuid.uuid4())).encode("utf-8")
    found: dict[str, dict] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        sock.settimeout(timeout)
        sock.sendto(msg, (WS_DISCOVERY_ADDR, WS_DISCOVERY_PORT))
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip not in found:
                    xaddrs = _extract_xaddrs(data.decode("utf-8", errors="ignore"))
                    found[ip] = {"ip": ip, "xaddrs": xaddrs}
            except socket.timeout:
                break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"WS-Discovery error: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return list(found.values())


def _extract_xaddrs(xml_text: str) -> list[str]:
    addrs = []
    for xa in re.finditer(r'<[^>]*XAddrs[^>]*>([^<]+)<', xml_text):
        addrs.extend(xa.group(1).split())
    return addrs


# ─── WS-Security Header (nonce-based, required by most cameras) ───────────────

def _make_wsse_header(user: str, password: str) -> str:
    """
    Generate a WS-Security UsernameToken with PasswordDigest + Nonce + Created.
    Required by Hikvision, Dahua, Axis, Hanwha and most ONVIF cameras.
    PasswordDigest = Base64(SHA1(nonce + created + password))
    """
    nonce_raw   = os.urandom(16)
    nonce_b64   = base64.b64encode(nonce_raw).decode()
    created     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest_raw  = hashlib.sha1(nonce_raw + created.encode() + password.encode()).digest()
    digest_b64  = base64.b64encode(digest_raw).decode()

    return (
        '<s:Header>'
        '<Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        '<UsernameToken>'
        f'<Username>{user}</Username>'
        f'<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-ext-1.0/password#PasswordDigest">{digest_b64}</Password>'
        f'<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-ext-1.0/encoding#Base64Binary">{nonce_b64}</Nonce>'
        f'<wsu:Created>{created}</wsu:Created>'
        '</UsernameToken>'
        '</Security>'
        '</s:Header>'
    )


def _soap_envelope(user: str, password: str, body: str) -> str:
    header = _make_wsse_header(user, password)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl"'
        ' xmlns:trt="http://www.onvif.org/ver10/media/wsdl"'
        ' xmlns:tt="http://www.onvif.org/ver10/schema">'
        f'{header}'
        f'<s:Body>{body}</s:Body>'
        '</s:Envelope>'
    )


def _soap_post(url: str, envelope: str, timeout: float = 5.0) -> str:
    import urllib.request
    data = envelope.encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": 'application/soap+xml; charset=utf-8',
            "Content-Length": str(len(data)),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _xml_text(xml: str, tag: str) -> Optional[str]:
    m = re.search(rf'<(?:[^:>]+:)?{re.escape(tag)}[^>]*>([^<]+)<', xml)
    return m.group(1).strip() if m else None


def _xml_all(xml: str, tag: str) -> list[str]:
    return [m.group(1).strip()
            for m in re.finditer(rf'<(?:[^:>]+:)?{re.escape(tag)}[^>]*>([^<]+)<', xml)]


# ─── ONVIF Probe Logic ────────────────────────────────────────────────────────

def _probe_camera(ip: str, user: str, password: str,
                  xaddrs: list[str] | None = None) -> dict:
    """
    Probe a camera using ONVIF (WS-Security digest auth).
    Tries XAddrs from discovery first, then common ports.
    """
    # Build candidate service URLs
    candidates = list(xaddrs or [])
    # Add common port candidates if not already included
    for port_path in ["/onvif/device_service", "/onvif/device"]:
        for port in [80, 8080, 8000, 2020]:
            url = f"http://{ip}:{port}{port_path}"
            if url not in candidates:
                candidates.append(url)

    result = {
        "ip": ip,
        "manufacturer": "Desconocido",
        "model": "Desconocido",
        "firmware": None,
        "serial": None,
        "streams": [],
        "streams_source": "none",
        "onvif_ok": False,
        "service_url": None,
    }

    # 1. Try each candidate URL for device info
    service_url = None
    device_xml  = ""
    for url in candidates[:6]:
        try:
            env = _soap_envelope(user, password,
                                 "<tds:GetDeviceInformation/>")
            device_xml  = _soap_post(url, env, timeout=4.0)
            service_url = url
            result["onvif_ok"]    = True
            result["service_url"] = url
            break
        except Exception as e:
            logger.debug(f"ONVIF probe failed {url}: {e}")
            continue

    if not result["onvif_ok"]:
        # ONVIF completely unreachable — use brand fallback
        result["streams"]        = _brand_fallback(ip, user, password, "generic")
        result["streams_source"] = "fallback_generic"
        return result

    # Parse device info
    result["manufacturer"] = _xml_text(device_xml, "Manufacturer") or "Desconocido"
    result["model"]        = _xml_text(device_xml, "Model")        or "Desconocido"
    result["firmware"]     = _xml_text(device_xml, "FirmwareVersion")
    result["serial"]       = _xml_text(device_xml, "SerialNumber")

    # 2. Resolve media service URL (may differ from device service)
    media_url = service_url  # default fallback
    try:
        env = _soap_envelope(user, password, "<tds:GetCapabilities/>")
        caps_xml   = _soap_post(service_url, env, timeout=4.0)
        media_addr = _xml_text(caps_xml, "XAddr")
        if media_addr and media_addr.startswith("http"):
            media_url = media_addr
    except Exception:
        pass

    # 3. Get media profiles
    profile_tokens: list[str] = []
    profile_names:  list[str] = []
    try:
        env      = _soap_envelope(user, password, "<trt:GetProfiles/>")
        prof_xml = _soap_post(media_url, env, timeout=5.0)
        # Extract token attributes from Profiles elements
        for m in re.finditer(r'<[^>]*Profiles[^>]+token="([^"]+)"[^>]*>', prof_xml):
            profile_tokens.append(m.group(1))
        # Fallback: look for token tags
        if not profile_tokens:
            profile_tokens = _xml_all(prof_xml, "token")
        # Profile name/resolution for display
        profile_names = _xml_all(prof_xml, "Name") or profile_tokens
    except Exception as e:
        logger.debug(f"GetProfiles failed {media_url}: {e}")

    # 4. Get stream URI per profile
    if profile_tokens:
        for idx, token in enumerate(profile_tokens[:4]):
            try:
                body = (
                    "<trt:GetStreamUri>"
                    "<trt:StreamSetup>"
                    "<tt:Stream>RTP-Unicast</tt:Stream>"
                    "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
                    "</trt:StreamSetup>"
                    f"<trt:ProfileToken>{token}</trt:ProfileToken>"
                    "</trt:GetStreamUri>"
                )
                env    = _soap_envelope(user, password, body)
                uri_xml = _soap_post(media_url, env, timeout=5.0)
                uri    = _xml_text(uri_xml, "Uri")
                if uri and "rtsp://" in uri:
                    # Inject credentials if missing
                    host_part = uri.split("://")[1].split("/")[0]
                    if "@" not in host_part:
                        uri = uri.replace("rtsp://", f"rtsp://{user}:{password}@", 1)
                    label = profile_names[idx] if idx < len(profile_names) else f"Perfil {idx + 1}"
                    result["streams"].append({
                        "label":    label,
                        "rtsp_url": uri,
                        "token":    token,
                    })
            except Exception as e:
                logger.debug(f"GetStreamUri failed token={token}: {e}")

    if result["streams"]:
        result["streams_source"] = "onvif"
        return result

    # 5. No streams from ONVIF — try brand-specific patterns
    brand   = _detect_brand(result["manufacturer"])
    streams = _brand_fallback(ip, user, password, brand)
    result["streams"]        = streams
    result["streams_source"] = f"brand_{brand}" if brand != "generic" else "fallback_generic"
    return result


# ─── Brand-specific RTSP patterns ─────────────────────────────────────────────

BRAND_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "hikvision": [
        ("Principal (HD)",     "rtsp://{u}:{p}@{ip}:554/Streaming/Channels/101"),
        ("Substream (SD)",     "rtsp://{u}:{p}@{ip}:554/Streaming/Channels/102"),
        ("Canal 2 principal",  "rtsp://{u}:{p}@{ip}:554/Streaming/Channels/201"),
    ],
    "dahua": [
        ("Canal 1 principal",  "rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel=1&subtype=0"),
        ("Canal 1 substream",  "rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel=1&subtype=1"),
        ("Canal 2 principal",  "rtsp://{u}:{p}@{ip}:554/cam/realmonitor?channel=2&subtype=0"),
    ],
    "axis": [
        ("Stream MJPEG",       "rtsp://{u}:{p}@{ip}:554/axis-media/media.amp"),
        ("Stream H264",        "rtsp://{u}:{p}@{ip}:554/axis-media/media.amp?videocodec=h264"),
    ],
    "hanwha": [
        ("Perfil 1",           "rtsp://{u}:{p}@{ip}:554/profile1/media.smp"),
        ("Perfil 2",           "rtsp://{u}:{p}@{ip}:554/profile2/media.smp"),
    ],
    "bosch": [
        ("Stream principal",   "rtsp://{u}:{p}@{ip}:554/rtsp_tunnel"),
    ],
    "uniview": [
        ("Canal 1 principal",  "rtsp://{u}:{p}@{ip}:554/unicast/c1/s0/live"),
        ("Canal 1 substream",  "rtsp://{u}:{p}@{ip}:554/unicast/c1/s1/live"),
    ],
    "reolink": [
        ("Stream principal",   "rtsp://{u}:{p}@{ip}:554//h264Preview_01_main"),
        ("Substream",          "rtsp://{u}:{p}@{ip}:554//h264Preview_01_sub"),
    ],
    "generic": [
        ("Stream 1",           "rtsp://{u}:{p}@{ip}:554/stream1"),
        ("Stream 2",           "rtsp://{u}:{p}@{ip}:554/stream2"),
        ("Stream H264",        "rtsp://{u}:{p}@{ip}:554/h264/ch1/main/av_stream"),
        ("Live",               "rtsp://{u}:{p}@{ip}:554/live"),
    ],
}


def _detect_brand(manufacturer: str) -> str:
    m = manufacturer.lower()
    for brand in BRAND_PATTERNS:
        if brand != "generic" and brand in m:
            return brand
    # Common aliases
    if "hikvision" in m or "hikvisio" in m or "hik" in m:
        return "hikvision"
    if "dahua" in m or "amcrest" in m:
        return "dahua"
    if "axis" in m:
        return "axis"
    if "hanwha" in m or "samsung" in m or "wisenet" in m:
        return "hanwha"
    return "generic"


def _brand_fallback(ip: str, user: str, password: str, brand: str) -> list[dict]:
    patterns = BRAND_PATTERNS.get(brand, BRAND_PATTERNS["generic"])
    return [
        {"label": label, "rtsp_url": url.format(u=user, p=password, ip=ip)}
        for label, url in patterns
    ]


# ─── API Endpoints ────────────────────────────────────────────────────────────

class ProbeRequest(BaseModel):
    ip: str
    user: str = "admin"
    password: str = ""
    port: int = 80
    xaddrs: list[str] = []


@router.get("/discover")
async def discover_cameras(timeout: float = 4.0):
    """WS-Discovery broadcast — finds all ONVIF cameras on the LAN."""
    loop = asyncio.get_event_loop()
    devices = await loop.run_in_executor(None, _ws_discover, timeout)
    logger.info(f"WS-Discovery: {len(devices)} dispositivos encontrados")
    return {"found": len(devices), "devices": devices}


@router.post("/probe")
async def probe_camera(req: ProbeRequest):
    """
    Probe a camera via ONVIF (WS-Security digest).
    Returns manufacturer, model, firmware, serial and available RTSP stream URLs.
    """
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _probe_camera, req.ip, req.user, req.password, req.xaddrs or None
    )
    return result


@router.get("/brands")
async def get_brand_patterns():
    """Reference RTSP URL patterns per brand."""
    return {
        brand: [url.format(u="admin", p="pass", ip="192.168.x.x")
                for _, url in patterns]
        for brand, patterns in BRAND_PATTERNS.items()
    }
