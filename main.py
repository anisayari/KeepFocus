from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.request import urlretrieve

import cv2
import mediapipe as mp
import numpy as np
from pytube import YouTube, extract


YOUTUBE_URL = "https://www.youtube.com/watch?v=lIIhz2Glx7s"
WINDOW_NAME = "Gaze Focus TamTam"
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "videos"
VIDEO_PATH = VIDEO_DIR / "youtube_trigger_video.mp4"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "face_landmarker.task"
PLAYER_HTML_PATH = BASE_DIR / "video_player.html"
PLAYER_PROFILE_DIR = BASE_DIR / ".video_player_profile"
CALIBRATION_PATH = BASE_DIR / "attention_calibration.json"
MACOS_SOUND_PATH = Path("/System/Library/Sounds/Ping.aiff")
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)

NOT_LOOKING_TRIGGER_SECONDS = 0.15
YAW_THRESHOLD = 18.0
PITCH_THRESHOLD = 16.0
ROLL_THRESHOLD = 15.0
GAZE_HORIZONTAL_MIN = 0.30
GAZE_HORIZONTAL_MAX = 0.70
GAZE_VERTICAL_MIN = 0.22
GAZE_VERTICAL_MAX = 0.78
FACE_BOX_PADDING = 20
EYE_BOX_PADDING = 12
POINT_RADIUS = 1
IRIS_POINT_RADIUS = 2
CAMERA_CAPTURE_WIDTH = 1280
CAMERA_CAPTURE_HEIGHT = 720
CAMERA_WINDOW_WIDTH = 1440
CAMERA_WINDOW_HEIGHT = 920
HEADER_HEIGHT = 72
CALIBRATION_REPETITIONS = 3
CALIBRATION_PREP_SECONDS = 2.0
CALIBRATION_CAPTURE_SECONDS = 2.5
CALIBRATION_MIN_SAMPLES = 12
CALIBRATION_MIN_STABILITY_SAMPLES = 5
VALIDATION_PREP_SECONDS = 1.2
VALIDATION_CAPTURE_SECONDS = 1.6
VALIDATION_MIN_SAMPLES = 8
VALIDATION_PASS_SCORE = 80.0
CALIBRATION_FEATURE_KEYS = ("yaw", "pitch", "roll", "gaze_x", "gaze_y")
CALIBRATION_SCALE_FLOOR = np.array([8.0, 8.0, 6.0, 0.08, 0.08], dtype=np.float64)
CALIBRATION_FEATURE_WEIGHTS = np.array([1.0, 1.0, 0.8, 1.25, 1.25], dtype=np.float64)

LEFT_IRIS = (468, 469, 470, 471, 472)
RIGHT_IRIS = (473, 474, 475, 476, 477)
LEFT_EYE_BOX = (33, 133, 159, 145, 160, 144, 158, 153, 157, 173)
RIGHT_EYE_BOX = (263, 362, 386, 374, 387, 373, 385, 380, 384, 398)
ANNOUNCEMENT_LOCK = threading.Lock()


def ensure_video_downloaded() -> Path:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    if VIDEO_PATH.exists():
        return VIDEO_PATH

    print("Telechargement de la video YouTube...")
    try:
        downloaded_path = download_with_pytube(VIDEO_PATH)
    except Exception as pytube_error:
        print(f"pytube a echoue: {pytube_error}")
        print("Fallback automatique vers pytubefix...")
        downloaded_path = download_with_pytubefix(VIDEO_PATH)

    print(f"Video enregistree dans: {downloaded_path}")
    return downloaded_path


def ensure_face_landmarker_model() -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        return MODEL_PATH

    print("Telechargement du modele FaceLandmarker...")
    urlretrieve(MODEL_URL, MODEL_PATH)
    print(f"Modele enregistre dans: {MODEL_PATH}")
    return MODEL_PATH


def find_browser_command() -> list[str]:
    system_name = platform.system()
    if system_name == "Darwin":
        candidates = (
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        )
    elif system_name == "Windows":
        candidates = (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        )
    else:
        candidates = tuple()

    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]

    for binary in ("google-chrome", "microsoft-edge", "chromium", "chromium-browser"):
        found = shutil.which(binary)
        if found is not None:
            return [found]

    raise FileNotFoundError("Aucun navigateur compatible (Chrome/Edge) n'est installe.")


def ensure_video_player_html() -> Path:
    if not PLAYER_HTML_PATH.exists():
        raise FileNotFoundError(f"Lecteur video introuvable: {PLAYER_HTML_PATH}")
    return PLAYER_HTML_PATH


def open_camera() -> cv2.VideoCapture:
    if platform.system() == "Darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
        camera = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    else:
        camera = cv2.VideoCapture(0)

    if camera.isOpened():
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_CAPTURE_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_CAPTURE_HEIGHT)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return camera


def announce_calibration_change(message: str) -> None:
    def worker() -> None:
        with ANNOUNCEMENT_LOCK:
            system_name = platform.system()
            if system_name == "Darwin":
                if MACOS_SOUND_PATH.exists():
                    subprocess.run(
                        ["afplay", str(MACOS_SOUND_PATH)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                say_executable = shutil.which("say")
                if say_executable is not None:
                    subprocess.run(
                        [say_executable, message],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    return
            elif system_name == "Windows":
                try:
                    import winsound

                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    return
                except Exception:
                    pass

            print(f"[Calibration] {message}")

    threading.Thread(target=worker, daemon=True).start()


def browser_app_name(browser_command: list[str]) -> str | None:
    executable_name = Path(browser_command[0]).name.lower()
    if "chrome" in executable_name:
        return "Google Chrome"
    if "edge" in executable_name:
        return "Microsoft Edge"
    return None


def pick_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def metrics_to_vector(metrics: dict[str, float]) -> np.ndarray:
    return np.array([metrics[key] for key in CALIBRATION_FEATURE_KEYS], dtype=np.float64)


def compute_profile_distance(
    vector: np.ndarray,
    center: np.ndarray,
    scale: np.ndarray,
) -> float:
    normalized = ((vector - center) / scale) * CALIBRATION_FEATURE_WEIGHTS
    return float(np.linalg.norm(normalized))


def compute_step_stability_score(samples: list[dict[str, float]]) -> float | None:
    if len(samples) < CALIBRATION_MIN_STABILITY_SAMPLES:
        return None

    vectors = np.vstack([metrics_to_vector(sample) for sample in samples])
    spreads = vectors.std(axis=0)
    normalized = (spreads / CALIBRATION_SCALE_FLOOR) * CALIBRATION_FEATURE_WEIGHTS
    raw_score = float(np.linalg.norm(normalized))
    return float(np.clip(100.0 - raw_score * 26.0, 0.0, 100.0))


def build_calibration_profile(
    screen_samples: list[dict[str, float]],
    phone_samples: list[dict[str, float]],
) -> dict[str, Any]:
    screen_vectors = np.vstack([metrics_to_vector(sample) for sample in screen_samples])
    phone_vectors = np.vstack([metrics_to_vector(sample) for sample in phone_samples])

    screen_center = screen_vectors.mean(axis=0)
    phone_center = phone_vectors.mean(axis=0)
    screen_scale = np.maximum(screen_vectors.std(axis=0), CALIBRATION_SCALE_FLOOR)
    phone_scale = np.maximum(phone_vectors.std(axis=0), CALIBRATION_SCALE_FLOOR)

    screen_self_distances = np.array(
        [compute_profile_distance(vector, screen_center, screen_scale) for vector in screen_vectors],
        dtype=np.float64,
    )
    phone_self_distances = np.array(
        [compute_profile_distance(vector, phone_center, phone_scale) for vector in phone_vectors],
        dtype=np.float64,
    )
    screen_scores = np.array(
        [
            compute_profile_distance(vector, phone_center, phone_scale)
            - compute_profile_distance(vector, screen_center, screen_scale)
            for vector in screen_vectors
        ],
        dtype=np.float64,
    )
    phone_scores = np.array(
        [
            compute_profile_distance(vector, phone_center, phone_scale)
            - compute_profile_distance(vector, screen_center, screen_scale)
            for vector in phone_vectors
        ],
        dtype=np.float64,
    )

    decision_boundary = float(
        (np.percentile(screen_scores, 20) + np.percentile(phone_scores, 80)) / 2.0
    )
    screen_distance_limit = float(max(np.percentile(screen_self_distances, 90) + 0.35, 1.75))
    phone_distance_limit = float(max(np.percentile(phone_self_distances, 90) + 0.35, 1.75))

    return {
        "version": 1,
        "screen_center": screen_center.tolist(),
        "screen_scale": screen_scale.tolist(),
        "phone_center": phone_center.tolist(),
        "phone_scale": phone_scale.tolist(),
        "decision_boundary": decision_boundary,
        "screen_distance_limit": screen_distance_limit,
        "phone_distance_limit": phone_distance_limit,
        "screen_sample_count": len(screen_samples),
        "phone_sample_count": len(phone_samples),
    }


def load_calibration_profile() -> dict[str, Any] | None:
    if not CALIBRATION_PATH.exists():
        return None
    try:
        profile = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    required_keys = {
        "screen_center",
        "screen_scale",
        "phone_center",
        "phone_scale",
        "decision_boundary",
        "screen_distance_limit",
        "phone_distance_limit",
    }
    if not required_keys.issubset(profile):
        return None
    return profile


def save_calibration_profile(profile: dict[str, Any]) -> None:
    CALIBRATION_PATH.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def draw_text_block(
    frame: np.ndarray,
    lines: list[str],
    *,
    origin: tuple[int, int] = (20, 30),
    color: tuple[int, int, int] = (255, 255, 255),
    line_height: int = 30,
) -> None:
    if not lines:
        return

    x, y = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2
    widths = [
        cv2.getTextSize(line, font, font_scale, thickness)[0][0]
        for line in lines
    ]
    block_width = max(widths) + 24
    block_height = line_height * len(lines) + 16

    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (x - 10, y - 24),
        (x - 10 + block_width, y - 24 + block_height),
        (0, 0, 0),
        -1,
    )
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0.0, frame)

    for index, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (x, y + index * line_height),
            font,
            font_scale,
            color,
            thickness,
            lineType=cv2.LINE_AA,
        )


def draw_badge(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    background: tuple[int, int, int],
    foreground: tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.55,
    padding_x: int = 14,
    padding_y: int = 10,
) -> int:
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = origin
    left = x
    top = y
    right = x + text_width + padding_x * 2
    bottom = y + text_height + padding_y * 2 + baseline

    overlay = frame.copy()
    cv2.rectangle(overlay, (left, top), (right, bottom), background, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0.0, frame)
    cv2.rectangle(frame, (left, top), (right, bottom), (255, 255, 255), 1)
    cv2.putText(
        frame,
        text,
        (x + padding_x, y + padding_y + text_height),
        font,
        font_scale,
        foreground,
        thickness,
        lineType=cv2.LINE_AA,
    )
    return right


def badge_width(
    text: str,
    *,
    font_scale: float = 0.55,
    padding_x: int = 14,
) -> int:
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 1
    (text_width, _), _ = cv2.getTextSize(text, font, font_scale, thickness)
    return text_width + padding_x * 2


def calibration_feature_bounds(feature_name: str) -> tuple[float, float]:
    if feature_name in {"yaw", "pitch"}:
        return -35.0, 35.0
    if feature_name == "roll":
        return -25.0, 25.0
    return 0.0, 1.0


def calibration_feature_label(feature_name: str) -> str:
    labels = {
        "yaw": "Yaw",
        "pitch": "Pitch",
        "roll": "Roll",
        "gaze_x": "Gaze X",
        "gaze_y": "Gaze Y",
    }
    return labels.get(feature_name, feature_name)


def draw_calibration_summary_panel(
    frame: np.ndarray,
    calibration_profile: dict[str, Any],
) -> None:
    panel_width = min(430, max(320, frame.shape[1] // 3))
    x1 = frame.shape[1] - panel_width - 16
    y1 = 96
    x2 = frame.shape[1] - 16
    y2 = frame.shape[0] - 90

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (15, 20, 32), -1)
    cv2.addWeighted(overlay, 0.90, frame, 0.10, 0.0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 90, 112), 1)

    title_y = y1 + 28
    cv2.putText(
        frame,
        "MOYENNES CALIBRATION",
        (x1 + 16, title_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
        lineType=cv2.LINE_AA,
    )

    screen_center = np.array(calibration_profile["screen_center"], dtype=np.float64)
    phone_center = np.array(calibration_profile["phone_center"], dtype=np.float64)
    validation_score = calibration_profile.get("validation_score")
    validation_label = (
        f"Check: {float(validation_score):.0f}/100"
        if validation_score is not None
        else "Check: n/a"
    )
    cv2.putText(
        frame,
        validation_label,
        (x1 + 16, title_y + 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.46,
        (155, 221, 177) if calibration_profile.get("validation_passed") else (255, 212, 140),
        1,
        lineType=cv2.LINE_AA,
    )

    row_y = title_y + 58
    bar_left = x1 + 118
    bar_right = x2 - 16
    bar_width = bar_right - bar_left

    for feature_name, screen_value, phone_value in zip(
        CALIBRATION_FEATURE_KEYS,
        screen_center,
        phone_center,
    ):
        low, high = calibration_feature_bounds(feature_name)
        ratio_screen = float(np.clip((screen_value - low) / (high - low), 0.0, 1.0))
        ratio_phone = float(np.clip((phone_value - low) / (high - low), 0.0, 1.0))

        cv2.putText(
            frame,
            calibration_feature_label(feature_name),
            (x1 + 16, row_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (235, 235, 235),
            1,
            lineType=cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (bar_left, row_y - 6),
            (bar_right, row_y - 6),
            (75, 81, 96),
            2,
            lineType=cv2.LINE_AA,
        )
        screen_x = bar_left + int(bar_width * ratio_screen)
        phone_x = bar_left + int(bar_width * ratio_phone)
        cv2.circle(frame, (screen_x, row_y - 6), 6, (0, 190, 0), -1, lineType=cv2.LINE_AA)
        cv2.circle(frame, (phone_x, row_y - 6), 6, (0, 165, 255), -1, lineType=cv2.LINE_AA)
        cv2.putText(
            frame,
            f"E {screen_value:+.2f}",
            (bar_left, row_y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (140, 255, 140),
            1,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"T {phone_value:+.2f}",
            (bar_left + 128, row_y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (120, 210, 255),
            1,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"D {screen_value - phone_value:+.2f}",
            (bar_left + 256, row_y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (222, 222, 222),
            1,
            lineType=cv2.LINE_AA,
        )
        row_y += 58

    footer_lines = [
        f"Score seuil: {float(calibration_profile['decision_boundary']):+.2f}",
        f"Limite ecran: {float(calibration_profile['screen_distance_limit']):.2f}",
        f"Limite tel: {float(calibration_profile['phone_distance_limit']):.2f}",
        "Vert = ecran, orange = telephone",
    ]
    footer_y = y2 - 64
    for line in footer_lines:
        cv2.putText(
            frame,
            line,
            (x1 + 16, footer_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (205, 208, 215),
            1,
            lineType=cv2.LINE_AA,
        )
        footer_y += 18


def normalize_download_path(downloaded_path: Path, final_path: Path) -> Path:
    if downloaded_path == final_path:
        return final_path

    if final_path.exists():
        final_path.unlink()
    downloaded_path.replace(final_path)
    return final_path


def download_with_pytube(target_path: Path) -> Path:
    yt = YouTube(YOUTUBE_URL)
    initial_player_response = extract.initial_player_response(yt.watch_html)
    if "streamingData" in initial_player_response:
        yt._vid_info = initial_player_response

    stream = (
        yt.streams.filter(progressive=True, file_extension="mp4")
        .order_by("resolution")
        .desc()
        .first()
    )
    if stream is None:
        raise RuntimeError("Aucun flux mp4 progressif n'a ete trouve avec pytube.")

    downloaded_path = Path(
        stream.download(
            output_path=str(target_path.parent),
            filename=target_path.stem,
            skip_existing=False,
        )
    )
    return normalize_download_path(downloaded_path, target_path)


def download_with_pytubefix(target_path: Path) -> Path:
    from pytubefix import YouTube as FixedYouTube

    yt = FixedYouTube(YOUTUBE_URL)
    stream = (
        yt.streams.filter(progressive=True, file_extension="mp4")
        .order_by("resolution")
        .desc()
        .first()
    )
    if stream is None:
        raise RuntimeError("Aucun flux mp4 progressif n'a ete trouve avec pytubefix.")

    downloaded_path = Path(
        stream.download(
            output_path=str(target_path.parent),
            filename=target_path.stem,
            skip_existing=False,
        )
    )
    return normalize_download_path(downloaded_path, target_path)


def average_point(
    landmarks: list[Any],
    indices: Iterable[int],
    width: int,
    height: int,
) -> np.ndarray:
    points = []
    for index in indices:
        landmark = landmarks[index]
        points.append((landmark.x * width, landmark.y * height))
    return np.mean(np.array(points, dtype=np.float64), axis=0)


def landmark_point(
    landmarks: list[Any],
    index: int,
    width: int,
    height: int,
) -> np.ndarray:
    landmark = landmarks[index]
    return np.array((landmark.x * width, landmark.y * height), dtype=np.float64)


def all_landmark_points(
    landmarks: list[Any],
    width: int,
    height: int,
) -> np.ndarray:
    points = []
    for landmark in landmarks:
        points.append(
            (
                int(np.clip(landmark.x * width, 0, width - 1)),
                int(np.clip(landmark.y * height, 0, height - 1)),
            )
        )
    return np.array(points, dtype=np.int32)


def bounding_box_from_points(
    points: np.ndarray,
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    x1 = max(int(points[:, 0].min()) - padding, 0)
    y1 = max(int(points[:, 1].min()) - padding, 0)
    x2 = min(int(points[:, 0].max()) + padding, width - 1)
    y2 = min(int(points[:, 1].max()) + padding, height - 1)
    return x1, y1, x2, y2


def bounding_box_from_indices(
    landmarks: list[Any],
    indices: Iterable[int],
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    points = []
    for index in indices:
        point = landmark_point(landmarks, index, width, height)
        points.append(
            (
                int(np.clip(point[0], 0, width - 1)),
                int(np.clip(point[1], 0, height - 1)),
            )
        )
    return bounding_box_from_points(np.array(points, dtype=np.int32), width, height, padding)


def normalized_axis_ratio(value: float, a: float, b: float) -> float:
    low = min(a, b)
    high = max(a, b)
    if abs(high - low) < 1e-6:
        return 0.5
    return (value - low) / (high - low)


def compute_iris_ratios(
    landmarks: list[Any],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    left_center = average_point(landmarks, LEFT_IRIS, width, height)
    right_center = average_point(landmarks, RIGHT_IRIS, width, height)

    left_outer = landmark_point(landmarks, 33, width, height)
    left_inner = landmark_point(landmarks, 133, width, height)
    left_top = landmark_point(landmarks, 159, width, height)
    left_bottom = landmark_point(landmarks, 145, width, height)

    right_outer = landmark_point(landmarks, 263, width, height)
    right_inner = landmark_point(landmarks, 362, width, height)
    right_top = landmark_point(landmarks, 386, width, height)
    right_bottom = landmark_point(landmarks, 374, width, height)

    left_horizontal = normalized_axis_ratio(left_center[0], left_outer[0], left_inner[0])
    left_vertical = normalized_axis_ratio(left_center[1], left_top[1], left_bottom[1])
    right_horizontal = normalized_axis_ratio(
        right_center[0], right_outer[0], right_inner[0]
    )
    right_vertical = normalized_axis_ratio(right_center[1], right_top[1], right_bottom[1])

    return left_horizontal, right_horizontal, left_vertical, right_vertical


def estimate_head_pose(
    landmarks: list[Any],
    width: int,
    height: int,
) -> tuple[float, float, float]:
    image_points = np.array(
        [
            landmark_point(landmarks, 1, width, height),
            landmark_point(landmarks, 152, width, height),
            landmark_point(landmarks, 33, width, height),
            landmark_point(landmarks, 263, width, height),
            landmark_point(landmarks, 61, width, height),
            landmark_point(landmarks, 291, width, height),
        ],
        dtype=np.float64,
    )

    model_points = np.array(
        [
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0),
        ],
        dtype=np.float64,
    )

    focal_length = float(width)
    camera_matrix = np.array(
        [[focal_length, 0, width / 2], [0, focal_length, height / 2], [0, 0, 1]],
        dtype=np.float64,
    )
    distortion = np.zeros((4, 1), dtype=np.float64)

    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return 0.0, 0.0, 0.0

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    projection = cv2.hconcat((rotation_matrix, translation_vector))
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(projection)
    pitch, yaw, _ = euler_angles.flatten()

    left_eye_center = average_point(landmarks, LEFT_EYE_BOX, width, height)
    right_eye_center = average_point(landmarks, RIGHT_EYE_BOX, width, height)
    roll = float(np.degrees(np.arctan2(
        right_eye_center[1] - left_eye_center[1],
        right_eye_center[0] - left_eye_center[0],
    )))

    return float(yaw), float(pitch), roll


def extract_attention_metrics(
    landmarks: list[Any],
    width: int,
    height: int,
) -> dict[str, float]:
    yaw, pitch, roll = estimate_head_pose(landmarks, width, height)
    left_h, right_h, left_v, right_v = compute_iris_ratios(landmarks, width, height)

    horizontal_ratio = (left_h + right_h) / 2
    vertical_ratio = (left_v + right_v) / 2

    return {
        "yaw": yaw,
        "pitch": pitch,
        "roll": roll,
        "gaze_x": horizontal_ratio,
        "gaze_y": vertical_ratio,
    }


def classify_attention(
    metrics: dict[str, float],
    calibration_profile: dict[str, Any] | None,
) -> tuple[bool, dict[str, float]]:
    enriched_metrics = dict(metrics)

    if calibration_profile is None:
        head_centered = (
            abs(metrics["yaw"]) <= YAW_THRESHOLD
            and abs(metrics["pitch"]) <= PITCH_THRESHOLD
            and abs(metrics["roll"]) <= ROLL_THRESHOLD
        )
        gaze_centered = (
            GAZE_HORIZONTAL_MIN <= metrics["gaze_x"] <= GAZE_HORIZONTAL_MAX
            and GAZE_VERTICAL_MIN <= metrics["gaze_y"] <= GAZE_VERTICAL_MAX
        )
        looking_at_screen = head_centered and gaze_centered
        enriched_metrics["screen_score"] = 1.0 if looking_at_screen else -1.0
        enriched_metrics["classification_mode"] = 0.0
        enriched_metrics["attention_state"] = "screen" if looking_at_screen else "away"
        return looking_at_screen, enriched_metrics

    vector = metrics_to_vector(metrics)
    screen_center = np.array(calibration_profile["screen_center"], dtype=np.float64)
    screen_scale = np.array(calibration_profile["screen_scale"], dtype=np.float64)
    phone_center = np.array(calibration_profile["phone_center"], dtype=np.float64)
    phone_scale = np.array(calibration_profile["phone_scale"], dtype=np.float64)

    screen_distance = compute_profile_distance(vector, screen_center, screen_scale)
    phone_distance = compute_profile_distance(vector, phone_center, phone_scale)
    screen_score = phone_distance - screen_distance
    phone_score = screen_distance - phone_distance
    looking_at_screen = (
        screen_score >= float(calibration_profile["decision_boundary"])
        and screen_distance <= float(calibration_profile["screen_distance_limit"])
    )
    looking_at_phone = (
        not looking_at_screen
        and phone_distance <= float(calibration_profile["phone_distance_limit"])
        and phone_distance < screen_distance
    )
    attention_state = "screen" if looking_at_screen else "phone" if looking_at_phone else "away"

    enriched_metrics["screen_distance"] = screen_distance
    enriched_metrics["phone_distance"] = phone_distance
    enriched_metrics["screen_score"] = screen_score
    enriched_metrics["phone_score"] = phone_score
    enriched_metrics["decision_boundary"] = float(calibration_profile["decision_boundary"])
    enriched_metrics["attention_state"] = attention_state
    enriched_metrics["classification_mode"] = 1.0
    return looking_at_screen, enriched_metrics


class ControlledVideoPlayer:
    def __init__(
        self,
        video_path: Path,
        browser_command: list[str],
        player_html: Path,
    ) -> None:
        self.video_path = video_path
        self.browser_command = browser_command
        self.browser_app_name = browser_app_name(browser_command)
        self.player_html = player_html
        self.port = pick_free_port()
        self.process: subprocess.Popen[bytes] | None = None
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.state_lock = threading.Lock()
        self.playing = False

    @property
    def is_active(self) -> bool:
        with self.state_lock:
            return self.playing

    def _make_handler(self):
        player = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(BASE_DIR), **kwargs)

            def do_GET(self):
                if self.path.split("?", 1)[0] == "/state":
                    with player.state_lock:
                        payload = json.dumps({"playing": player.playing}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                super().do_GET()

            def log_message(self, format, *args):
                return

        return Handler

    def _ensure_server(self) -> None:
        if self.server is not None:
            return
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), self._make_handler())
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()

    def _window_is_open(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _mac_activate(self) -> None:
        if platform.system() != "Darwin" or self.browser_app_name is None:
            return
        subprocess.run(
            ["osascript", "-e", f'tell application "{self.browser_app_name}" to activate'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def _mac_hide(self) -> None:
        if platform.system() != "Darwin" or self.browser_app_name is None:
            return
        subprocess.run(
            ["osascript", "-e", f'tell application "{self.browser_app_name}" to hide'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def _activate_window(self) -> None:
        if platform.system() != "Darwin":
            return

        def worker() -> None:
            self._mac_activate()
            time.sleep(0.35)
            self._mac_activate()

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_window(self) -> None:
        if self._window_is_open():
            return
        self._ensure_server()
        PLAYER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            [
                *self.browser_command,
                "--new-window",
                f"--user-data-dir={PLAYER_PROFILE_DIR}",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-session-crashed-bubble",
                "--no-first-run",
                "--window-size=1280,760",
                f"--app=http://127.0.0.1:{self.port}/{self.player_html.name}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def start(self) -> None:
        with self.state_lock:
            self.playing = True
        try:
            self._ensure_window()
        except Exception:
            with self.state_lock:
                self.playing = False
            raise
        self._activate_window()

    def update(self) -> None:
        if self.is_active:
            self._ensure_window()

    def stop(self) -> None:
        with self.state_lock:
            self.playing = False
        self._mac_hide()

    def shutdown(self) -> None:
        self.stop()
        if self.process is not None and self.process.poll() is None:
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if platform.system() != "Windows":
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        self.process = None
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.server_thread is not None:
            self.server_thread.join(timeout=3)
            self.server_thread = None


def read_and_process_frame(
    camera: cv2.VideoCapture,
    face_landmarker: Any,
) -> tuple[bool, np.ndarray | None, list[Any] | None]:
    ok, frame = camera.read()
    if not ok:
        return False, None, None

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    timestamp_ms = int(time.monotonic() * 1000)
    results = face_landmarker.detect_for_video(mp_image, timestamp_ms)
    landmarks = results.face_landmarks[0] if results.face_landmarks else None
    return True, frame, landmarks


def prompt_for_calibration(
    camera: cv2.VideoCapture,
    face_landmarker: Any,
    existing_profile: dict[str, Any] | None,
) -> str:
    while True:
        ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
        if not ok or frame is None:
            return "quit"

        if landmarks is not None:
            draw_face_visuals(frame, landmarks, color_override=(0, 220, 255))

        lines = [
            "Calibration du regard",
            "C : calibrer maintenant",
            (
                "S / Entree / Espace : utiliser la calibration sauvegardee"
                if existing_profile is not None
                else "S / Entree / Espace : continuer sans calibration"
            ),
            (
                "Calibration sauvegardee detectee"
                if existing_profile is not None
                else "Aucune calibration sauvegardee"
            ),
            "Un son annonce chaque changement de cible",
            "Q ou ESC : quitter",
        ]
        draw_text_block(frame, lines, color=(255, 255, 255))
        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("c"), ord("C")):
            return "calibrate"
        if key in (ord("s"), ord("S"), 13, 32):
            return "use_saved" if existing_profile is not None else "skip"
        if key in (27, ord("q"), ord("Q")):
            return "quit"


def run_validation_phase(
    camera: cv2.VideoCapture,
    face_landmarker: Any,
    calibration_profile: dict[str, Any],
    *,
    target: str,
    message: str,
) -> dict[str, float] | None:
    announce_calibration_change(
        "Verification ecran" if target == "screen" else "Verification telephone"
    )

    prep_end = time.monotonic() + VALIDATION_PREP_SECONDS
    while time.monotonic() < prep_end:
        ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
        if not ok or frame is None:
            return None
        if landmarks is not None:
            draw_face_visuals(frame, landmarks, color_override=(255, 190, 0))
        draw_text_block(
            frame,
            [
                "Verification calibration",
                message,
                f"Debut dans {prep_end - time.monotonic():.1f}s",
                "On verifie que le profil reconnait bien la cible",
            ],
            color=(255, 255, 255),
        )
        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            return None

    total_samples = 0
    matched_samples = 0
    step_samples: list[dict[str, float]] = []
    capture_end = time.monotonic() + VALIDATION_CAPTURE_SECONDS
    while time.monotonic() < capture_end:
        ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
        if not ok or frame is None:
            return None
        if landmarks is not None:
            draw_face_visuals(frame, landmarks, color_override=(255, 190, 0))
            metrics = extract_attention_metrics(landmarks, frame.shape[1], frame.shape[0])
            _, enriched_metrics = classify_attention(metrics, calibration_profile)
            predicted_state = str(enriched_metrics.get("attention_state", "away"))
            step_samples.append(metrics)
            total_samples += 1
            if predicted_state == target:
                matched_samples += 1

        live_stability = compute_step_stability_score(step_samples)
        live_score_text = (
            f"Score live: {live_stability:.0f}/100"
            if live_stability is not None
            else "Score live: ..."
        )
        draw_text_block(
            frame,
            [
                "Verification calibration",
                message,
                f"Reconnu correctement: {matched_samples}/{max(total_samples, 1)}",
                live_score_text,
            ],
            color=(255, 255, 255),
        )
        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            return None

    if total_samples == 0:
        return {
            "accuracy": 0.0,
            "matched": 0.0,
            "total": 0.0,
            "stability_score": 0.0,
        }

    return {
        "accuracy": matched_samples / total_samples,
        "matched": float(matched_samples),
        "total": float(total_samples),
        "stability_score": float(compute_step_stability_score(step_samples) or 0.0),
    }


def run_calibration_validation(
    camera: cv2.VideoCapture,
    face_landmarker: Any,
    calibration_profile: dict[str, Any],
) -> dict[str, float] | None:
    screen_result = run_validation_phase(
        camera,
        face_landmarker,
        calibration_profile,
        target="screen",
        message="Regarde l'ecran",
    )
    if screen_result is None:
        return None

    phone_result = run_validation_phase(
        camera,
        face_landmarker,
        calibration_profile,
        target="phone",
        message="Regarde ton telephone",
    )
    if phone_result is None:
        return None

    validation_score = ((screen_result["accuracy"] + phone_result["accuracy"]) / 2.0) * 100.0
    validation_passed = (
        screen_result["total"] >= VALIDATION_MIN_SAMPLES
        and phone_result["total"] >= VALIDATION_MIN_SAMPLES
        and validation_score >= VALIDATION_PASS_SCORE
        and screen_result["accuracy"] >= 0.7
        and phone_result["accuracy"] >= 0.7
    )
    return {
        "validation_score": validation_score,
        "validation_passed": 1.0 if validation_passed else 0.0,
        "screen_validation_accuracy": screen_result["accuracy"],
        "phone_validation_accuracy": phone_result["accuracy"],
        "screen_validation_total": screen_result["total"],
        "phone_validation_total": phone_result["total"],
    }


def run_calibration(
    camera: cv2.VideoCapture,
    face_landmarker: Any,
) -> dict[str, Any] | None:
    screen_samples: list[dict[str, float]] = []
    phone_samples: list[dict[str, float]] = []
    calibration_steps = []
    for repetition in range(CALIBRATION_REPETITIONS):
        calibration_steps.append(
            ("screen", f"Phase {2 * repetition + 1}/{2 * CALIBRATION_REPETITIONS}: regarde l'ordinateur")
        )
        calibration_steps.append(
            (
                "phone",
                f"Phase {2 * repetition + 2}/{2 * CALIBRATION_REPETITIONS}: regarde ton telephone sans cacher ton visage",
            )
        )

    for target, message in calibration_steps:
        while True:
            calibration_instruction = (
                "Regarde l'ecran"
                if target == "screen"
                else "Regarde ton telephone"
            )
            announce_calibration_change(calibration_instruction)
            prep_end = time.monotonic() + CALIBRATION_PREP_SECONDS
            while time.monotonic() < prep_end:
                ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
                if not ok or frame is None:
                    return None
                if landmarks is not None:
                    draw_face_visuals(frame, landmarks, color_override=(0, 220, 255))

                remaining = prep_end - time.monotonic()
                draw_text_block(
                    frame,
                    [
                        "Calibration en cours",
                        message,
                        f"Debut dans {remaining:.1f}s",
                        "Un son te dit quand changer",
                        "Q ou ESC pour annuler",
                    ],
                    color=(255, 255, 255),
                )
                cv2.imshow(WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    return None

            step_samples: list[dict[str, float]] = []
            capture_end = time.monotonic() + CALIBRATION_CAPTURE_SECONDS
            while time.monotonic() < capture_end:
                ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
                if not ok or frame is None:
                    return None
                if landmarks is not None:
                    draw_face_visuals(frame, landmarks, color_override=(0, 220, 255))
                    step_samples.append(
                        extract_attention_metrics(landmarks, frame.shape[1], frame.shape[0])
                    )

                remaining = capture_end - time.monotonic()
                live_stability = compute_step_stability_score(step_samples)
                live_score_text = (
                    f"Score stabilite: {live_stability:.0f}/100"
                    if live_stability is not None
                    else "Score stabilite: ..."
                )
                draw_text_block(
                    frame,
                    [
                        "Capture calibration",
                        message,
                        f"Temps restant {remaining:.1f}s",
                        f"Echantillons valides: {len(step_samples)}",
                        live_score_text,
                    ],
                    color=(255, 255, 255),
                )
                cv2.imshow(WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    return None

            if len(step_samples) >= CALIBRATION_MIN_SAMPLES:
                if target == "screen":
                    screen_samples.extend(step_samples)
                else:
                    phone_samples.extend(step_samples)
                break

            retry_end = time.monotonic() + 1.8
            while time.monotonic() < retry_end:
                ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
                if not ok or frame is None:
                    return None
                if landmarks is not None:
                    draw_face_visuals(frame, landmarks, color_override=(0, 220, 255))
                draw_text_block(
                    frame,
                    [
                        "Pas assez d'echantillons detectes",
                        "On recommence cette phase",
                        "Garde tout ton visage visible",
                    ],
                    color=(0, 180, 255),
                )
                cv2.imshow(WINDOW_NAME, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    return None

    profile = build_calibration_profile(screen_samples, phone_samples)
    validation = run_calibration_validation(camera, face_landmarker, profile)
    if validation is not None:
        profile.update(
            {
                "validation_score": validation["validation_score"],
                "validation_passed": bool(validation["validation_passed"]),
                "screen_validation_accuracy": validation["screen_validation_accuracy"],
                "phone_validation_accuracy": validation["phone_validation_accuracy"],
                "screen_validation_total": int(validation["screen_validation_total"]),
                "phone_validation_total": int(validation["phone_validation_total"]),
            }
        )
    save_calibration_profile(profile)

    success_end = time.monotonic() + 5.0
    while time.monotonic() < success_end:
        ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
        if not ok or frame is None:
            return profile
        if landmarks is not None:
            draw_face_visuals(frame, landmarks, color_override=(0, 220, 255))
        draw_calibration_summary_panel(frame, profile)
        validation_score = float(profile.get("validation_score", 0.0))
        validation_status = (
            "CHECK OK"
            if bool(profile.get("validation_passed"))
            else "CHECK A REFAIRE"
        )
        draw_text_block(
            frame,
            [
                "Calibration terminee",
                "Le profil a ete enregistre",
                f"Score verification: {validation_score:.0f}/100",
                validation_status,
                "Lis le panneau a droite pour voir les moyennes calculees",
            ],
            color=(0, 220, 120) if bool(profile.get("validation_passed")) else (0, 190, 255),
        )
        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break

    return profile


def draw_face_visuals(
    frame: np.ndarray,
    landmarks: list[Any],
    looking_at_screen: bool | None = None,
    color_override: tuple[int, int, int] | None = None,
) -> None:
    height, width = frame.shape[:2]
    face_points = all_landmark_points(landmarks, width, height)
    face_box = bounding_box_from_points(face_points, width, height, FACE_BOX_PADDING)
    left_eye_box = bounding_box_from_indices(
        landmarks, LEFT_EYE_BOX, width, height, EYE_BOX_PADDING
    )
    right_eye_box = bounding_box_from_indices(
        landmarks, RIGHT_EYE_BOX, width, height, EYE_BOX_PADDING
    )

    if color_override is not None:
        box_color = color_override
        point_color = tuple(min(channel + 30, 255) for channel in color_override)
    else:
        box_color = (0, 190, 0) if looking_at_screen else (0, 0, 255)
        point_color = (80, 255, 80) if looking_at_screen else (80, 80, 255)

    for x, y in face_points:
        cv2.circle(frame, (x, y), POINT_RADIUS, point_color, -1, lineType=cv2.LINE_AA)

    for iris_indices in (LEFT_IRIS, RIGHT_IRIS):
        for index in iris_indices:
            iris_point = landmark_point(landmarks, index, width, height)
            cv2.circle(
                frame,
                (int(iris_point[0]), int(iris_point[1])),
                IRIS_POINT_RADIUS,
                (255, 255, 0),
                -1,
                lineType=cv2.LINE_AA,
            )

    cv2.rectangle(frame, face_box[:2], face_box[2:], box_color, 2)
    cv2.rectangle(frame, left_eye_box[:2], left_eye_box[2:], box_color, 2)
    cv2.rectangle(frame, right_eye_box[:2], right_eye_box[2:], box_color, 2)
    cv2.putText(
        frame,
        "VISAGE",
        (face_box[0], max(20, face_box[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        box_color,
        2,
    )
    cv2.putText(
        frame,
        "OEIL G",
        (left_eye_box[0], max(20, left_eye_box[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        box_color,
        2,
    )
    cv2.putText(
        frame,
        "OEIL D",
        (right_eye_box[0], max(20, right_eye_box[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        box_color,
        2,
    )


def draw_status_overlay(
    frame: np.ndarray,
    attention_state: str,
    face_found: bool,
    away_seconds: float,
    metrics: dict[str, float],
    video_launched: bool,
    calibration_mode_label: str,
) -> None:
    if not face_found:
        status = "VISAGE NON DETECTE"
        color = (0, 110, 255)
    elif attention_state == "screen":
        status = "ECRAN"
        color = (0, 180, 0)
    elif attention_state == "phone":
        status = "TELEPHONE"
        color = (0, 165, 255)
    else:
        status = "REGARD DETOURNE"
        color = (0, 0, 255)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], HEADER_HEIGHT), (17, 24, 39), -1)
    cv2.addWeighted(overlay, 0.88, frame, 0.12, 0.0, frame)

    x = 18
    y = 14
    x = draw_badge(frame, status, (x, y), background=color) + 10
    x = draw_badge(
        frame,
        f"AWAY {away_seconds:.1f}s",
        (x, y),
        background=(59, 76, 112),
    ) + 10
    x = draw_badge(
        frame,
        calibration_mode_label,
        (x, y),
        background=(53, 59, 72),
    ) + 10
    draw_badge(
        frame,
        "VIDEO ON" if video_launched else "VIDEO OFF",
        (x, y),
        background=(0, 0, 255) if video_launched else (72, 72, 72),
    )

    helper_labels = ["C recalibrer", "Q quitter"]
    helper_gap = 10
    helper_x = frame.shape[1] - 18
    for label in reversed(helper_labels):
        helper_x -= badge_width(label, font_scale=0.5)
        draw_badge(
            frame,
            label,
            (helper_x, y),
            background=(44, 49, 61),
            foreground=(220, 225, 235),
            font_scale=0.5,
        )
        helper_x -= helper_gap

    if metrics:
        footer_height = 62 if metrics.get("classification_mode") == 1.0 else 34
        footer_top = frame.shape[0] - footer_height
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (0, footer_top),
            (frame.shape[1], frame.shape[0]),
            (14, 14, 18),
            -1,
        )
        cv2.addWeighted(overlay, 0.76, frame, 0.24, 0.0, frame)
        bottom_y = frame.shape[0] - 16
        cv2.putText(
            frame,
            (
                f"Yaw: {metrics['yaw']:+.1f}  Pitch: {metrics['pitch']:+.1f}  "
                f"Roll: {metrics['roll']:+.1f}"
            ),
            (20, bottom_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (220, 220, 220),
            1,
        )
        cv2.putText(
            frame,
            f"Gaze X: {metrics['gaze_x']:.2f}  Gaze Y: {metrics['gaze_y']:.2f}",
            (520, bottom_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (220, 220, 220),
            1,
        )
        if metrics.get("classification_mode") == 1.0:
            cv2.putText(
                frame,
                (
                    f"Score ecran: {metrics['screen_score']:+.2f}  "
                    f"Limite: {metrics['decision_boundary']:+.2f}"
                ),
                (20, bottom_y - 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (220, 220, 220),
                1,
            )


def calibration_mode_text(calibration_profile: dict[str, Any] | None) -> str:
    if calibration_profile is not None:
        validation_score = calibration_profile.get("validation_score")
        validation_passed = calibration_profile.get("validation_passed")
        if validation_score is not None:
            prefix = "CALIB OK" if validation_passed else "CALIB CHECK"
            return f"{prefix} {float(validation_score):.0f}"
        return "CALIB PERSO"
    return "SEUILS PAR DEFAUT"


def main() -> int:
    try:
        video_path = ensure_video_downloaded()
        model_path = ensure_face_landmarker_model()
        player_command = find_browser_command()
        player_html = ensure_video_player_html()
        saved_calibration_profile = load_calibration_profile()
    except Exception as exc:
        print(f"Erreur pendant la preparation des ressources: {exc}")
        return 1

    face_landmarker_options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    face_landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(
        face_landmarker_options
    )

    camera = open_camera()
    if not camera.isOpened():
        print("Impossible d'ouvrir la camera.")
        face_landmarker.close()
        return 1

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, CAMERA_WINDOW_WIDTH, CAMERA_WINDOW_HEIGHT)
    player = ControlledVideoPlayer(video_path, player_command, player_html)
    calibration_choice = prompt_for_calibration(
        camera,
        face_landmarker,
        saved_calibration_profile,
    )
    if calibration_choice == "quit":
        camera.release()
        face_landmarker.close()
        cv2.destroyAllWindows()
        return 0

    calibration_profile = saved_calibration_profile if calibration_choice == "use_saved" else None
    if calibration_choice == "calibrate":
        calibration_profile = run_calibration(camera, face_landmarker)
        if calibration_profile is None:
            calibration_profile = saved_calibration_profile

    calibration_mode_label = calibration_mode_text(calibration_profile)

    last_looking_time = time.monotonic()

    try:
        while True:
            ok, frame, landmarks = read_and_process_frame(camera, face_landmarker)
            if not ok or frame is None:
                print("Lecture camera impossible.")
                break

            face_found = landmarks is not None
            looking_at_screen = False
            attention_state = "away"
            metrics: dict[str, float] = {}

            if face_found:
                metrics = extract_attention_metrics(landmarks, frame.shape[1], frame.shape[0])
                looking_at_screen, metrics = classify_attention(
                    metrics,
                    calibration_profile,
                )
                attention_state = str(
                    metrics.get(
                        "attention_state",
                        "screen" if looking_at_screen else "away",
                    )
                )
                draw_face_visuals(frame, landmarks, looking_at_screen)

            now = time.monotonic()
            if attention_state in {"screen", "phone"}:
                last_looking_time = now
                if player.is_active:
                    player.stop()

            away_seconds = max(0.0, now - last_looking_time)
            if (
                attention_state == "away"
                and away_seconds >= NOT_LOOKING_TRIGGER_SECONDS
                and not player.is_active
            ):
                try:
                    player.start()
                except Exception as exc:
                    print(f"Impossible de lancer la video: {exc}")
                    break

            if player.is_active:
                player.update()

            draw_status_overlay(
                frame=frame,
                attention_state=attention_state,
                face_found=face_found,
                away_seconds=away_seconds,
                metrics=metrics,
                video_launched=player.is_active,
                calibration_mode_label=calibration_mode_label,
            )

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("c"), ord("C")):
                player.stop()
                updated_profile = run_calibration(camera, face_landmarker)
                if updated_profile is not None:
                    calibration_profile = updated_profile
                    calibration_mode_label = calibration_mode_text(calibration_profile)
                last_looking_time = time.monotonic()
                continue
            if key in (27, ord("q"), ord("Q")):
                break
    finally:
        camera.release()
        face_landmarker.close()
        player.shutdown()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
